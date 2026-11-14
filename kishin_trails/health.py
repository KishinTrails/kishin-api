"""
Read-only access to the measurement database written by health-sync.

GarminDB writes the schemas ``garmin`` and ``garmin_activities``; withings-sync
writes ``withings.measures``. The tables below declare only the columns read
here. They use their own ``MetaData``, so ``Base.metadata.create_all`` never
creates them, and the connection is opened in a read-only transaction mode on
PostgreSQL.

Values are returned in metric units whatever GarminDB's ``measurement_system``.
GarminDB's times (``start_time``, record ``timestamp``) are device-local and
naive; Withings ``measured_at`` is naive UTC.
"""

from __future__ import annotations

import datetime
import functools
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Time,
    create_engine,
    select,
)
from sqlalchemy.engine import Connection, Engine

from kishin_trails.config import settings
from kishin_trails.utils import latLngToS2Cell
from kishin_trails.willpower import axisProgress, ema

KM_PER_MILE = 1.609344
M_PER_FOOT = 0.3048

#: Schemas used here, before ``HEALTH_DB_PREFIX`` is applied.
SCHEMAS = ("garmin", "garmin_activities", "withings")

#: Withings measure type codes, as stored in ``withings.measures.type``.
WITHINGS_TYPES = {
    "weight": 1,
    "fat_free_mass": 5,
    "fat_ratio": 6,
    "fat_mass_weight": 8,
    "muscle_mass": 76,
    "hydration": 77,
    "bone_mass": 88,
}

HR_ZONES = range(1, 6)

metadata = MetaData()

attributes = Table(
    "attributes",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", String),
    schema="garmin",
)


def _commonColumns() -> list[Column]:
    """Columns GarminDB's activities and laps tables share (``ActivitiesCommon``)."""
    return [
        Column("start_time", DateTime),
        Column("stop_time", DateTime),
        Column("elapsed_time", Time),
        Column("moving_time", Time),
        Column("distance", Float),
        Column("cycles", Float),
        Column("avg_hr", Integer),
        Column("max_hr", Integer),
        Column("avg_rr", Float),
        Column("max_rr", Float),
        Column("calories", Integer),
        Column("avg_cadence", Integer),
        Column("max_cadence", Integer),
        Column("avg_speed", Float),
        Column("max_speed", Float),
        Column("ascent", Float),
        Column("descent", Float),
        Column("max_temperature", Float),
        Column("min_temperature", Float),
        Column("avg_temperature", Float),
        Column("start_lat", Float),
        Column("start_long", Float),
        Column("stop_lat", Float),
        Column("stop_long", Float),
        Column("hr_zones_method", String),
        *[Column(f"hrz_{zone}_hr", Integer) for zone in HR_ZONES],
        *[Column(f"hrz_{zone}_time", Time) for zone in HR_ZONES],
    ]


activities = Table(
    "activities",
    metadata,
    Column("activity_id", String, primary_key=True),
    Column("name", String),
    Column("description", String),
    Column("type", String),
    Column("laps", Integer),
    Column("sport", String),
    Column("sub_sport", String),
    Column("device_serial_number", BigInteger),
    Column("self_eval_feel", String),
    Column("self_eval_effort", String),
    Column("training_load", Float),
    Column("training_effect", Float),
    Column("anaerobic_training_effect", Float),
    *_commonColumns(),
    schema="garmin_activities",
)

activityLaps = Table(
    "activity_laps",
    metadata,
    Column("activity_id", String, primary_key=True),
    Column("lap", Integer, primary_key=True),
    *_commonColumns(),
    schema="garmin_activities",
)

stepsActivities = Table(
    "steps_activities",
    metadata,
    Column("activity_id", String, primary_key=True),
    Column("steps", Integer),
    Column("avg_pace", Time),
    Column("avg_moving_pace", Time),
    Column("max_pace", Time),
    Column("avg_steps_per_min", Integer),
    Column("max_steps_per_min", Integer),
    Column("avg_step_length", Float),
    Column("avg_vertical_ratio", Float),
    Column("avg_vertical_oscillation", Float),
    Column("avg_ground_contact_time", Time),
    Column("vo2_max", Float),
    schema="garmin_activities",
)

