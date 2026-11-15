"""
Tests for the `kishin` CLI: `kishin password`, `kishin gpx import` and
`kishin db copy-from-sqlite`.
"""

from __future__ import annotations

import datetime
import stat
from typing import Callable

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from kishin_trails.cli import app
from kishin_trails.cli.common import MIN_PASSWORD_LENGTH
from kishin_trails.database import Base
from kishin_trails.models import POI, ExploredTile, NoiseCache, Tile
from kishin_trails.plan_file import buildPlan
from kishin_trails.training import ACTIVE_PLAN_ID, ActivePlan, Plan
from kishin_trails.security import verifyPassword

from plandata import examplePlan

runner = CliRunner()

PASSWORD = "a-good-password"


@pytest.fixture
def invokeGpx(db_session) -> Callable[..., object]:
    """Runs `kishin gpx …` against the test database."""
    def run(*args: str, **kwargs):
        return runner.invoke(app, ["gpx", *args], **kwargs)

    return run


@pytest.fixture
def gpxFile(tmp_path) -> str:
    """A minimal two-point GPX track, written fresh so the test owns it.

    *.gpx is gitignored (real activity files are personal hiking data, not
    repo content), so a fixture file checked into the repo is not an option.
    """
    path = tmp_path / "track.gpx"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">\n'
        "  <trk><trkseg>\n"
        '    <trkpt lat="48.855421" lon="2.345939"></trkpt>\n'
        '    <trkpt lat="48.856421" lon="2.346939"></trkpt>\n'
        "  </trkseg></trk>\n"
        "</gpx>\n"
    )
    return str(path)


# --- password --------------------------------------------------------------------


