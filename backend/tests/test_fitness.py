"""The fitness layer: ingest tokens, the Apple Health import, and /me/fitness.

The ingest endpoint speaks Health Auto Export's documented JSON and
authenticates with a bearer token, never cookies. All imported data is
self-only; minors have no fitness area at all. Imports are idempotent, so
the exporter can resend whole windows forever.
"""

import datetime as dt

TODAY = dt.date.today()
YESTERDAY = TODAY - dt.timedelta(days=1)


def _stamp(day: dt.date, hhmmss: str) -> str:
    return f"{day.isoformat()} {hhmmss} -0700"


def _payload(day: dt.date = TODAY) -> dict:
    return {
        "data": {
            "metrics": [
                {
                    "name": "step_count",
                    "units": "count",
                    "data": [
                        {"date": _stamp(day, "09:00:00"), "qty": 4200},
                        {"date": _stamp(day, "18:00:00"), "qty": 3800},
                    ],
                },
                {
                    "name": "active_energy",
                    "units": "kcal",
                    "data": [{"date": _stamp(day, "20:00:00"), "qty": 512.5}],
                },
                {
                    "name": "apple_exercise_time",
                    "units": "min",
                    "data": [{"date": _stamp(day, "20:00:00"), "qty": 34}],
                },
                {
                    "name": "resting_heart_rate",
                    "units": "count/min",
                    "data": [
                        {"date": _stamp(day, "08:00:00"), "qty": 58},
                        {"date": _stamp(day, "22:00:00"), "qty": 62},
                    ],
                },
                {
                    "name": "weight_body_mass",
                    "units": "lb",
                    "data": [{"date": _stamp(day, "07:00:00"), "qty": 200.0}],
                },
                {
                    "name": "mindful_minutes",  # untracked: silently ignored
                    "units": "min",
                    "data": [{"date": _stamp(day, "07:00:00"), "qty": 10}],
                },
            ],
            "workouts": [
                {
                    "id": "workout-abc-123",
                    "name": "Outdoor Run",
                    "start": _stamp(day, "06:30:00"),
                    "end": _stamp(day, "07:05:00"),
                    "duration": 2100,
                    "activeEnergyBurned": {"qty": 320.0, "units": "kcal"},
                    "distance": {"qty": 5.2, "units": "km"},
                    "heartRate": {"min": {"qty": 95}, "avg": {"qty": 142}, "max": {"qty": 171}},
                }
            ],
        }
    }


def _mint(client) -> str:
    res = client.post("/me/fitness/token")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["path"] == "/api/ingest/health"
    return body["token"]


def _send(client, token, payload):
    return client.post(
        "/ingest/health", json=payload, headers={"Authorization": f"Bearer {token}"}
    )


# ---- tokens ----------------------------------------------------------------------


def test_minors_have_no_fitness_area(child):
    assert child.post("/me/fitness/token").status_code == 403
    assert child.get("/me/fitness").status_code == 403
    assert child.delete("/me/fitness/token").status_code == 403


def test_reminting_replaces_the_old_token(owner):
    first = _mint(owner)
    second = _mint(owner)
    assert _send(owner, first, _payload()).status_code == 401
    assert _send(owner, second, _payload()).status_code == 200


def test_a_revoked_token_stops_working(owner):
    token = _mint(owner)
    assert owner.delete("/me/fitness/token").status_code == 204
    assert _send(owner, token, _payload()).status_code == 401
    # /me/fitness reports the disconnect.
    assert owner.get("/me/fitness").json()["connected"] is False


def test_garbage_tokens_401_uniformly(owner, anon):
    assert anon.post("/ingest/health", json=_payload()).status_code == 401
    assert (
        anon.post(
            "/ingest/health",
            json=_payload(),
            headers={"Authorization": "Bearer not-a-real-token"},
        ).status_code
        == 401
    )


# ---- the import ------------------------------------------------------------------


def test_import_lands_on_the_fitness_tab(owner):
    token = _mint(owner)
    res = _send(owner, token, _payload())
    assert res.status_code == 200, res.text
    assert res.json()["workouts"] == 1

    body = owner.get("/me/fitness", params={"date": TODAY.isoformat()}).json()
    assert body["connected"] is True
    assert body["last_sync"] is not None
    assert body["today"]["steps"] == 8000  # two intra-day points summed
    assert body["today"]["active_kcal"] == 512.5
    assert body["today"]["exercise_minutes"] == 34
    assert body["today"]["resting_hr"] == 60  # averaged, not summed

    [workout] = body["workouts"]
    assert workout["activity"] == "Outdoor Run"
    assert workout["duration_s"] == 2100
    assert workout["kcal"] == 320.0
    assert workout["distance_m"] == 5200.0  # km normalized to meters
    assert workout["avg_hr"] == 142

    week = body["week"]
    assert len(week) == 7
    assert week[-1]["date_for"] == TODAY.isoformat()
    assert week[-1]["steps"] == 8000
    assert week[-1]["active_kcal"] == 512.5
    assert week[-1]["exercise_minutes"] == 34
    assert week[-1]["resting_hr"] == 60
    assert week[0]["steps"] is None and week[0]["active_kcal"] is None