activityRecords = Table(
    "activity_records",
    metadata,
    Column("activity_id", String, primary_key=True),
    Column("record", Integer, primary_key=True),
    Column("timestamp", DateTime),
    Column("position_lat", Float),
    Column("position_long", Float),
    Column("distance", Float),
    Column("cadence", Integer),
    Column("altitude", Float),
    Column("hr", Integer),
    Column("speed", Float),
    Column("temperature", Float),
    schema="garmin_activities",
)

measures = Table(
    "measures",
    metadata,
    Column("grpid", BigInteger, primary_key=True),
    Column("type", SmallInteger, primary_key=True),
    Column("measured_at", DateTime, nullable=False),
    Column("value", Float, nullable=False),
    schema="withings",
)


@dataclass(frozen=True)
class Activity:
    """One Garmin activity summary, in metric units, durations in seconds.

    ``start_time`` and ``stop_time`` are the device-local times GarminDB stores.
    ``avg_speed_kmh`` is GarminDB's value, or distance over moving time when
    GarminDB has none.
    """

    activity_id: str
    name: str | None
    sport: str | None
    sub_sport: str | None
    start_time: datetime.datetime | None
    stop_time: datetime.datetime | None
    elapsed_sec: int | None
    moving_sec: int | None
    distance_km: float | None
    ascent_m: float | None
    descent_m: float | None
    avg_hr: int | None
    max_hr: int | None
    calories: int | None
    avg_speed_kmh: float | None
    training_effect: float | None
    anaerobic_training_effect: float | None


@dataclass(frozen=True)
class DailyActivities:
    """Totals of the activities started on one device-local day."""

    date: datetime.date
    count: int
    distance_km: float
    moving_sec: int
    elapsed_sec: int
    ascent_m: float


def healthEngine(url: str, prefix: str = "") -> Engine:
    """Engine on the measurement database.

    Args:
        url: SQLAlchemy URL of the reader account.
        prefix: health-sync's ``HEALTH_DB_PREFIX``, put in front of every schema name.

    Raises:
        ValueError: when ``url`` is empty.
    """
    if not url:
        raise ValueError("HEALTH_DATABASE_URL is not set")

    connectArgs = {}
    if url.startswith("postgresql"):
        connectArgs["options"] = "-c default_transaction_read_only=on"

    engine = create_engine(url, connect_args=connectArgs)
    return engine.execution_options(schema_translate_map={schema: prefix + schema for schema in SCHEMAS})


@functools.cache
def sharedHealthEngine() -> Engine:
    """One engine per process, from the settings, for the API."""
    return healthEngine(settings.HEALTH_DATABASE_URL, settings.HEALTH_DB_PREFIX)


def localZone() -> ZoneInfo:
    """The ``TIMEZONE`` setting.

    Raises:
        ValueError: when the name is not a known time zone.
    """
    try:
        return ZoneInfo(settings.TIMEZONE)
    except (KeyError, ValueError) as error:
        raise ValueError(f"TIMEZONE {settings.TIMEZONE!r} is not a known time zone.") from error


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def toSeconds(value: datetime.time | None) -> int | None:
    """Whole seconds in a GarminDB ``Time`` duration column."""
    if value is None:
        return None
    return value.hour * 3600 + value.minute * 60 + value.second


def toMilliseconds(value: datetime.time | None) -> float | None:
    """Milliseconds in a GarminDB ``Time`` duration column; None for 0, GarminDB's default."""
    if value is None:
        return None
    milliseconds = (value.hour * 3600 + value.minute * 60 + value.second) * 1000 + value.microsecond / 1000
    return milliseconds or None


def unitSystem(conn: Connection) -> str:
    """``metric`` or ``statute``, from GarminDB's ``measurement_system`` attribute.

    GarminDB stores the value as the string of its enum, such as
    ``DisplayMeasure.statute``. A missing attribute counts as metric, the
    GarminDB default.
    """
    value = conn.scalar(select(attributes.c.value).where(attributes.c.key == "measurement_system"))
    return "statute" if value and "statute" in value else "metric"