def test_password_writes_a_hash_readable_by_its_owner_only(tmp_path):
    hashFile = tmp_path / "KISHIN_PASSWORD_HASH"
    result = runner.invoke(app, ["password", str(hashFile)], input=f"{PASSWORD}\n{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    assert verifyPassword(PASSWORD, hashFile.read_text())
    assert stat.S_IMODE(hashFile.stat().st_mode) == 0o600
    assert PASSWORD not in result.output.replace(PASSWORD + "\n", "")


def test_password_tightens_the_mode_of_an_existing_file(tmp_path):
    hashFile = tmp_path / "KISHIN_PASSWORD_HASH"
    hashFile.write_text("old")
    hashFile.chmod(0o644)
    result = runner.invoke(app, ["password", str(hashFile)], input=f"{PASSWORD}\n{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(hashFile.stat().st_mode) == 0o600


def test_password_too_short_writes_nothing(tmp_path):
    hashFile = tmp_path / "KISHIN_PASSWORD_HASH"
    result = runner.invoke(app, ["password", str(hashFile)], input="abc\nabc\n")
    assert result.exit_code == 1
    assert not hashFile.exists()


def test_password_length_limit(tmp_path):
    hashFile = tmp_path / "KISHIN_PASSWORD_HASH"
    tooShort = "x" * (MIN_PASSWORD_LENGTH - 1)
    assert runner.invoke(app, ["password", str(hashFile)], input=f"{tooShort}\n{tooShort}\n").exit_code == 1
    assert not hashFile.exists()
    longEnough = "x" * MIN_PASSWORD_LENGTH
    assert runner.invoke(app, ["password", str(hashFile)], input=f"{longEnough}\n{longEnough}\n").exit_code == 0
    assert verifyPassword(longEnough, hashFile.read_text())


def test_password_in_a_missing_directory_fails(tmp_path):
    result = runner.invoke(app, ["password", str(tmp_path / "missing" / "hash")])
    assert result.exit_code == 1


# --- gpx import ------------------------------------------------------------------


def test_gpx_import_marks_the_track_explored(invokeGpx, db_session, gpxFile):
    result = invokeGpx("import", gpxFile)
    assert result.exit_code == 0, result.output
    explored = set(db_session.scalars(select(ExploredTile.s2_cell_id)))
    assert explored
    assert explored == set(db_session.scalars(select(Tile.s2_cell_id)))

    again = invokeGpx("import", gpxFile)
    assert again.exit_code == 0, again.output
    assert set(db_session.scalars(select(ExploredTile.s2_cell_id))) == explored


def test_gpx_import_dry_run_writes_nothing(invokeGpx, db_session, gpxFile):
    result = invokeGpx("import", gpxFile, "--dry-run")
    assert result.exit_code == 0, result.output
    assert db_session.scalars(select(ExploredTile)).all() == []


# --- db copy-from-sqlite -----------------------------------------------------------


@pytest.fixture
def sqliteFile(tmp_path):
    """A kishin.db as the SQLite version wrote it: every current table, a few rows, and an
    old ``users`` table."""
    path = tmp_path / "kishin.db"
    source = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(source)
    with Session(source) as session:
        session.add(Tile(s2_cell_id="89c25a221", tile_type="peak", active=True))
        session.add(Tile(s2_cell_id="89c25a223", tile_type="natural", active=False))
        session.flush()
        session.add(POI(s2_cell_id="89c25a221", osm_id=BIG_OSM_ID, name="Example Peak", lat=48.85, lon=2.35))
        session.add(ExploredTile(s2_cell_id="89c25a221"))
        session.add(NoiseCache(s2_cell_id="89c25a221", scale=50, octaves=3, amplitude_decay=0.5, noise_value=0.7))
        plan = buildPlan(examplePlan())
        session.add(plan)
        session.flush()
        session.add(ActivePlan(id=ACTIVE_PLAN_ID, plan_id=plan.id, start_date=datetime.date(2026, 1, 5)))
        session.commit()
    with source.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR)"))
    source.dispose()
    return path


#: An OpenStreetMap id above 2^31, which a PostgreSQL INTEGER cannot hold.
BIG_OSM_ID = 11_000_000_000


def test_copy_from_sqlite(db_session, sqliteFile):
    result = runner.invoke(app, ["db", "copy-from-sqlite", str(sqliteFile)])
    assert result.exit_code == 0, result.output

    tiles = {tile.s2_cell_id: tile.active for tile in db_session.scalars(select(Tile))}
    assert tiles == {"89c25a221": True, "89c25a223": False}
    assert db_session.scalars(select(POI.osm_id)).all() == [BIG_OSM_ID]
    assert db_session.scalars(select(ExploredTile.s2_cell_id)).all() == ["89c25a221"]
    assert db_session.scalar(select(NoiseCache.noise_value)) == 0.7
    active = db_session.get(ActivePlan, ACTIVE_PLAN_ID)
    assert active.start_date == datetime.date(2026, 1, 5)
    assert active.plan.name == "Example Plan"
    assert len(active.plan.trainings) == 14


def test_copy_from_sqlite_moves_the_id_sequences(db_session, sqliteFile):
    runner.invoke(app, ["db", "copy-from-sqlite", str(sqliteFile)])
    copiedId = db_session.scalar(select(Plan.id))
    newPlan = buildPlan(examplePlan())
    db_session.add(newPlan)
    db_session.commit()
    assert newPlan.id == copiedId + 1


def test_copy_from_sqlite_skips_missing_tables(db_session, sqliteFile):
    with create_engine(f"sqlite:///{sqliteFile}").begin() as conn:
        conn.execute(text("DROP TABLE active_plan"))
    result = runner.invoke(app, ["db", "copy-from-sqlite", str(sqliteFile)])
    assert result.exit_code == 0, result.output
    assert "active_plan" in result.output and "not in the file, skipped" in result.output
    assert db_session.get(ActivePlan, ACTIVE_PLAN_ID) is None


def test_copy_from_sqlite_refuses_filled_tables(db_session, sqliteFile):
    db_session.add(Tile(s2_cell_id="89c25a225", tile_type="peak"))
    db_session.commit()
    result = runner.invoke(app, ["db", "copy-from-sqlite", str(sqliteFile)])
    assert result.exit_code == 1
    assert "already hold rows: tiles" in result.output
    assert db_session.scalars(select(Tile.s2_cell_id)).all() == ["89c25a225"]
