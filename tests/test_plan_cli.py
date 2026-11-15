"""
Tests for `kishin plan …`.
"""

from __future__ import annotations

import datetime
import json

import pytest
from typer.testing import CliRunner

from kishin_trails.cli import app
from kishin_trails.database import Base
from kishin_trails.training import ACTIVE_PLAN_ID, ActivePlan, Plan, TrainingCompletion

from plandata import examplePlan

runner = CliRunner()

MONDAY = "2026-01-05"


@pytest.fixture
def planFile(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(examplePlan()))
    return path


def _import(path, *extra):
    return runner.invoke(app, ["plan", "import", str(path), "--start", MONDAY, *extra])


def test_import_makes_the_plan_active(db_session, planFile):
    result = _import(planFile)
    assert result.exit_code == 0, result.output
    assert "is the active plan, starting 2026-01-05" in result.output
    active = db_session.get(ActivePlan, ACTIVE_PLAN_ID)
    assert active.plan.name == "Example Plan"
    assert str(active.start_date) == MONDAY


def test_second_import_replaces_the_active_plan(db_session, planFile):
    _import(planFile)
    result = runner.invoke(app, ["plan", "import", str(planFile), "--start", "2026-01-12"])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    assert db_session.query(Plan).count() == 2
    active = db_session.get(ActivePlan, ACTIVE_PLAN_ID)
    assert str(active.start_date) == "2026-01-12"
    assert active.plan_id == max(plan.id for plan in db_session.query(Plan))


def test_import_refuses_a_day_that_is_not_monday(db_session, planFile):
    result = runner.invoke(app, ["plan", "import", str(planFile), "--start", "2026-01-06"])
    assert result.exit_code == 1
    assert "is not a Monday" in result.output


def test_import_reports_file_problems(db_session, tmp_path):
    data = examplePlan()
    data["weeks"][0]["trainings"].pop()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(data))
    result = _import(path)
    assert result.exit_code == 1
    assert "week 1: 2 YOGA, expected 3" in result.output
    assert db_session.query(Plan).count() == 0


def test_list_and_show(db_session, planFile):
    _import(planFile)
    listed = runner.invoke(app, ["plan", "list"])
    assert listed.exit_code == 0
    assert "Example Plan  (2 weeks, 0/14 done)" in listed.output
    assert listed.output.startswith("*")

    shown = runner.invoke(app, ["plan", "show"])
    assert shown.exit_code == 0, shown.output
    assert "week 1  BASE  2026-01-05" in shown.output
    assert "[ ] 1. EXPLORATORY_LONG_RUN 13 km" in shown.output
    assert "[ ] 2. FUNDAMENTAL_RUN 30 min" in shown.output


def test_delete(db_session, planFile):
    _import(planFile)
    plan = db_session.query(Plan).one()
    plan.trainings[2].completion = TrainingCompletion(completed_at=datetime.datetime(2026, 1, 6, 18, 0))
    db_session.commit()

    result = runner.invoke(app, ["plan", "delete", str(plan.id), "--yes"])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    assert db_session.query(Plan).count() == 0
    assert db_session.query(TrainingCompletion).count() == 0
    assert db_session.get(ActivePlan, ACTIVE_PLAN_ID) is None


def test_delete_unknown_plan(db_session):
    assert runner.invoke(app, ["plan", "delete", "42", "--yes"]).exit_code == 1


def test_commands_create_missing_tables(db_session, planFile):
    for name in ("training_completions", "active_plan"):
        Base.metadata.tables[name].drop(bind=db_session.get_bind())
    result = _import(planFile)
    assert result.exit_code == 0, result.output
    assert db_session.get(ActivePlan, ACTIVE_PLAN_ID) is not None