def toKm(distance: float | None, units: str) -> float | None:
    """A GarminDB distance (km or miles) in km. Speeds in km/h or mph convert the same way."""
    if distance is None:
        return None
    return distance * KM_PER_MILE if units == "statute" else distance


def toMeters(height: float | None, units: str) -> float | None:
    """A GarminDB altitude, ascent or descent (m or feet) in m."""
    if height is None:
        return None
    return height * M_PER_FOOT if units == "statute" else height


def toCelsius(temperature: float | None, units: str) -> float | None:
    """A GarminDB temperature (°C or °F) in °C."""
    if temperature is None:
        return None
    return (temperature - 32) * 5 / 9 if units == "statute" else temperature


def toPaceSecPerKm(pace: datetime.time | None, units: str) -> float | None:
    """A GarminDB pace (per km or per mile) in seconds per km; None for 0, GarminDB's default."""
    seconds = toSeconds(pace)
    if not seconds:
        return None
    return seconds / KM_PER_MILE if units == "statute" else float(seconds)


def averageSpeedKmh(speedKmh: float | None, distanceKm: float | None, movingSec: int | None) -> float | None:
    """``speedKmh``, or distance over moving time when it is missing."""
    if speedKmh:
        return speedKmh
    if distanceKm and movingSec:
        return distanceKm / (movingSec / 3600)
    return None


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


def _activity(row, units: str) -> Activity:
    distanceKm = toKm(row.distance, units)
    movingSec = toSeconds(row.moving_time)
    return Activity(
        activity_id=row.activity_id,
        name=row.name,
        sport=row.sport,
        sub_sport=row.sub_sport,
        start_time=row.start_time,
        stop_time=row.stop_time,
        elapsed_sec=toSeconds(row.elapsed_time),
        moving_sec=movingSec,
        distance_km=distanceKm,
        ascent_m=toMeters(row.ascent, units),
        descent_m=toMeters(row.descent, units),
        avg_hr=row.avg_hr,
        max_hr=row.max_hr,
        calories=row.calories,
        avg_speed_kmh=averageSpeedKmh(toKm(row.avg_speed, units), distanceKm, movingSec),
        training_effect=row.training_effect,
        anaerobic_training_effect=row.anaerobic_training_effect,
    )


def queryActivities(
    conn: Connection,
    start: datetime.datetime | None = None,
    end: datetime.datetime | None = None,
    sport: str | None = None,
    *,
    newestFirst: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> list[Activity]:
    """Activities started in ``[start, end)`` (device-local times), oldest first unless ``newestFirst``."""
    query = select(activities)
    if start is not None:
        query = query.where(activities.c.start_time >= start)
    if end is not None:
        query = query.where(activities.c.start_time < end)
    if sport is not None:
        query = query.where(activities.c.sport == sport)
    order = activities.c.start_time.desc() if newestFirst else activities.c.start_time
    query = query.order_by(order, activities.c.activity_id).offset(offset)
    if limit is not None:
        query = query.limit(limit)

    units = unitSystem(conn)
    return [_activity(row, units) for row in conn.execute(query)]


def recentActivities(conn: Connection, since: datetime.datetime, sport: str | None = None) -> list[Activity]:
    """Activities started at or after ``since``, oldest first."""
    return queryActivities(conn, since, None, sport)


def getActivity(conn: Connection, activityId: str) -> Activity | None:
    """One activity summary by id, or None."""
    row = conn.execute(select(activities).where(activities.c.activity_id == activityId)).first()
    return None if row is None else _activity(row, unitSystem(conn))


def dailyActivities(
    conn: Connection,
    start: datetime.date,
    end: datetime.date,
    sport: str | None = None,
) -> list[DailyActivities]:
    """Totals per device-local day from ``start`` to ``end`` included; days without activities are left out."""
    rows = queryActivities(
        conn,
        datetime.datetime.combine(start, datetime.time.min),
        datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min),
        sport,
    )
    byDay: dict[datetime.date, list[Activity]] = {}
    for activity in rows:
        if activity.start_time is not None:
            byDay.setdefault(activity.start_time.date(), []).append(activity)

    return [
        DailyActivities(
            date=day,
            count=len(dayActivities),
            distance_km=sum(activity.distance_km or 0.0 for activity in dayActivities),
            moving_sec=sum(activity.moving_sec or 0 for activity in dayActivities),
            elapsed_sec=sum(activity.elapsed_sec or 0 for activity in dayActivities),
            ascent_m=sum(activity.ascent_m or 0.0 for activity in dayActivities),
        ) for day, dayActivities in sorted(byDay.items())
    ]


