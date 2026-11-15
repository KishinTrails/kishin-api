"""
Tests for reading plan files (kishin_trails.plan_file).
"""

import json

import pytest

from kishin_trails.plan_file import PlanFileError, buildPlan, readPlanFile
from kishin_trails.training_types import SegmentType, TrainingType, WeekPhase

from plandata import examplePlan


def test_build_plan():
    plan = buildPlan(examplePlan())
    assert plan.name == "Example Plan"
    assert plan.target_fat_ratio == 20.0
    assert [(week.week_number, week.phase) for week in plan.weeks] == [(1, WeekPhase.BASE), (2, WeekPhase.RECOVERY)]
    assert len(plan.trainings) == 14
    longRun = plan.trainings[0]
    assert (longRun.week_number, longRun.position, longRun.training_type) == (1, 1, TrainingType.EXPLORATORY_LONG_RUN)
    assert longRun.segments[0].target_distance_km == 13
    assert (longRun.segments[0].target_rpe_min, longRun.segments[0].target_rpe_max) == (3, 5)
    assert plan.trainings[1].segments[0].duration_sec == 1800
    assert plan.trainings[1].segments[0].segment_type is SegmentType.EASY
    assert plan.trainings[-1].position == 7


def test_read_plan_file(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(examplePlan()))
    assert readPlanFile(path).name == "Example Plan"


def test_not_json(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("{")
    with pytest.raises(PlanFileError, match="is not JSON"):
        readPlanFile(path)


def test_missing_file(tmp_path):
    with pytest.raises(PlanFileError, match="cannot read"):
        readPlanFile(tmp_path / "missing.json")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda data: data.pop("name"), "name: Field required"),
        (lambda data: data.update(weeks=[]), "weeks: List should have at least 1 item"),
        (lambda data: data["weeks"][0].update(phase="TAPER"), "weeks.0.phase"),
        (lambda data: data["weeks"][0]["trainings"][0].update(type="SPRINT"), "weeks.0.trainings.0.type"),
        (lambda data: data.update(extra=1), "extra: Extra inputs are not permitted"),
        (
            lambda data: data["weeks"][0]["trainings"][0]["segments"][0].update(duration_min=30),
            "exactly one of distance_km and duration_min",
        ),
        (lambda data: data["weeks"][0]["trainings"][0]["segments"][0].update(rpe=[6, 5]), "rpe must be"),
    ],
)
def test_format_errors(change, message):
    data = examplePlan()
    change(data)
    with pytest.raises(PlanFileError) as error:
        buildPlan(data)
    assert any(message in problem for problem in error.value.problems), error.value.problems


def test_plan_rules():
    data = examplePlan()
    data["weeks"][1]["trainings"].pop()
    data["weeks"][0]["trainings"][2]["segments"] = [{"type": "EASY", "duration_min": 20}]
    with pytest.raises(PlanFileError) as error:
        buildPlan(data)
    assert error.value.problems == [
        "week 1 position 3 (CROSS_TRAINING): a tick item has segments",
        "week 2: 2 YOGA, expected 3",
    ]
