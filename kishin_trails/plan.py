"""
Training plan router: the active plan's progression and manual completion.

A run is completed by linking a Garmin activity and entering an RPE (wiki
"Athlete Integration" §6). Any running activity of the training's week is
accepted, whatever its distance or duration. Cross-training, leg day and yoga are ticked. The plan
itself is imported from a local file with ``kishin plan import``; no route
creates or edits plans. Willpower is not computed here.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from kishin_trails import health
from kishin_trails.athlete import getHealthConnection
from kishin_trails.database import getDb
from kishin_trails.dependencies import requireLogin
from kishin_trails.schemas import (
    ActivitySummaryOut,
    CompleteTrainingIn,
    CompletionActivityOut,
    CompletionOut,
    PlanOut,
    PlanSegmentOut,
    PlanTrainingOut,
    PlanWeekOut,
    WeekRunningOut,
)
from kishin_trails.training import ACTIVE_PLAN_ID, ActivePlan, Plan, Training, TrainingCompletion
from kishin_trails.training_types import TICK_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plan", tags=["plan"], dependencies=[Depends(requireLogin)])

#: GarminDB sport of the activities that can complete a run.
RUNNING_SPORT = "running"

def optionalHealthConnection() -> Iterator[Connection | None]:
    """FastAPI dependency: a health database connection, or None when it is not configured or not reachable."""
    try:
        engine = health.sharedHealthEngine()
        conn = engine.connect()
    except (ValueError, SQLAlchemyError) as error:
        logger.info("Health database unavailable: %s", error)
        yield None
        return
    try:
        yield conn
    finally:
        conn.close()


DbSession = Annotated[Session, Depends(getDb)]
OptionalHealth = Annotated[Connection | None, Depends(optionalHealthConnection)]


def weekRange(startDate: datetime.date, weekNumber: int) -> tuple[datetime.date, datetime.date]:
    """Monday and Sunday of a plan week."""
    monday = startDate + datetime.timedelta(weeks=weekNumber - 1)
    return monday, monday + datetime.timedelta(days=6)


def trainingTargets(training: Training) -> tuple[float | None, int | None]:
    """Distance (km) and duration (s) targets of a training, None when it has none of that kind."""
    return training.total_distance_km or None, training.total_duration_sec or None


def activePlan(session: Session) -> tuple[ActivePlan, Plan] | None:
    """The active plan, or None."""
    active = session.get(ActivePlan, ACTIVE_PLAN_ID)
    if active is None:
        return None
    return active, active.plan


def getTraining(session: Session, trainingId: int) -> Training:
    """A training of any plan.

    Raises:
        HTTPException: 404 when it does not exist.
    """
    training = session.get(Training, trainingId)
    if training is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training not found.")
    return training


def _completionOut(completion: TrainingCompletion, conn: Connection | None) -> CompletionOut:
    activity = None
    if completion.activity_id is not None:
        summary = health.getActivity(conn, completion.activity_id) if conn is not None else None
        activity = CompletionActivityOut(
            activity_id=completion.activity_id,
            name=summary.name if summary else None,
            start_time=summary.start_time if summary else None,
            distance_km=summary.distance_km if summary else None,
            moving_sec=summary.moving_sec if summary else None,
        )
    return CompletionOut(completed_at=completion.completed_at, rpe=completion.rpe, activity=activity)


def _trainingOut(training: Training, conn: Connection | None) -> PlanTrainingOut:
    distanceKm, durationSec = trainingTargets(training)
    return PlanTrainingOut(
        id=training.id,
        position=training.position,
        type=training.training_type.value,
        is_tick=training.training_type in TICK_TYPES,
        target_distance_km=distanceKm,
        target_duration_sec=durationSec,
        segments=[
            PlanSegmentOut(
                position=segment.position,
                type=segment.segment_type.value,
                duration_sec=segment.duration_sec,
                distance_km=segment.target_distance_km,
                rpe_min=segment.target_rpe_min,
                rpe_max=segment.target_rpe_max,
                pace_min_km=segment.target_pace_min_km,
            ) for segment in training.segments
        ],
        completion=_completionOut(training.completion, conn) if training.completion else None,
    )


def _weeklyRunning(conn: Connection, startDate: datetime.date, weekCount: int) -> dict[int, WeekRunningOut]:
    """Running activities of the plan's weeks, by week number."""
    first, _ = weekRange(startDate, 1)
    _, last = weekRange(startDate, weekCount)
    runs = health.queryActivities(
        conn,
        datetime.datetime.combine(first, datetime.time.min),
        datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min),
        RUNNING_SPORT,
    )
    weeks = {
        number: WeekRunningOut(run_count=0, run_km=0.0, run_moving_sec=0, longest_run_km=None)
        for number in range(1, weekCount + 1)
    }
    for run in runs:
        if run.start_time is None:
            continue
        number = (run.start_time.date() - startDate).days // 7 + 1
        week = weeks.get(number)
        if week is None:
            continue
        km = run.distance_km or 0.0
        week.run_count += 1
        week.run_km += km
        week.run_moving_sec += run.moving_sec or 0
        week.longest_run_km = max(week.longest_run_km or 0.0, km)
    return weeks