def _hrZones(row) -> list[dict[str, Any]]:
    return [
        {
            "zone": zone,
            "hr": getattr(row, f"hrz_{zone}_hr"),
            "time_sec": toSeconds(getattr(row, f"hrz_{zone}_time")),
        } for zone in HR_ZONES
    ]


def _lap(row, units: str) -> dict[str, Any]:
    distanceKm = toKm(row.distance, units)
    movingSec = toSeconds(row.moving_time)
    return {
        "lap": row.lap,
        "start_time": row.start_time,
        "stop_time": row.stop_time,
        "elapsed_sec": toSeconds(row.elapsed_time),
        "moving_sec": movingSec,
        "distance_km": distanceKm,
        "avg_speed_kmh": averageSpeedKmh(toKm(row.avg_speed, units), distanceKm, movingSec),
        "max_speed_kmh": toKm(row.max_speed, units),
        "avg_hr": row.avg_hr,
        "max_hr": row.max_hr,
        "avg_cadence": row.avg_cadence,
        "max_cadence": row.max_cadence,
        "ascent_m": toMeters(row.ascent, units),
        "descent_m": toMeters(row.descent, units),
        "calories": row.calories,
        "avg_temperature_c": toCelsius(row.avg_temperature, units),
        "hr_zones": _hrZones(row),
    }


def _running(row, units: str) -> dict[str, Any]:
    return {
        "steps": row.steps,
        "avg_pace_sec_per_km": toPaceSecPerKm(row.avg_pace, units),
        "avg_moving_pace_sec_per_km": toPaceSecPerKm(row.avg_moving_pace, units),
        "max_pace_sec_per_km": toPaceSecPerKm(row.max_pace, units),
        "avg_steps_per_min": row.avg_steps_per_min,
        "max_steps_per_min": row.max_steps_per_min,
        "avg_step_length_mm": row.avg_step_length,
        "avg_vertical_ratio_pct": row.avg_vertical_ratio,
        "avg_vertical_oscillation_mm": row.avg_vertical_oscillation,
        "avg_ground_contact_time_ms": toMilliseconds(row.avg_ground_contact_time),
        "vo2_max": row.vo2_max,
    }


def activityDetail(conn: Connection, activityId: str) -> dict[str, Any] | None:
    """Every stored field of one activity, its heart rate zones, running details and laps; None if unknown."""
    row = conn.execute(select(activities).where(activities.c.activity_id == activityId)).first()
    if row is None:
        return None

    units = unitSystem(conn)
    detail: dict[str, Any] = vars(_activity(row, units)).copy()
    detail.update(
        {
            "description": row.description,
            "type": row.type,
            "lap_count": row.laps,
            "device_serial_number": row.device_serial_number,
            "self_eval_feel": row.self_eval_feel,
            "self_eval_effort": row.self_eval_effort,
            "training_load": row.training_load,
            "cycles": row.cycles,
            "avg_cadence": row.avg_cadence,
            "max_cadence": row.max_cadence,
            "max_speed_kmh": toKm(row.max_speed, units),
            "avg_rr": row.avg_rr,
            "max_rr": row.max_rr,
            "avg_temperature_c": toCelsius(row.avg_temperature, units),
            "min_temperature_c": toCelsius(row.min_temperature, units),
            "max_temperature_c": toCelsius(row.max_temperature, units),
            "start_lat": row.start_lat,
            "start_lon": row.start_long,
            "stop_lat": row.stop_lat,
            "stop_lon": row.stop_long,
            "hr_zones_method": row.hr_zones_method,
            "hr_zones": _hrZones(row),
        }
    )

    steps = conn.execute(select(stepsActivities).where(stepsActivities.c.activity_id == activityId)).first()
    detail["running"] = None if steps is None else _running(steps, units)

    laps = conn.execute(
        select(activityLaps).where(activityLaps.c.activity_id == activityId).order_by(activityLaps.c.lap)
    )
    detail["laps"] = [_lap(lap, units) for lap in laps]
    return detail


