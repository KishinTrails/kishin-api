"""
Tests for the health-sync reader (kishin_trails.health) and `kishin health …`.

The measurement database is replaced by an in-memory SQLite database. SQLite has
no schemas, so the engine maps every schema to none. All rows are made up.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

from kishin_trails import health
from kishin_trails.cli import app
from kishin_trails.utils import latLngToS2Cell

runner = CliRunner()

NOW = datetime.datetime.now()
TODAY = datetime.datetime.now(datetime.UTC).date()

# Two points in one level-16 cell, then one point about 300 m east.
TRACK = [(48.8566, 2.3522), (48.85661, 2.35221), (48.8566, 2.3562)]


def _activity(**fields) -> dict:
    """An activities row; columns not given are null."""
    return {column.name: None for column in health.activities.columns} | fields


def _day(offset: int, hour: int = 7) -> datetime.datetime:
    """A naive UTC timestamp ``offset`` days before today."""
    return datetime.datetime.combine(TODAY - datetime.timedelta(days=offset), datetime.time(hour))


@pytest.fixture
def engine(monkeypatch):
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
                    elapsed_time=datetime.time(0, 32, 10),
                    moving_time=datetime.time(0, 31, 0),
                    distance=6.0,
                    ascent=40.0,
                    sport="running",
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
                {
                    "activity_id": "1001", "record": index, "position_lat": lat, "position_long": lng
                } for index, (lat, lng) in enumerate(TRACK)
            ] + [{
                "activity_id": "1001", "record": len(TRACK), "position_lat": None, "position_long": None
            }],
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

    monkeypatch.setattr(health, "healthEngine", lambda url, prefix="": sqlite)
    return sqlite


def test_health_engine_requires_url():
    with pytest.raises(ValueError):
        health.healthEngine("")


def test_health_engine_prefix():
    engine = health.healthEngine("sqlite://", "health_")
    assert engine.get_execution_options()["schema_translate_map"]["withings"] == "health_withings"


def test_unit_system(engine):
    with engine.connect() as conn:
        assert health.unitSystem(conn) == "metric"


def test_statute_distance_in_km(engine):
    with engine.begin() as conn:
        conn.execute(health.attributes.update().values(value="DisplayMeasure.statute"))
    with engine.connect() as conn:
        activity = health.getActivity(conn, "1001")
    assert activity is not None
    assert activity.distance_km == pytest.approx(6.0 * 1.609344)


def test_recent_activities(engine):
    with engine.connect() as conn:
        rows = health.recentActivities(conn, NOW - datetime.timedelta(days=30), "running")
    assert [row.activity_id for row in rows] == ["1001", "1002"]
    assert rows[0].elapsed_sec == 32 * 60 + 10
    assert rows[0].moving_sec == 31 * 60
    assert rows[0].distance_km == 6.0


def test_activity_cells(engine):
    with engine.connect() as conn:
        cells = health.activityCells(conn, "1001")
    assert cells == [latLngToS2Cell(*TRACK[0]), latLngToS2Cell(*TRACK[2])]


def test_daily_measures_keeps_last_of_day(engine):
    with engine.connect() as conn:
        fat = health.dailyMeasures(conn, health.WITHINGS_TYPES["fat_ratio"])
    assert fat == [(TODAY - datetime.timedelta(days=3), 24.0), (TODAY - datetime.timedelta(days=1), 22.0)]


def test_cli_without_url(monkeypatch):
    monkeypatch.setattr("kishin_trails.cli.health.settings.HEALTH_DATABASE_URL", "")
    result = runner.invoke(app, ["health", "activities"])
    assert result.exit_code == 1
    assert "HEALTH_DATABASE_URL is not set" in result.output


def test_cli_activities(engine):
    result = runner.invoke(app, ["health", "activities", "--sport", "running"])
    assert result.exit_code == 0, result.output
    assert "1001" in result.output
    assert "14.00" in result.output
    assert "0999" not in result.output
    assert "1003" not in result.output


def test_cli_cells(engine):
    result = runner.invoke(app, ["health", "cells", "1001"])
    assert result.exit_code == 0, result.output
    assert "cells: 2" in result.output


def test_cli_cells_unknown_activity(engine):
    result = runner.invoke(app, ["health", "cells", "42"])
    assert result.exit_code == 1


def test_cli_measures(engine):
    result = runner.invoke(app, ["health", "measures", "--fat-alpha", "0.5"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert len(lines) == 3
    # Day 1: fat 22.0, EMA 0.5 × 22 + 0.5 × 24 = 23.0; muscle EMA carried from day 3.
    assert lines[2].split()[1:] == ["22.00", "23.00", "-", "35.00"]


def test_cli_multiplier(engine):
    start = (TODAY - datetime.timedelta(days=3)).isoformat()
    end = TODAY.isoformat()
    result = runner.invoke(
        app,
        [
            "health",
            "multiplier",
            "--start", start,
            "--end", end,
            "--fat-target", "20",
            "--w-fat", "1",
            "--decay", "0.1",
            "--fat-alpha", "1",
            "--base-cap", "100",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "fat_start: 24.00  muscle_start: 35.00"
    days = [line.split() for line in lines[2:]]
    assert len(days) == 4
    # Day 3 measured: progress 0, multiplier 1.0. Day 2: decay to 0.9.
    # Day 1 measured: fat 22, progress (24 - 22) / (24 - 20) = 0.5, target 1.25. Day 0: 1.125.
    assert [row[-2] for row in days] == ["1.000", "0.900", "1.250", "1.125"]
    assert days[-1][-1] == "112.5"


def test_cli_multiplier_needs_fat_start(engine):
    start = (TODAY - datetime.timedelta(days=10)).isoformat()
    result = runner.invoke(
        app,
        ["health", "multiplier", "--start", start, "--fat-target", "20", "--w-fat", "1", "--decay", "0.1"],
    )
    assert result.exit_code == 1
    assert "fat_start is undefined" in result.output


def test_cli_willpower_long_run(engine):
    result = runner.invoke(
        app,
        [
            "health", "willpower", "1002",
            "--type", "long", "--rpe", "6", "--partial-bonus", "1.2", "--target-km", "15",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "adherence bonus: 1.2" in result.output
    assert "willpower: 168.0" in result.output
    assert "complete: True" in result.output


def test_cli_willpower_fundamental_run(engine):
    result = runner.invoke(
        app,
        ["health", "willpower", "1001", "--type", "fundamental", "--rpe", "4", "--partial-bonus", "1.2"],
    )
    assert result.exit_code == 0, result.output
    assert "willpower: 90.0" in result.output
    assert "elapsed time: 0:32:10  complete: True" in result.output


def test_cli_willpower_rpe_below_bands(engine):
    result = runner.invoke(
        app,
        ["health", "willpower", "1001", "--type", "fundamental", "--rpe", "2", "--partial-bonus", "1.2"],
    )
    assert result.exit_code == 1
