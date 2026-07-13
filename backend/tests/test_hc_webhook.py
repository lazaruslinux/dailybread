"""The Android fitness dialect: HC Webhook payloads on the same ingest
endpoint. UTC times land on the FAMILY's clock; the Apple path is untouched."""

import datetime as dt

import pytest

from app.routers import fitness

TODAY = dt.date.today()


@pytest.fixture(autouse=True)
def _hc_enabled(monkeypatch):
    """Pin the switch on: these tests must keep exercising the dialect even
    if it's ever parked again (it shipped parked 2026-07-10 to -11)."""
    monkeypatch.setattr(fitness, "HC_INGEST_ENABLED", True)


def _mint(client) -> str:
    res = client.post("/me/fitness/token")
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _send(client, token, payload):
    return client.post(
        "/ingest/health", json=payload, headers={"Authorization": f"Bearer {token}"}
    )


def _utc(day: dt.date, hh: int, mm: int = 0) -> str:
    return f"{day.isoformat()}T{hh:02d}:{mm:02d}:00.000Z"


def _payload(day: dt.date = TODAY) -> dict:
    """A representative HC Webhook body, per its docs/webhook.md shapes.
    Times sit mid-day UTC so server-timezone drift can't move the date."""
    return {
        "timestamp": _utc(day, 12),
        "app_version": "1.4.0",
        "steps": [
            {"count": 4200, "start_time": _utc(day, 9), "end_time": _utc(day, 10)},
            {"count": 3800, "start_time": _utc(day, 15), "end_time": _utc(day, 16)},
        ],
        "active_calories": [
            {"calories": 512.5, "start_time": _utc(day, 12), "end_time": _utc(day, 13)},
        ],
        "resting_heart_rate": [
            {"bpm": 58, "time": _utc(day, 8)},
            {"bpm": 62, "time": _utc(day, 14)},
        ],
        "exercise_sessions": [
            {
                "type": "running",
                "start_time": _utc(day, 13),
                "end_time": _utc(day, 13, 34),
                "duration_seconds": 2040,
                "distance_meters": 5100,
            }
        ],
        "weight": [{"kilograms": 90.7, "time": _utc(day, 7)}],
        "body_fat": [{"percentage": 23.4, "time": _utc(day, 7)}],
    }


def test_hc_payload_lands_on_the_fitness_tab(owner):
    token = _mint(owner)
    res = _send(owner, token, _payload())
    assert res.status_code == 200, res.text
    body = owner.get(f"/me/fitness?date={TODAY.isoformat()}").json()
    assert body["today"]["steps"] == 8000
    assert body["today"]["active_kcal"] == 512.5
    assert body["today"]["resting_hr"] == 60
    assert body["today"]["exercise_minutes"] == 34
    assert len(body["workouts"]) == 1
    w = body["workouts"][0]
    assert w["activity"] == "Running"
    assert w["distance_m"] == 5100
    assert w["route"] is None
    assert w["source"] == "android"


def test_hc_daily_distance_lands_in_meters(owner):
    token = _mint(owner)
    payload = {
        "app_version": "1.4.0",
        "distance": [
            {"distance_meters": 1500, "start_time": _utc(TODAY, 9)},
            {"distance_meters": 2500, "start_time": _utc(TODAY, 15)},
        ],
    }
    assert _send(owner, token, payload).status_code == 200
    body = owner.get(f"/me/fitness?date={TODAY.isoformat()}").json()
    assert body["today"]["distance"] == 4000


def test_hc_weight_and_body_fat_join_the_weight_log(owner):
    token = _mint(owner)
    _send(owner, token, _payload())
    weights = owner.get("/me/health").json()["weights"]
    row = next(w for w in weights if w["date_for"] == TODAY.isoformat())
    assert row["weight_kg"] == 90.7
    assert row["body_fat_pct"] == 23.4


def test_hc_resends_never_duplicate(owner):
    token = _mint(owner)
    _send(owner, token, _payload())
    _send(owner, token, _payload())
    body = owner.get(f"/me/fitness?date={TODAY.isoformat()}").json()
    assert body["today"]["steps"] == 8000
    assert len(body["workouts"]) == 1


def test_hc_times_land_on_the_familys_clock(owner):
    """03:00 UTC is the previous evening in Phoenix: the steps must file
    under the family-local day, not the UTC one."""
    res = owner.patch("/families/me", json={"name": "Home", "timezone": "America/Phoenix"})
    assert res.status_code == 200, res.text
    token = _mint(owner)
    payload = {
        "app_version": "1.4.0",
        "steps": [{"count": 1000, "start_time": _utc(TODAY, 3), "end_time": _utc(TODAY, 4)}],
    }
    assert _send(owner, token, payload).status_code == 200
    phoenix_day = (TODAY - dt.timedelta(days=1)).isoformat()
    week = owner.get(f"/me/fitness?date={TODAY.isoformat()}").json()["week"]
    by_day = {d["date_for"]: d["steps"] for d in week}
    assert by_day[phoenix_day] == 1000
    assert by_day[TODAY.isoformat()] is None


def test_hc_workouts_check_off_opted_in_routines(owner):
    res = owner.post(
        "/items",
        json={
            "kind": "routine",
            "title": "Morning run",
            "repeat": {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
            "workout_auto_complete": True,
        },
    )
    assert res.status_code == 201
    token = _mint(owner)
    out = _send(owner, token, _payload()).json()
    assert out["routines_completed"] == 1


def test_malformed_hc_payloads_are_survived(owner):
    token = _mint(owner)
    res = _send(
        owner,
        token,
        {
            "app_version": "1.4.0",
            "steps": ["junk", {"count": "x", "start_time": 5}, {"count": 10}],
            "exercise_sessions": [{"type": 42}, "junk"],
            "weight": [{"kilograms": None}],
        },
    )
    assert res.status_code == 200
    assert res.json() == {"days": 0, "workouts": 0, "routines_completed": 0}
