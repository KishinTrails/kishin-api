"""
Tests for the `kishin` CLI: `kishin password`, `kishin gpx import` and
`kishin db drop-legacy-tables`.
"""

from __future__ import annotations

import stat
from typing import Callable

import pytest
from sqlalchemy import inspect, select, text
from typer.testing import CliRunner

from kishin_trails.cli import app
from kishin_trails.cli.common import MIN_PASSWORD_LENGTH
from kishin_trails.models import ExploredTile, Tile
from kishin_trails.security import verifyPassword

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


# --- db drop-legacy-tables ---------------------------------------------------------


def _createLegacyTables(db_session) -> None:
    """The multi-account tables, as an older version created them, with one row each."""
    db_session.execute(text("DROP TABLE plans"))
    for statement in (
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR, hashed_password VARCHAR)",
        "CREATE TABLE user_explored_tiles (user_id INTEGER, tile_s2_cell_id VARCHAR)",
        "CREATE TABLE user_active_plans (user_id INTEGER PRIMARY KEY, plan_id INTEGER, start_date DATE)",
        "CREATE TABLE plans (id INTEGER PRIMARY KEY, name VARCHAR, goal_type VARCHAR, owner_id INTEGER, "
        "target_fat_ratio FLOAT, target_muscle_mass_kg FLOAT)",
        "INSERT INTO users VALUES (1, 'foo', 'hash')",
        "INSERT INTO user_explored_tiles VALUES (1, '89c25a221')",
    ):
        db_session.execute(text(statement))
    db_session.commit()


def test_drop_legacy_tables_keeps_tiles(db_session):
    db_session.add(Tile(s2_cell_id="89c25a221", tile_type="peak"))
    db_session.commit()
    _createLegacyTables(db_session)

    result = runner.invoke(app, ["db", "drop-legacy-tables", "--yes"])
    assert result.exit_code == 0, result.output

    inspector = inspect(db_session.get_bind())
    tables = set(inspector.get_table_names())
    assert not {"users", "user_explored_tiles", "user_active_plans"} & tables
    assert "owner_id" not in {column["name"] for column in inspector.get_columns("plans")}
    assert "active_plan" in tables
    assert db_session.scalars(select(Tile.s2_cell_id)).all() == ["89c25a221"]


def test_drop_legacy_tables_keeps_current_plan_tables(db_session):
    result = runner.invoke(app, ["db", "drop-legacy-tables", "--yes"])
    assert result.exit_code == 0, result.output
    assert "No legacy tables." in result.output
