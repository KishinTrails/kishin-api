"""
``kishin health`` — read the health-sync measurement database and compute the
Willpower formulas on it. Nothing here writes to any database.

    kishin health activities --days 30 --sport running
    kishin health cells 12345678901
    kishin health measures --days 90
    kishin health multiplier --start 2026-01-05 --fat-target 20 --muscle-target 40 --w-fat 0.5 --decay 0.05
    kishin health willpower 12345678901 --type long --rpe 4 --partial-bonus 1.25 --target-km 15

The database URL comes from ``HEALTH_DATABASE_URL`` (environment, ``.env`` or
``/run/secrets/HEALTH_DATABASE_URL``).
"""

from __future__ import annotations

import datetime
import enum
from bisect import bisect_right
from dataclasses import dataclass
from typing import Annotated

import typer
from sqlalchemy.engine import Connection

from kishin_trails import health
from kishin_trails.config import settings
from kishin_trails.training_types import TrainingType
from kishin_trails.willpower import (
    BASELINE,
    adherenceBonus,
    axisProgress,
    dailyMultipliers,
    earnedWillpower,
    ema,
    targetMultiplier,
)

from .common import fail

app = typer.Typer(help="Read health-sync data and compute the Willpower formulas.", no_args_is_help=True)

#: Fraction of a distance target that completes a distance-based run (§6).
DISTANCE_COMPLETION_RATIO = 0.9

#: Duration of the fundamental run, in seconds.
FUNDAMENTAL_RUN_SEC = 30 * 60


class RunType(str, enum.Enum):
    """Run types that earn Willpower."""

    LONG = "long"
    FUNDAMENTAL = "fundamental"


RUN_TRAINING_TYPES = {
    RunType.LONG: TrainingType.EXPLORATORY_LONG_RUN,
    RunType.FUNDAMENTAL: TrainingType.FUNDAMENTAL_RUN,
}


def connect() -> Connection:
    """Opens a connection to the measurement database, or exits with an error."""
    try:
        engine = health.healthEngine(settings.HEALTH_DATABASE_URL, settings.HEALTH_DB_PREFIX)
    except ValueError as error:
        fail(str(error))
        raise
    return engine.connect()


def formatDuration(seconds: int | None) -> str:
    """``h:mm:ss``, or ``-``."""
    if seconds is None:
        return "-"
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def formatNumber(value: float | None, digits: int = 2) -> str:
    """``value`` with ``digits`` decimals, or ``-``."""
    return "-" if value is None else f"{value:.{digits}f}"


@dataclass(frozen=True)
class Series:
    """The daily values of one Withings measure type and their moving average."""

    days: list[datetime.date]
    values: list[float]
    averages: list[float]

    @classmethod
    def fromDaily(cls, daily: list[tuple[datetime.date, float]], alpha: float) -> Series:
        """Builds a series from ``health.dailyMeasures`` output."""
        values = [value for _, value in daily]
        return cls([day for day, _ in daily], values, ema(values, alpha))

    def valueOf(self, day: datetime.date) -> float | None:
        """The measurement of ``day``, or None."""
        index = bisect_right(self.days, day)
        return self.values[index - 1] if index and self.days[index - 1] == day else None

    def averageOn(self, day: datetime.date) -> float | None:
        """The moving average at the last measurement on or before ``day``."""
        index = bisect_right(self.days, day)
        return self.averages[index - 1] if index else None

    def progressOn(self, day: datetime.date, start: float | None, target: float | None) -> float | None:
        """``axisProgress`` of the moving average on ``day``."""
        current = self.averageOn(day)
        if start is None or current is None:
            return None
        return axisProgress(start, current, target)


def loadSeries(fatAlpha: float, muscleAlpha: float) -> tuple[Series, Series]:
    """The fat ratio and muscle mass series, over every measurement in the database."""
    with connect() as conn:
        fat = health.dailyMeasures(conn, health.WITHINGS_TYPES["fat_ratio"])
        muscle = health.dailyMeasures(conn, health.WITHINGS_TYPES["muscle_mass"])
    try:
        return Series.fromDaily(fat, fatAlpha), Series.fromDaily(muscle, muscleAlpha)
    except ValueError as error:
        fail(str(error))
        raise