def _weeksOut(
    plan: Plan,
    startDate: datetime.date,
    conn: Connection | None,
    running: dict[int, WeekRunningOut] | None,
) -> list[PlanWeekOut]:
    trainingsByWeek: dict[int, list[Training]] = {}
    for training in plan.trainings:
        trainingsByWeek.setdefault(training.week_number, []).append(training)

    weeks = []
    for week in plan.weeks:
        start, end = weekRange(startDate, week.week_number)
        weeks.append(
            PlanWeekOut(
                week_number=week.week_number,
                phase=week.phase.value,
                start=start,
                end=end,
                trainings=[_trainingOut(training, conn) for training in trainingsByWeek.get(week.week_number, [])],
                running=running.get(week.week_number) if running is not None else None,
            )
        )
    return weeks


@router.get(
    "",
    summary="Active plan progression",
    description="The active plan with its weeks, trainings, completions and the running Garmin recorded each week.",
    response_model=PlanOut,
)
def getPlan(session: DbSession, conn: OptionalHealth) -> PlanOut:
    """Progression of the active plan."""
    found = activePlan(session)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active plan.")
    active, plan = found

    weekCount = len(plan.weeks)
    running: dict[int, WeekRunningOut] | None = None
    if conn is not None:
        try:
            running = _weeklyRunning(conn, active.start_date, weekCount)
        except SQLAlchemyError as error:
            logger.info("Health database query failed: %s", error)
            conn = None

    today = datetime.datetime.now(health.localZone()).date()
    return PlanOut(
        plan_id=plan.id,
        name=plan.name,
        goal_type=plan.goal_type,
        target_fat_ratio=plan.target_fat_ratio,
        target_muscle_mass_kg=plan.target_muscle_mass_kg,
        start_date=active.start_date,
        current_week=active.currentWeek(today),
        week_count=weekCount,
        health_available=conn is not None,
        weeks=_weeksOut(plan, active.start_date, conn, running),
    )


@router.get(
    "/trainings/{training_id}/candidates",
    summary="Activities that can complete a run",
    description="Garmin running activities of the training's week that are not linked to another training.",
    response_model=list[ActivitySummaryOut],
)
def getCandidates(
    training_id: int,
    session: DbSession,
    conn: Annotated[Connection, Depends(getHealthConnection)],
) -> list[health.Activity]:
    """Unlinked running activities of the training's week, oldest first."""
    training = getTraining(session, training_id)
    if training.training_type in TICK_TYPES:
        return []
    active = session.get(ActivePlan, ACTIVE_PLAN_ID)
    startDate = active.start_date if active is not None and active.plan_id == training.plan_id else None
    if startDate is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The training is not in the active plan.")

    monday, sunday = weekRange(startDate, training.week_number)
    linked = set(session.scalars(select(TrainingCompletion.activity_id).where(TrainingCompletion.activity_id.is_not(None))))
    activities = health.queryActivities(
        conn,
        datetime.datetime.combine(monday, datetime.time.min),
        datetime.datetime.combine(sunday + datetime.timedelta(days=1), datetime.time.min),
        RUNNING_SPORT,
    )
    return [activity for activity in activities if activity.activity_id not in linked]


@router.post(
    "/trainings/{training_id}/complete",
    summary="Mark a training done",
    description=(
        "A run takes a Garmin activity and an RPE; any distance or duration is accepted. "
        "A tick item takes neither."
    ),
    response_model=PlanTrainingOut,
    status_code=status.HTTP_201_CREATED,
)
def completeTraining(
    training_id: int,
    body: CompleteTrainingIn,
    session: DbSession,
    conn: OptionalHealth,
) -> PlanTrainingOut:
    """Records the completion."""
    training = getTraining(session, training_id)
    if training.completion is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The training is already done.")

    if training.training_type in TICK_TYPES:
        if body.activity_id is not None or body.rpe is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A tick item takes no activity and no RPE."
            )
    else:
        if body.activity_id is None or body.rpe is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A run needs an activity and an RPE."
            )
        if conn is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The health database is not available."
            )
        activity = health.getActivity(conn, body.activity_id)
        if activity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found.")
        taken = session.scalar(select(TrainingCompletion).where(TrainingCompletion.activity_id == body.activity_id))
        if taken is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="The activity already completes another training."
            )

    training.completion = TrainingCompletion(
        completed_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        activity_id=body.activity_id,
        rpe=body.rpe,
    )
    session.commit()
    session.refresh(training)
    return _trainingOut(training, conn)


@router.delete(
    "/trainings/{training_id}/complete",
    summary="Undo a completion",
    status_code=status.HTTP_204_NO_CONTENT,
)
def uncompleteTraining(training_id: int, session: DbSession) -> None:
    """Removes the completion."""
    training = getTraining(session, training_id)
    if training.completion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The training is not done.")
    training.completion = None
    session.commit()
