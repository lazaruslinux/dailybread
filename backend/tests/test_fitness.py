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


def _bodyfat_payload(day: dt.date, fat_qty, weight_qty=200.0) -> dict:
    """Body fat listed BEFORE weight, the order the exporter doesn't promise:
    the import must land the weigh-in first anyway."""
    return {
        "data": {
            "metrics": [
                {
                    "name": "body_fat_percentage",
                    "units": "%",
                    "data": [{"date": _stamp(day, "07:00:00"), "qty": fat_qty}],
                },
                {
                    "name": "weight_body_mass",
                    "units": "lb",
                    "data": [{"date": _stamp(day, "07:00:00"), "qty": weight_qty}],
                },
            ]
        }
    }


def _today_weight(client) -> dict:
    weights = client.get("/me/health").json()["weights"]
    rows = [w for w in weights if w["date_for"] == TODAY.isoformat()]
    assert rows
    return rows[0]


def test_body_fat_joins_the_days_weight_entry(owner):
    token = _mint(owner)
    assert _send(owner, token, _bodyfat_payload(TODAY, 23.4)).status_code == 200
    row = _today_weight(owner)
    assert abs(row["weight_kg"] - 90.72) < 0.01
    assert row["body_fat_pct"] == 23.4


def test_body_fat_fractions_are_understood(owner):
    # HealthKit stores body fat as a fraction; some exporter versions pass
    # that straight through.
    token = _mint(owner)
    _send(owner, token, _bodyfat_payload(TODAY, 0.234))
    assert _today_weight(owner)["body_fat_pct"] == 23.4


def test_typed_body_fat_beats_the_sync(owner):
    owner.put(
        "/me/health/weight",
        json={"date_for": TODAY.isoformat(), "weight_kg": 88.0, "body_fat_pct": 20.0},
    )
    token = _mint(owner)
    _send(owner, token, _bodyfat_payload(TODAY, 23.4))
    row = _today_weight(owner)
    assert row["weight_kg"] == 88.0
    assert row["body_fat_pct"] == 20.0


def test_sync_fills_a_blank_body_fat_on_a_manual_weigh_in(owner):
    owner.put(
        "/me/health/weight",
        json={"date_for": TODAY.isoformat(), "weight_kg": 88.0},
    )
    token = _mint(owner)
    _send(owner, token, _bodyfat_payload(TODAY, 23.4))
    row = _today_weight(owner)
    assert row["weight_kg"] == 88.0  # the deliberate weigh-in still wins
    assert row["body_fat_pct"] == 23.4  # but the blank fat is filled


def test_body_fat_without_a_weigh_in_is_skipped(owner):
    token = _mint(owner)
    payload = _bodyfat_payload(TODAY, 23.4)
    del payload["data"]["metrics"][1]  # no weight anywhere
    assert _send(owner, token, payload).status_code == 200
    weights = owner.get("/me/health").json()["weights"]
    assert not [w for w in weights if w["date_for"] == TODAY.isoformat()]


# ---- watch calories in the food budget -------------------------------------------


def test_watch_kcal_is_off_by_default(owner):
    token = _mint(owner)
    _send(owner, token, _payload())  # active_energy 512.5 lands
    day = owner.get(f"/diary?date={TODAY.isoformat()}").json()
    assert day["burned"] == 0
    assert day["watch_kcal"] is None
    assert day["targets"]["exercise_kcal"] == 0


def test_opted_in_watch_kcal_raises_the_budget(owner):
    assert owner.put("/me/fitness/watch-kcal", json={"enabled": True}).json() == {
        "enabled": True
    }
    token = _mint(owner)
    _send(owner, token, _payload())
    day = owner.get(f"/diary?date={TODAY.isoformat()}").json()
    assert day["burned"] == 512.5
    assert day["watch_kcal"] == 512.5
    assert day["targets"]["exercise_kcal"] == 512.5


def test_watch_and_manual_log_never_sum(owner):
    """The budget takes the larger of the two: a logged run is already inside
    the watch's active total, so summing would count it twice."""
    owner.put("/me/fitness/watch-kcal", json={"enabled": True})
    owner.put("/me/health/weight", json={"date_for": TODAY.isoformat(), "weight_kg": 90.0})
    res = owner.post(
        "/me/exercise",
        json={"date_for": TODAY.isoformat(), "activity": "running", "effort": "moderate", "minutes": 120},
    )
    assert res.status_code == 201, res.text
    manual = res.json()["kcal"]
    token = _mint(owner)
    _send(owner, token, _payload())  # watch says 512.5
    day = owner.get(f"/diary?date={TODAY.isoformat()}").json()
    assert day["burned"] == max(manual, 512.5)
    assert day["targets"]["exercise_kcal"] == max(manual, 512.5)


def test_watch_kcal_toggle_is_adults_only(child):
    assert child.put("/me/fitness/watch-kcal", json={"enabled": True}).status_code == 403


# ---- workout -> routine auto-complete --------------------------------------------


def _daily_routine(client, title: str, auto: bool = True, days: list[int] | None = None) -> dict:
    res = client.post(
        "/items",
        json={
            "kind": "routine",
            "title": title,
            "repeat": {"type": "weekly", "days": days or [0, 1, 2, 3, 4, 5, 6]},
            "workout_auto_complete": auto,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _feed_item(client, item_id: int) -> dict:
    feed = client.get(f"/items/feed?date={TODAY.isoformat()}").json()
    return next(i for i in feed["today"] if i["id"] == item_id)


def test_a_workout_checks_off_an_opted_in_routine(owner):
    routine = _daily_routine(owner, "Morning run", auto=True)
    plain = _daily_routine(owner, "Read a book", auto=False)
    token = _mint(owner)
    res = _send(owner, token, _payload())
    assert res.json()["routines_completed"] == 1
    assert _feed_item(owner, routine["id"])["completed"] is True
    assert _feed_item(owner, plain["id"])["completed"] is False


def test_resent_workouts_do_not_double_complete(owner):
    routine = _daily_routine(owner, "Morning run")
    token = _mint(owner)
    assert _send(owner, token, _payload()).json()["routines_completed"] == 1
    assert _send(owner, token, _payload()).json()["routines_completed"] == 0
    assert _feed_item(owner, routine["id"])["completed"] is True


def test_a_deliberate_check_is_left_alone(owner):
    routine = _daily_routine(owner, "Morning run")
    assert owner.post(f"/items/{routine['id']}/complete?date={TODAY.isoformat()}").status_code == 200
    token = _mint(owner)
    assert _send(owner, token, _payload()).json()["routines_completed"] == 0


def test_the_routine_must_land_on_the_workout_day(owner):
    # Scheduled only on a weekday that is NOT today.
    off_day = [(TODAY.weekday() + 3) % 7]
    _daily_routine(owner, "Leg day", days=off_day)
    token = _mint(owner)
    assert _send(owner, token, _payload()).json()["routines_completed"] == 0


def test_only_the_syncing_members_routines_complete(owner, parent):
    # The second parent's own flagged routine; the owner's workout is not theirs.
    _daily_routine(parent, "Their run")
    token = _mint(owner)
    assert _send(owner, token, _payload()).json()["routines_completed"] == 0


def test_the_flag_is_routines_only(owner):
    res = owner.post(
        "/items",
        json={"kind": "task", "title": "Call dentist", "workout_auto_complete": True},
    )
    assert res.status_code == 400


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
    assert res.json() == {"days": 0, "workouts": 0, "routines_completed": 0}