def activityTrack(conn: Connection, activityId: str) -> list[tuple[float, float]]:
    """``(lon, lat)`` of the records that have a position, in record order."""
    query = (
        select(activityRecords.c.position_long,
               activityRecords.c.position_lat).where(activityRecords.c.activity_id == activityId).where(
                   activityRecords.c.position_lat.is_not(None)
               ).where(activityRecords.c.position_long.is_not(None)).order_by(activityRecords.c.record)
    )
    return list(conn.execute(query).tuples())


def activityRecordSeries(conn: Connection, activityId: str) -> dict[str, list[Any]]:
    """The records of one activity as one list per field, in record order, metric units.

    ``elapsed_sec`` counts from the first record.
    """
    rows = conn.execute(
        select(activityRecords).where(activityRecords.c.activity_id == activityId).order_by(activityRecords.c.record)
    ).all()
    units = unitSystem(conn)
    first = rows[0].timestamp if rows and rows[0].timestamp is not None else None
    return {
        "timestamp": [row.timestamp for row in rows],
        "elapsed_sec": [
            (row.timestamp - first).total_seconds() if first is not None and row.timestamp is not None else None
            for row in rows
        ],
        "distance_km": [toKm(row.distance, units) for row in rows],
        "altitude_m": [toMeters(row.altitude, units) for row in rows],
        "hr": [row.hr for row in rows],
        "speed_kmh": [toKm(row.speed, units) for row in rows],
        "cadence": [row.cadence for row in rows],
        "temperature_c": [toCelsius(row.temperature, units) for row in rows],
        "lat": [row.position_lat for row in rows],
        "lon": [row.position_long for row in rows],
    }


def activityCells(conn: Connection, activityId: str, level: int = 16) -> list[str]:
    """S2 tokens crossed by the GPS track of an activity, in order of first visit.

    Records without a position are skipped. Each token appears once.
    """
    cells: dict[str, None] = {}
    for lon, lat in activityTrack(conn, activityId):
        cells.setdefault(latLngToS2Cell(lat, lon, level))
    return list(cells)


# ---------------------------------------------------------------------------
# Withings measures
# ---------------------------------------------------------------------------


def dailyMeasures(
    conn: Connection,
    typeCode: int,
    since: datetime.datetime | None = None,
    tz: datetime.tzinfo = datetime.UTC,
) -> list[tuple[datetime.date, float]]:
    """The last measurement of each calendar day in ``tz`` for one Withings type, oldest first.

    ``measured_at`` is stored as naive UTC; ``since`` is compared with it as is.
    """
    query = select(measures.c.measured_at, measures.c.value).where(measures.c.type == typeCode)
    if since is not None:
        query = query.where(measures.c.measured_at >= since)
    query = query.order_by(measures.c.measured_at)

    byDay: dict[datetime.date, float] = {}
    for measuredAt, value in conn.execute(query):
        byDay[measuredAt.replace(tzinfo=datetime.UTC).astimezone(tz).date()] = value
    return list(byDay.items())


@dataclass(frozen=True)
class Series:
    """The daily values of one Withings measure type and their moving average."""

    days: list[datetime.date]
    values: list[float]
    averages: list[float]

    @classmethod
    def fromDaily(cls, daily: list[tuple[datetime.date, float]], alpha: float) -> Series:
        """Builds a series from ``dailyMeasures`` output."""
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
