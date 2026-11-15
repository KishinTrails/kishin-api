"""
Athlete data router: Garmin activities and Withings measurements, read-only.

The data comes from the health-sync database (``HEALTH_DATABASE_URL``), read
with a read-only account; no route writes to it.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.engine import Connection

from kishin_trails import health
from kishin_trails.dependencies import requireLogin
from kishin_trails.schemas import (
    ActivityDetailOut,
    ActivitySummaryOut,
    DailyActivitiesOut,
    LineStringOut,
    MeasureDayOut,
    RecordsOut,
    TrackOut,
    TrackPropertiesOut,
)
from kishin_trails.willpower import FAT_ALPHA, MUSCLE_ALPHA

router = APIRouter(prefix="/athlete", tags=["athlete"], dependencies=[Depends(requireLogin)])

#: Days covered by the daily and measures routes when no range is given.
DEFAULT_RANGE_DAYS = 365

MAX_LIMIT = 1000


def getHealthConnection() -> Iterator[Connection]:
    """FastAPI dependency: one connection to the health database per request.

    Raises:
        HTTPException: 503 when ``HEALTH_DATABASE_URL`` is not set.
    """
    try:
        engine = health.sharedHealthEngine()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The health database is not configured."
        ) from error
    with engine.connect() as conn:
        yield conn


HealthConnection = Annotated[Connection, Depends(getHealthConnection)]
StartDate = Annotated[datetime.date | None, Query(description="First day, included")]
EndDate = Annotated[datetime.date | None, Query(description="Last day, included")]
Sport = Annotated[str | None, Query(description="GarminDB sport, such as running or walking")]


def _range(start: datetime.date | None, end: datetime.date | None) -> tuple[datetime.date, datetime.date]:
    """``start`` and ``end``, defaulting to the last ``DEFAULT_RANGE_DAYS`` days ending today in ``TIMEZONE``."""
    last = end or datetime.datetime.now(health.localZone()).date()
    first = start or last - datetime.timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if first > last:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start is after end.")
    return first, last


def _activityOr404(conn: Connection, activityId: str) -> health.Activity:
    activity = health.getActivity(conn, activityId)
    if activity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found.")
    return activity


@router.get(
    "/activities",
    summary="List activities",
    description="Garmin activities, newest first. Dates filter on the device-local start time.",
    response_model=list[ActivitySummaryOut],
)
def listActivities(
    conn: HealthConnection,
    *,
    start: StartDate = None,
    end: EndDate = None,
    sport: Sport = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[health.Activity]:
    """Activity summaries, newest first."""
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start is after end.")
    return health.queryActivities(
        conn,
        datetime.datetime.combine(start, datetime.time.min) if start else None,
        datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min) if end else None,
        sport,
        newestFirst=True,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/activities/daily",
    summary="Activity totals per day",
    description=(
        "One row per device-local day that has activities: count, distance, moving and elapsed time, ascent. "
        "Defaults to the last 365 days. For the calendar view and the distance and time graphs."
    ),
    response_model=list[DailyActivitiesOut],
)
def listDailyActivities(
    conn: HealthConnection,
    start: StartDate = None,
    end: EndDate = None,
    sport: Sport = None,
) -> list[health.DailyActivities]:
    """Totals per day."""
    first, last = _range(start, end)
    return health.dailyActivities(conn, first, last, sport)


@router.get(
    "/activities/{activity_id}",
    summary="Activity detail",
    description="Every stored field of one activity, with heart rate zones, running details and laps.",
    response_model=ActivityDetailOut,
)
def getActivityDetail(activity_id: str, conn: HealthConnection) -> dict:
    """One activity with everything stored about it."""
    detail = health.activityDetail(conn, activity_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found.")
    return detail


@router.get(
    "/activities/{activity_id}/track",
    summary="Activity GPS track",
    description="The GPS track as a GeoJSON Feature with a LineString of [lon, lat] positions.",
    response_model=TrackOut,
)
def getActivityTrack(activity_id: str, conn: HealthConnection) -> TrackOut:
    """GeoJSON track; empty with no bbox when the activity has no position."""
    _activityOr404(conn, activity_id)
    points = health.activityTrack(conn, activity_id)
    bbox = None
    if points:
        lons = [lon for lon, _ in points]
        lats = [lat for _, lat in points]
        bbox = [min(lons), min(lats), max(lons), max(lats)]
    return TrackOut(
        geometry=LineStringOut(coordinates=[[lon, lat] for lon, lat in points]),
        properties=TrackPropertiesOut(activity_id=activity_id, points=len(points)),
        bbox=bbox,
    )


@router.get(
    "/activities/{activity_id}/records",
    summary="Activity records",
    description="Every record of one activity, one list per field, for charts.",
    response_model=RecordsOut,
)
def getActivityRecords(activity_id: str, conn: HealthConnection) -> dict:
    """Record series of one activity."""
    _activityOr404(conn, activity_id)
    return {"activity_id": activity_id, **health.activityRecordSeries(conn, activity_id)}


@router.get(
    "/measures",
    summary="Body measurements per day",
    description=(
        "Withings readings per calendar day in TIMEZONE, with the fat ratio and muscle mass moving averages. "
        "Defaults to the last 365 days."
    ),
    response_model=list[MeasureDayOut],
)
def listMeasures(conn: HealthConnection, start: StartDate = None, end: EndDate = None) -> list[MeasureDayOut]:
    """Daily readings; the averages include readings before ``start``."""
    first, last = _range(start, end)
    zone = health.localZone()
    daily = {name: dict(health.dailyMeasures(conn, code, tz=zone)) for name, code in health.WITHINGS_TYPES.items()}
    fat = health.Series.fromDaily(sorted(daily["fat_ratio"].items()), FAT_ALPHA)
    muscle = health.Series.fromDaily(sorted(daily["muscle_mass"].items()), MUSCLE_ALPHA)

    days = sorted({day for values in daily.values() for day in values if first <= day <= last})
    return [
        MeasureDayOut(
            date=day,
            weight_kg=daily["weight"].get(day),
            fat_ratio_pct=daily["fat_ratio"].get(day),
            fat_ratio_ema=fat.averageOn(day),
            muscle_mass_kg=daily["muscle_mass"].get(day),
            muscle_mass_ema=muscle.averageOn(day),
            fat_mass_kg=daily["fat_mass_weight"].get(day),
            fat_free_mass_kg=daily["fat_free_mass"].get(day),
            bone_mass_kg=daily["bone_mass"].get(day),
            hydration_kg=daily["hydration"].get(day),
        ) for day in days
    ]
