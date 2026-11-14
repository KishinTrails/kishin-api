"""
A made-up health-sync database for the tests: in-memory SQLite with every schema
mapped to none, since SQLite has no schemas. All rows are made up.
"""

from __future__ import annotations

import datetime

from sqlalchemy import create_engine, insert
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from kishin_trails import health

NOW = datetime.datetime.now()
TODAY = datetime.datetime.now(datetime.UTC).date()

# Two points in one level-16 cell, then one point about 300 m east.
TRACK = [(48.8566, 2.3522), (48.85661, 2.35221), (48.8566, 2.3562)]


def _row(table, **fields) -> dict:
    """A row of ``table``; columns not given are null."""
    return {column.name: None for column in table.columns} | fields


def _activity(**fields) -> dict:
    """An activities row; columns not given are null."""
    return _row(health.activities, **fields)


def _day(offset: int, hour: int = 7) -> datetime.datetime:
    """A naive UTC timestamp ``offset`` days before today."""
    return datetime.datetime.combine(TODAY - datetime.timedelta(days=offset), datetime.time(hour))


def buildHealthEngine() -> Engine:
    """Creates and fills the made-up health database."""
    sqlite = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False
        },
        poolclass=StaticPool,
    ).execution_options(schema_translate_map={schema: None for schema in health.SCHEMAS})
    health.metadata.create_all(sqlite)

    with sqlite.begin() as conn:
        conn.execute(insert(health.attributes).values(key="measurement_system", value="DisplayMeasure.metric"))
        conn.execute(
            insert(health.activities),
            [
                _activity(
                    activity_id="1001",
                    name="Example Run",
                    start_time=NOW - datetime.timedelta(days=2),
                    stop_time=NOW - datetime.timedelta(days=2) + datetime.timedelta(minutes=33),
                    elapsed_time=datetime.time(0, 32, 10),
                    moving_time=datetime.time(0, 31, 0),
                    distance=6.0,
                    ascent=40.0,
                    descent=35.0,
                    avg_hr=140,
                    max_hr=165,
                    calories=400,
                    sport="running",
                    sub_sport="generic",
                    laps=2,
                    training_effect=2.5,
                    hr_zones_method="max_heart_rate",
                    hrz_1_hr=100,
                    hrz_1_time=datetime.time(0, 5, 0),
                    hrz_2_hr=120,
                    hrz_2_time=datetime.time(0, 26, 0),
                ),
                _activity(
                    activity_id="1002",
                    name="Example Long Run",
                    start_time=NOW - datetime.timedelta(days=1),
                    elapsed_time=datetime.time(1, 40, 0),
                    moving_time=datetime.time(1, 35, 0),
                    distance=14.0,
                    ascent=300.0,
                    sport="running",
                ),
                _activity(
                    activity_id="1003",
                    name="Example Ride",
                    start_time=NOW - datetime.timedelta(days=1),
                    distance=30.0,
                    sport="cycling",
                ),
                _activity(
                    activity_id="1004",
                    name="Example Short Run",
                    start_time=NOW - datetime.timedelta(days=40),
                    elapsed_time=datetime.time(0, 30, 40),
                    moving_time=datetime.time(0, 29, 30),
                    distance=4.0,
                    sport="running",
                ),
                _activity(
                    activity_id="0999",
                    name="Example Old Run",
                    start_time=NOW - datetime.timedelta(days=60),
                    distance=5.0,
                    sport="running",
                ),
            ],
        )
        conn.execute(
            insert(health.activityRecords),
            [
                _row(
                    health.activityRecords,
                    activity_id="1001",
                    record=index,
                    timestamp=NOW - datetime.timedelta(days=2) + datetime.timedelta(seconds=10 * index),
                    position_lat=lat,
                    position_long=lng,
                    distance=0.03 * index,
                    altitude=100.0 + index,
                    hr=130 + index,
                    speed=10.8,
                    cadence=85,
                    temperature=20.0,
                ) for index, (lat, lng) in enumerate(TRACK)
            ] + [_row(health.activityRecords, activity_id="1001", record=len(TRACK), hr=140)],
        )
        conn.execute(
            insert(health.activityLaps),
            [
                _row(
                    health.activityLaps,
                    activity_id="1001",
                    lap=lap,
                    distance=3.0,
                    moving_time=datetime.time(0, 15, 30),
                    elapsed_time=datetime.time(0, 16, 5),
                    avg_hr=135 + lap,
                ) for lap in (1, 2)
            ],
        )
        conn.execute(
            insert(health.stepsActivities),
            [
                _row(
                    health.stepsActivities,
                    activity_id="1001",
                    steps=5000,
                    avg_pace=datetime.time(0, 5, 10),
                    avg_moving_pace=datetime.time(0, 5, 10),
                    max_pace=datetime.time(0, 0, 0),
                    avg_step_length=1200.0,
                    avg_ground_contact_time=datetime.time(0, 0, 0, 250000),
                )
            ],
        )
        conn.execute(
            insert(health.measures),
            [
                # Day 3: fat and muscle; day 3 again later the same day; day 1: fat only.
                {
                    "grpid": 1, "type": 6, "measured_at": _day(3), "value": 25.0
                },
                {
                    "grpid": 1, "type": 76, "measured_at": _day(3), "value": 35.0
                },
                {
                    "grpid": 2, "type": 6, "measured_at": _day(3, 20), "value": 24.0
                },
                {
                    "grpid": 3, "type": 6, "measured_at": _day(1), "value": 22.0
                },
                {
                    "grpid": 3, "type": 1, "measured_at": _day(1), "value": 70.0
                },
            ],
        )

    return sqlite