def test_resending_a_window_never_duplicates(owner):
    token = _mint(owner)
    assert _send(owner, token, _payload()).status_code == 200
    assert _send(owner, token, _payload()).status_code == 200

    body = owner.get("/me/fitness", params={"date": TODAY.isoformat()}).json()
    assert body["today"]["steps"] == 8000  # upserted, not doubled
    assert len(body["workouts"]) == 1  # matched on the exporter's id


def test_imported_weight_lands_in_the_weight_log_in_kg(owner):
    token = _mint(owner)
    _send(owner, token, _payload())
    weights = owner.get("/me/health").json()["weights"]
    assert any(
        w["date_for"] == TODAY.isoformat() and abs(w["weight_kg"] - 90.72) < 0.01
        for w in weights
    )


def test_a_deliberate_weigh_in_beats_the_sync(owner):
    owner.put(
        "/me/health/weight",
        json={"date_for": TODAY.isoformat(), "weight_kg": 88.0},
    )
    token = _mint(owner)
    _send(owner, token, _payload())
    weights = owner.get("/me/health").json()["weights"]
    today_rows = [w for w in weights if w["date_for"] == TODAY.isoformat()]
    assert today_rows and today_rows[0]["weight_kg"] == 88.0


def test_fitness_data_is_self_only(owner, parent):
    token = _mint(owner)
    _send(owner, token, _payload())
    body = parent.get("/me/fitness").json()
    assert body["today"]["steps"] is None
    assert body["workouts"] == []
    assert body["connected"] is False


# ---- goals + history --------------------------------------------------------------


def test_goals_start_on_the_recommended_defaults(owner):
    body = owner.get("/me/fitness").json()
    assert body["goals"] == {"steps": 10000, "active_kcal": 500, "exercise_minutes": 30}


def test_a_member_can_tune_and_reset_their_own_goals(owner):
    res = owner.patch("/me/fitness/goals", json={"steps": 4000})
    assert res.status_code == 200, res.text
    assert res.json() == {"steps": 4000, "active_kcal": 500, "exercise_minutes": 30}
    # a later partial change leaves the tuned field alone
    res = owner.patch("/me/fitness/goals", json={"exercise_minutes": 10})
    assert res.json() == {"steps": 4000, "active_kcal": 500, "exercise_minutes": 10}
    # an explicit null puts one goal back on the default, nothing else moves
    res = owner.patch("/me/fitness/goals", json={"steps": None})
    assert res.json() == {"steps": 10000, "active_kcal": 500, "exercise_minutes": 10}


def test_goals_are_per_member(owner, parent):
    owner.patch("/me/fitness/goals", json={"steps": 4000})
    assert parent.get("/me/fitness").json()["goals"]["steps"] == 10000


def test_nonsense_goals_are_refused(owner):
    assert owner.patch("/me/fitness/goals", json={"steps": 10}).status_code == 422
    assert owner.patch("/me/fitness/goals", json={"active_kcal": 999999}).status_code == 422
    assert owner.patch("/me/fitness/goals", json={"exercise_minutes": 0}).status_code == 422
    # none of that stuck
    assert owner.get("/me/fitness").json()["goals"]["steps"] == 10000


def test_minors_cannot_touch_goals_or_history(child):
    assert child.patch("/me/fitness/goals", json={"steps": 4000}).status_code == 403
    assert child.get("/me/fitness/history").status_code == 403


def test_history_serves_the_trailing_thirty_days(owner):
    token = _mint(owner)
    _send(owner, token, _payload())
    _send(owner, token, _payload(YESTERDAY))

    days = owner.get("/me/fitness/history", params={"date": TODAY.isoformat()}).json()["days"]
    assert len(days) == 30
    assert days[0]["date_for"] == (TODAY - dt.timedelta(days=29)).isoformat()
    assert days[-1]["date_for"] == TODAY.isoformat()
    assert days[-1]["steps"] == 8000 and days[-2]["steps"] == 8000
    assert days[0]["steps"] is None  # empty days come back honest, not zero


def test_history_is_self_only_too(owner, parent):
    token = _mint(owner)
    _send(owner, token, _payload())
    days = parent.get("/me/fitness/history").json()["days"]
    assert all(d["steps"] is None for d in days)


def test_malformed_payloads_are_survived(owner):
    token = _mint(owner)
    res = _send(
        owner,
        token,
        {
            "data": {
                "metrics": [
                    "junk",
                    {"name": "step_count", "units": "count", "data": [{"date": "??", "qty": 1}]},
                    {"name": "step_count"},
                ],
                "workouts": [{"name": "No start"}, 42],
            }
        },
    )
    assert res.status_code == 200
    assert res.json() == {"days": 0, "workouts": 0}
