"""
Tests for the plan routes (kishin_trails.plan), on the made-up health database
of tests/healthdata.py and the made-up plan of tests/plandata.py.

The plan starts on the Monday of activity 1002's week, so 1002 (14 km) is in
week 1. Week 1 asks for a 13 km long run and a 30-minute run.
"""

from __future__ import annotations

import datetime

import pytest
from httpx import AsyncClient

from kishin_trails.main import app
from kishin_trails.plan import optionalHealthConnection
from kishin_trails.plan_file import buildPlan
from kishin_trails.training import ActivePlan, Plan

from healthdata import NOW
from plandata import examplePlan

pytestmark = pytest.mark.asyncio

LONG_RUN_DAY = (NOW - datetime.timedelta(days=1)).date()
START = LONG_RUN_DAY - datetime.timedelta(days=LONG_RUN_DAY.weekday())


@pytest.fixture
def plan(db_session) -> Plan:
    """The example plan, active."""
    examplePlanRow = buildPlan(examplePlan())
    db_session.add(examplePlanRow)
    db_session.flush()
    db_session.add(ActivePlan(plan_id=examplePlanRow.id, start_date=START))
    db_session.commit()
    return examplePlanRow


def _training(plan: Plan, week: int, position: int) -> int:
    return next(t.id for t in plan.trainings if t.week_number == week and t.position == position)


async def test_no_active_plan(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/plan")
    assert response.status_code == 404


async def test_progression(authenticated_client: AsyncClient, health_engine, plan):
    response = await authenticated_client.get("/plan")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Example Plan"
    assert body["week_count"] == 2
    assert body["start_date"] == START.isoformat()
    assert body["health_available"] is True
    today = datetime.datetime.now(datetime.UTC).date()
    assert body["current_week"] == (today - START).days // 7 + 1

    week1 = body["weeks"][0]
    assert week1["phase"] == "BASE"
    assert week1["start"] == START.isoformat()
    assert week1["end"] == (START + datetime.timedelta(days=6)).isoformat()
    longRun, fundamental = week1["trainings"][:2]
    assert (longRun["type"], longRun["target_distance_km"], longRun["is_tick"]) == ("EXPLORATORY_LONG_RUN", 13, False)
    assert fundamental["target_duration_sec"] == 1800
    assert week1["trainings"][2]["is_tick"] is True
    assert all(training["completion"] is None for training in week1["trainings"])
    assert week1["running"]["longest_run_km"] == 14.0
    in1001 = START <= (NOW - datetime.timedelta(days=2)).date()
    assert week1["running"]["run_moving_sec"] == 95 * 60 + (31 * 60 if in1001 else 0)


async def test_progression_without_health(authenticated_client: AsyncClient, plan):
    def no_health():
        yield None

    app.dependency_overrides[optionalHealthConnection] = no_health
    response = await authenticated_client.get("/plan")
    assert response.status_code == 200
    assert response.json()["health_available"] is False
    assert response.json()["weeks"][0]["running"] is None


async def test_candidates(authenticated_client: AsyncClient, health_engine, plan):
    response = await authenticated_client.get(f"/plan/trainings/{_training(plan, 1, 1)}/candidates")
    assert response.status_code == 200
    ids = [activity["activity_id"] for activity in response.json()]
    assert "1002" in ids
    assert "1003" not in ids  # cycling
    expected1001 = START <= (NOW - datetime.timedelta(days=2)).date()
    assert ("1001" in ids) == expected1001


async def test_candidates_of_a_tick_item(authenticated_client: AsyncClient, health_engine, plan):
    response = await authenticated_client.get(f"/plan/trainings/{_training(plan, 1, 3)}/candidates")
    assert response.json() == []


async def test_complete_a_run(authenticated_client: AsyncClient, health_engine, plan):
    trainingId = _training(plan, 1, 1)
    response = await authenticated_client.post(
        f"/plan/trainings/{trainingId}/complete", json={"activity_id": "1002", "rpe": 4}
    )
    assert response.status_code == 201, response.json()
    completion = response.json()["completion"]
    assert completion["rpe"] == 4
    assert completion["activity"]["distance_km"] == 14.0
    assert completion["activity"]["name"] == "Example Long Run"

    candidates = await authenticated_client.get(f"/plan/trainings/{_training(plan, 1, 2)}/candidates")
    assert "1002" not in [activity["activity_id"] for activity in candidates.json()]

    progression = (await authenticated_client.get("/plan")).json()
    assert progression["weeks"][0]["trainings"][0]["completion"]["rpe"] == 4


async def test_complete_a_tick_item_and_undo(authenticated_client: AsyncClient, health_engine, plan):
    trainingId = _training(plan, 1, 5)
    response = await authenticated_client.post(f"/plan/trainings/{trainingId}/complete", json={})
    assert response.status_code == 201
    assert response.json()["completion"]["activity"] is None

    again = await authenticated_client.post(f"/plan/trainings/{trainingId}/complete", json={})
    assert again.status_code == 409

    undo = await authenticated_client.delete(f"/plan/trainings/{trainingId}/complete")
    assert undo.status_code == 204
    assert (await authenticated_client.delete(f"/plan/trainings/{trainingId}/complete")).status_code == 404


@pytest.mark.parametrize(
    ("position", "body", "status", "detail"),
    [
        (1, {"activity_id": "1002"}, 422, "A run needs an activity and an RPE."),
        (1, {"activity_id": "42", "rpe": 4}, 404, "Activity not found."),
        (3, {"activity_id": "1002", "rpe": 4}, 422, "A tick item takes no activity and no RPE."),
    ],
)
async def test_completion_refused(authenticated_client: AsyncClient, health_engine, plan, position, body, status, detail):
    response = await authenticated_client.post(f"/plan/trainings/{_training(plan, 1, position)}/complete", json=body)
    assert response.status_code == status
    assert detail in response.json()["detail"]


async def test_rpe_out_of_range(authenticated_client: AsyncClient, health_engine, plan):
    response = await authenticated_client.post(
        f"/plan/trainings/{_training(plan, 1, 1)}/complete", json={"activity_id": "1002", "rpe": 11}
    )
    assert response.status_code == 422


@pytest.mark.parametrize(("position", "activityId"), [(1, "1001"), (2, "1004")])
async def test_any_run_completes_a_run(authenticated_client: AsyncClient, health_engine, plan, position, activityId):
    """Activity 1001 is shorter than the 13 km target and 1004 shorter than the 30 min target."""
    response = await authenticated_client.post(
        f"/plan/trainings/{_training(plan, 1, position)}/complete", json={"activity_id": activityId, "rpe": 3}
    )
    assert response.status_code == 201


async def test_one_activity_completes_one_training(authenticated_client: AsyncClient, health_engine, plan):
    first = await authenticated_client.post(
        f"/plan/trainings/{_training(plan, 1, 1)}/complete", json={"activity_id": "1002", "rpe": 4}
    )
    assert first.status_code == 201
    second = await authenticated_client.post(
        f"/plan/trainings/{_training(plan, 2, 1)}/complete", json={"activity_id": "1002", "rpe": 4}
    )
    assert second.status_code == 409


async def test_unknown_training(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.post("/plan/trainings/42/complete", json={})
    assert response.status_code == 404