@dataclass(frozen=True)
class Composition:
    """Both body composition series, their start values and their targets."""

    fat: Series
    muscle: Series
    fatStart: float | None
    muscleStart: float | None
    fatTarget: float | None
    muscleTarget: float | None
    wFat: float

    @classmethod
    def load(cls, firstDay: datetime.date, targets: tuple[float | None, float | None], wFat: float,
             alphas: tuple[float, float]) -> Composition:
        """Reads the series; the start values are the moving averages on ``firstDay``.

        Exits with an error when a target is given and its series has no
        measurement on or before ``firstDay``.
        """
        fat, muscle = loadSeries(*alphas)
        fatTarget, muscleTarget = targets
        fatStart, muscleStart = fat.averageOn(firstDay), muscle.averageOn(firstDay)
        if fatTarget is not None and fatStart is None:
            fail(f"No fat ratio on or before {firstDay}; fat_start is undefined.")
        if muscleTarget is not None and muscleStart is None:
            fail(f"No muscle mass on or before {firstDay}; muscle_start is undefined.")
        return cls(fat, muscle, fatStart, muscleStart, fatTarget, muscleTarget, wFat)

    def measured(self, day: datetime.date) -> bool:
        """Whether ``day`` has a fat ratio or a muscle mass."""
        return self.fat.valueOf(day) is not None or self.muscle.valueOf(day) is not None

    def fatProgress(self, day: datetime.date) -> float | None:
        """Fat axis progress on ``day``."""
        return self.fat.progressOn(day, self.fatStart, self.fatTarget)

    def muscleProgress(self, day: datetime.date) -> float | None:
        """Muscle axis progress on ``day``."""
        return self.muscle.progressOn(day, self.muscleStart, self.muscleTarget)

    def target(self, day: datetime.date) -> float:
        """Target multiplier on ``day``."""
        return targetMultiplier(self.fatProgress(day), self.muscleProgress(day), self.wFat)


def printMultipliers(
    composition: Composition, days: list[datetime.date], multipliers: list[float], baseCap: float | None
) -> None:
    """Prints one line per day of the ``multiplier`` command."""
    typer.echo(
        f"fat_start: {formatNumber(composition.fatStart)}  muscle_start: {formatNumber(composition.muscleStart)}"
    )
    header = (
        f"{'day (UTC)':<10}  {'m':<1}  {'fat ema':>7}  {'mus ema':>7}  {'fat prog':>8}  {'mus prog':>8}  "
        f"{'target':>6}  {'mult':>6}"
    )
    typer.echo(header + (f"  {'cap':>8}" if baseCap is not None else ""))
    for day, value in zip(days, multipliers):
        line = (
            f"{day.isoformat():<10}  {'*' if composition.measured(day) else ' '}  "
            f"{formatNumber(composition.fat.averageOn(day)):>7}  {formatNumber(composition.muscle.averageOn(day)):>7}  "
            f"{formatNumber(composition.fatProgress(day), 3):>8}  {formatNumber(composition.muscleProgress(day), 3):>8}  "
            f"{formatNumber(composition.target(day), 3):>6}  {formatNumber(value, 3):>6}"
        )
        if baseCap is not None:
            line += f"  {formatNumber(baseCap * value, 1):>8}"
        typer.echo(line)


def getActivityOrFail(conn: Connection, activityId: str) -> health.Activity:
    """The activity, or exits with an error."""
    activity = health.getActivity(conn, activityId)
    if activity is None:
        fail(f"No activity {activityId}.")
        raise typer.Exit(code=1)
    return activity


@app.command("activities")
def listActivities(
    days: Annotated[int, typer.Option("--days", help="How many days back to list")] = 30,
    sport: Annotated[str | None, typer.Option("--sport", help="Only this GarminDB sport, such as running")] = None,
) -> None:
    """List recent Garmin activities, with distance in km."""
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    with connect() as conn:
        rows = health.recentActivities(conn, since, sport)

    if not rows:
        typer.echo("No activities.")
        return

    typer.echo(f"{'start (device time)':<19}  {'activity id':<14}  {'sport':<12}  {'km':>7}  {'moving':>8}  {'ascent':>6}")
    for activity in rows:
        start = activity.start_time.strftime("%Y-%m-%d %H:%M") if activity.start_time else "-"
        typer.echo(
            f"{start:<19}  {activity.activity_id:<14}  {activity.sport or '-':<12}  "
            f"{formatNumber(activity.distance_km):>7}  {formatDuration(activity.moving_sec):>8}  "
            f"{formatNumber(activity.ascent, 0):>6}"
        )


@app.command("cells")
def cells(
    activityId: Annotated[str, typer.Argument(help="GarminDB activity_id")],
    level: Annotated[int, typer.Option("--level", help="S2 level")] = 16,
) -> None:
    """List the S2 cells crossed by an activity's GPS track."""
    with connect() as conn:
        getActivityOrFail(conn, activityId)
        tokens = health.activityCells(conn, activityId, level)

    typer.echo(f"cells: {len(tokens)}")
    for token in tokens:
        typer.echo(token)


