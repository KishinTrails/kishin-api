"""
Read-only access to the measurement database written by health-sync.

GarminDB writes the schemas ``garmin`` and ``garmin_activities``; withings-sync
writes ``withings.measures``. The tables below declare only the columns read
here. They use their own ``MetaData``, so ``Base.metadata.create_all`` never
creates them, and the connection is opened in a read-only transaction mode on
PostgreSQL.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

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

from kishin_trails.utils import latLngToS2Cell

KM_PER_MILE = 1.609344

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

metadata = MetaData()

attributes = Table(
    "attributes",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", String),
    schema="garmin",
)

activities = Table(
    "activities",
    metadata,
    Column("activity_id", String, primary_key=True),
    Column("name", String),
    Column("start_time", DateTime),
    Column("stop_time", DateTime),
    Column("elapsed_time", Time),
    Column("moving_time", Time),
    Column("distance", Float),
    Column("ascent", Float),
    Column("sport", String),
    Column("sub_sport", String),
    Column("avg_hr", Integer),
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
    """One Garmin activity, with distance in km and durations in seconds.

    ``start_time`` is the device-local time GarminDB stores.
    """

    activity_id: str
    name: str | None
    start_time: datetime.datetime | None
    sport: str | None
    sub_sport: str | None
    distance_km: float | None
    elapsed_sec: int | None
    moving_sec: int | None
    ascent: float | None
    avg_hr: int | None


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


def toSeconds(value: datetime.time | None) -> int | None:
    """Seconds in a GarminDB ``Time`` duration column."""
    if value is None:
        return None
    return value.hour * 3600 + value.minute * 60 + value.second


def unitSystem(conn: Connection) -> str:
    """``metric`` or ``statute``, from GarminDB's ``measurement_system`` attribute.

    GarminDB stores the value as the string of its enum, such as
    ``DisplayMeasure.statute``. A missing attribute counts as metric, the
    GarminDB default.
    """
    value = conn.scalar(select(attributes.c.value).where(attributes.c.key == "measurement_system"))
    return "statute" if value and "statute" in value else "metric"


def toKm(distance: float | None, units: str) -> float | None:
    """A GarminDB distance converted to km."""
    if distance is None:
        return None
    return distance * KM_PER_MILE if units == "statute" else distance


def _activity(row, units: str) -> Activity:
    return Activity(
        activity_id=row.activity_id,
        name=row.name,
        start_time=row.start_time,
        sport=row.sport,
        sub_sport=row.sub_sport,
        distance_km=toKm(row.distance, units),
        elapsed_sec=toSeconds(row.elapsed_time),
        moving_sec=toSeconds(row.moving_time),
        ascent=row.ascent,
        avg_hr=row.avg_hr,
    )


def recentActivities(conn: Connection, since: datetime.datetime, sport: str | None = None) -> list[Activity]:
    """Activities started at or after ``since``, oldest first."""
    query = select(activities).where(activities.c.start_time >= since).order_by(activities.c.start_time)
    if sport is not None:
        query = query.where(activities.c.sport == sport)

    units = unitSystem(conn)
    return [_activity(row, units) for row in conn.execute(query)]


def getActivity(conn: Connection, activityId: str) -> Activity | None:
    """One activity by id, or None."""
    row = conn.execute(select(activities).where(activities.c.activity_id == activityId)).first()
    return None if row is None else _activity(row, unitSystem(conn))


def activityCells(conn: Connection, activityId: str, level: int = 16) -> list[str]:
    """S2 tokens crossed by the GPS track of an activity, in order of first visit.

    Records without a position are skipped. Each token appears once.
    """
    query = (
        select(activityRecords.c.position_lat,
               activityRecords.c.position_long).where(activityRecords.c.activity_id == activityId).where(
                   activityRecords.c.position_lat.is_not(None)
               ).where(activityRecords.c.position_long.is_not(None)).order_by(activityRecords.c.record)
    )

    cells: dict[str, None] = {}
    for lat, lng in conn.execute(query):
        cells.setdefault(latLngToS2Cell(lat, lng, level))
    return list(cells)


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
