"""
Tests for the read-only athlete routes (kishin_trails.athlete), on the made-up
health database of tests/healthdata.py.
"""

from __future__ import annotations

import datetime

import pytest
from httpx import AsyncClient

from kishin_trails import health
from kishin_trails.config import settings

from healthdata import NOW, TODAY, TRACK

pytestmark = pytest.mark.asyncio


async def test_requires_login(client: AsyncClient, health_engine):
    response = await client.get("/athlete/activities")
    assert response.status_code == 401


async def test_not_configured(authenticated_client: AsyncClient, monkeypatch):
    health.sharedHealthEngine.cache_clear()
    monkeypatch.setattr(settings, "HEALTH_DATABASE_URL", "")
    response = await authenticated_client.get("/athlete/activities")
    health.sharedHealthEngine.cache_clear()
    assert response.status_code == 503


async def test_list_activities(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities")
    assert response.status_code == 200
    rows = response.json()
    assert [row["activity_id"] for row in rows][:2] in (["1002", "1003"], ["1003", "1002"])
    assert rows[-1]["activity_id"] == "0999"
    run = next(row for row in rows if row["activity_id"] == "1001")
    assert run["distance_km"] == 6.0
    assert run["moving_sec"] == 31 * 60
    assert run["avg_speed_kmh"] == pytest.approx(6.0 / (31 / 60))
    assert run["descent_m"] == 35.0


async def test_list_activities_filters(authenticated_client: AsyncClient, health_engine):
    start = (NOW - datetime.timedelta(days=45)).date().isoformat()
    response = await authenticated_client.get(
        "/athlete/activities", params={"sport": "running", "start": start, "limit": 2, "offset": 1}
    )
    assert response.status_code == 200
    assert [row["activity_id"] for row in response.json()] == ["1001", "1004"]


async def test_list_activities_bad_range(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities", params={"start": "2026-02-01", "end": "2026-01-01"})
    assert response.status_code == 400


async def test_daily(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities/daily", params={"sport": "running"})
    assert response.status_code == 200
    days = {row["date"]: row for row in response.json()}
    day = (NOW - datetime.timedelta(days=2)).date().isoformat()
    assert days[day] == {
        "date": day, "count": 1, "distance_km": 6.0, "moving_sec": 31 * 60, "elapsed_sec": 32 * 60 + 10, "ascent_m": 40.0
    }
    assert len(days) == 4


async def test_daily_groups_one_day(authenticated_client: AsyncClient, health_engine):
    day = (NOW - datetime.timedelta(days=1)).date().isoformat()
    response = await authenticated_client.get("/athlete/activities/daily", params={"start": day, "end": day})
    assert response.status_code == 200
    assert response.json() == [
        {
            "date": day, "count": 2, "distance_km": 44.0, "moving_sec": 95 * 60, "elapsed_sec": 100 * 60, "ascent_m": 300.0
        }
    ]


async def test_detail(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities/1001")
    assert response.status_code == 200
    detail = response.json()
    assert detail["name"] == "Example Run"
    assert detail["lap_count"] == 2
    assert detail["hr_zones"][:2] == [{"zone": 1, "hr": 100, "time_sec": 300}, {"zone": 2, "hr": 120, "time_sec": 1560}]
    assert detail["running"]["steps"] == 5000
    assert detail["running"]["avg_pace_sec_per_km"] == 310
    assert detail["running"]["max_pace_sec_per_km"] is None
    assert detail["running"]["avg_ground_contact_time_ms"] == 250
    assert [lap["lap"] for lap in detail["laps"]] == [1, 2]
    assert detail["laps"][0]["avg_speed_kmh"] == pytest.approx(3.0 / (15.5 / 60))


async def test_detail_without_running_details(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities/1003")
    assert response.status_code == 200
    assert response.json()["running"] is None
    assert response.json()["laps"] == []


@pytest.mark.parametrize("suffix", ["", "/track", "/records"])
async def test_unknown_activity(authenticated_client: AsyncClient, health_engine, suffix):
    response = await authenticated_client.get(f"/athlete/activities/42{suffix}")
    assert response.status_code == 404


async def test_track(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities/1001/track")
    assert response.status_code == 200
    track = response.json()
    assert track["type"] == "Feature"
    assert track["geometry"] == {"type": "LineString", "coordinates": [[lng, lat] for lat, lng in TRACK]}
    assert track["properties"] == {"activity_id": "1001", "points": 3}
    lats = [lat for lat, _ in TRACK]
    lngs = [lng for _, lng in TRACK]
    assert track["bbox"] == [min(lngs), min(lats), max(lngs), max(lats)]


async def test_track_without_positions(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities/1003/track")
    assert response.status_code == 200
    assert response.json()["geometry"]["coordinates"] == []
    assert response.json()["bbox"] is None


async def test_records(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/activities/1001/records")
    assert response.status_code == 200
    records = response.json()
    assert records["hr"] == [130, 131, 132, 140]
    assert records["elapsed_sec"][:3] == [0, 10, 20]
    assert records["elapsed_sec"][3] is None
    assert records["altitude_m"] == [100.0, 101.0, 102.0, None]
    assert records["lat"][3] is None
    assert len({len(values) for key, values in records.items() if key != "activity_id"}) == 1


async def test_statute_units(authenticated_client: AsyncClient, health_engine):
    with health_engine.begin() as conn:
        conn.execute(health.attributes.update().values(value="DisplayMeasure.statute"))
    detail = (await authenticated_client.get("/athlete/activities/1001")).json()
    assert detail["distance_km"] == pytest.approx(6.0 * health.KM_PER_MILE)
    assert detail["ascent_m"] == pytest.approx(40.0 * health.M_PER_FOOT)
    assert detail["running"]["avg_pace_sec_per_km"] == pytest.approx(310 / health.KM_PER_MILE)
    records = (await authenticated_client.get("/athlete/activities/1001/records")).json()
    assert records["temperature_c"][0] == pytest.approx((20.0 - 32) * 5 / 9)
    assert records["speed_kmh"][0] == pytest.approx(10.8 * health.KM_PER_MILE)


async def test_measures(authenticated_client: AsyncClient, health_engine):
    response = await authenticated_client.get("/athlete/measures")
    assert response.status_code == 200
    days = response.json()
    assert [day["date"] for day in days] == [
        (TODAY - datetime.timedelta(days=3)).isoformat(), (TODAY - datetime.timedelta(days=1)).isoformat()
    ]
    first, last = days
    assert first["fat_ratio_pct"] == 24.0
    assert first["muscle_mass_kg"] == 35.0
    assert last["weight_kg"] == 70.0
    assert last["muscle_mass_kg"] is None
    assert last["muscle_mass_ema"] == 35.0
    # Fat EMA with alpha 0.30: 24, then 0.3 × 22 + 0.7 × 24.
    assert last["fat_ratio_ema"] == pytest.approx(23.4)


async def test_measures_range_keeps_history_in_average(authenticated_client: AsyncClient, health_engine):
    day = (TODAY - datetime.timedelta(days=1)).isoformat()
    response = await authenticated_client.get("/athlete/measures", params={"start": day, "end": day})
    assert response.status_code == 200
    assert [row["date"] for row in response.json()] == [day]
    assert response.json()[0]["fat_ratio_ema"] == pytest.approx(23.4)