@app.command("measures")
def listMeasures(
    days: Annotated[int, typer.Option("--days", help="How many days back to show")] = 90,
    fatAlpha: Annotated[float, typer.Option("--fat-alpha", help="EMA alpha of the fat ratio")] = 0.30,
    muscleAlpha: Annotated[float, typer.Option("--muscle-alpha", help="EMA alpha of the muscle mass")] = 0.10,
) -> None:
    """Show fat ratio and muscle mass per day, with their moving averages.

    The averages run over every measurement in the database, including those
    before the days shown.
    """
    fat, muscle = loadSeries(fatAlpha, muscleAlpha)

    first = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=days)
    shown = sorted(day for day in set(fat.days) | set(muscle.days) if day >= first)
    if not shown:
        typer.echo("No measurements.")
        return

    typer.echo(f"{'day (UTC)':<10}  {'fat %':>6}  {'fat ema':>7}  {'muscle':>6}  {'mus ema':>7}")
    for day in shown:
        typer.echo(
            f"{day.isoformat():<10}  {formatNumber(fat.valueOf(day)):>6}  {formatNumber(fat.averageOn(day)):>7}  "
            f"{formatNumber(muscle.valueOf(day)):>6}  {formatNumber(muscle.averageOn(day)):>7}"
        )


@app.command("multiplier")
def multiplier(
    *,
    start: Annotated[datetime.datetime, typer.Option("--start", formats=["%Y-%m-%d"], help="First day of the plan")],
    wFat: Annotated[float, typer.Option("--w-fat", help="W_FAT; W_MUSCLE is 1 - W_FAT")],
    decay: Annotated[float, typer.Option("--decay", help="DECAY_PER_MISSED_DAY, for example 0.05")],
    fatTarget: Annotated[float | None, typer.Option("--fat-target", help="Target fat ratio in %")] = None,
    muscleTarget: Annotated[float | None, typer.Option("--muscle-target", help="Target muscle mass in kg")] = None,
    end: Annotated[
        datetime.datetime | None, typer.Option("--end", formats=["%Y-%m-%d"], help="Last day; default today (UTC)")
    ] = None,
    baseCap: Annotated[float | None, typer.Option("--base-cap", help="Base_Cap, to print the Willpower cap")] = None,
    fatAlpha: Annotated[float, typer.Option("--fat-alpha", help="EMA alpha of the fat ratio")] = 0.30,
    muscleAlpha: Annotated[float, typer.Option("--muscle-alpha", help="EMA alpha of the muscle mass")] = 0.10,
) -> None:
    """Compute the Willpower cap multiplier day by day from the plan start.

    fat_start and muscle_start are the moving averages on the start day. A day
    counts as measured when it has a fat ratio or a muscle mass. Before the first
    day the multiplier is BASELINE (1.0).
    """
    firstDay = start.date()
    lastDay = end.date() if end else datetime.datetime.now(datetime.UTC).date()
    if lastDay < firstDay:
        fail("--end is before --start.")

    composition = Composition.load(firstDay, (fatTarget, muscleTarget), wFat, (fatAlpha, muscleAlpha))
    days = [firstDay + datetime.timedelta(days=offset) for offset in range((lastDay - firstDay).days + 1)]
    try:
        multipliers = dailyMultipliers(
            [composition.target(day) if composition.measured(day) else None for day in days], BASELINE, decay
        )
    except ValueError as error:
        fail(str(error))
        raise

    printMultipliers(composition, days, multipliers, baseCap)


@app.command("willpower")
def willpower(
    activityId: Annotated[str, typer.Argument(help="GarminDB activity_id")],
    runType: Annotated[RunType, typer.Option("--type", help="Which training the activity completes")],
    rpe: Annotated[int, typer.Option("--rpe", min=1, max=10, help="RPE entered by the player")],
    partialBonus: Annotated[float, typer.Option("--partial-bonus", help="Adherence bonus of the partial band")],
    targetKm: Annotated[float | None, typer.Option("--target-km", help="Long run target, to check completion")] = None,
) -> None:
    """Compute the Willpower an activity earns, and whether it completes the training."""
    with connect() as conn:
        activity = getActivityOrFail(conn, activityId)

    if activity.distance_km is None:
        fail(f"Activity {activityId} has no distance.")
        raise typer.Exit(code=1)

    trainingType = RUN_TRAINING_TYPES[runType]
    try:
        bonus = adherenceBonus(trainingType, rpe, partialBonus)
        earned = earnedWillpower(activity.distance_km, trainingType, rpe, partialBonus)
    except ValueError as error:
        fail(str(error))
        raise

    typer.echo(f"distance: {activity.distance_km:.2f} km")
    typer.echo(f"adherence bonus: {bonus}")
    typer.echo(f"willpower: {earned:.1f}")

    if runType is RunType.FUNDAMENTAL:
        duration = activity.elapsed_sec
        complete = duration is not None and duration >= FUNDAMENTAL_RUN_SEC
        typer.echo(f"elapsed time: {formatDuration(duration)}  complete: {complete}")
    elif targetKm is not None:
        complete = activity.distance_km >= targetKm * DISTANCE_COMPLETION_RATIO
        typer.echo(f"target: {targetKm:.2f} km  complete: {complete}")
