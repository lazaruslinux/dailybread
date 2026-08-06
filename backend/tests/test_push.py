"""Web Push: subscription management and the reminder engine.

pywebpush is patched with a recorder - no test talks to a real push service.
The reminder engine runs against the test database by pointing app.push's
SessionLocal at the same engine the API fixtures use.
"""

import datetime as dt
from types import SimpleNamespace


import app.push as push_engine
from tests.conftest import user_id

SUB = {
    "endpoint": "https://push.example/device-1",
    "keys": {"p256dh": "client-public-key", "auth": "client-auth-secret"},
}
SUB2 = {
    "endpoint": "https://push.example/device-2",
    "keys": {"p256dh": "client-public-key-2", "auth": "client-auth-secret-2"},
}


# configured/outbox/engine_db now live in conftest.py, shared with the
# approval and digest tests.


# ---- endpoints ---------------------------------------------------------------


def test_push_is_off_until_the_server_is_configured(owner):
    assert owner.get("/push/key").status_code == 503
    assert owner.put("/push/subscription", json=SUB).status_code == 503
    assert owner.post("/push/test").status_code == 503


def test_key_requires_a_session(anon, configured):
    assert anon.get("/push/key").status_code == 401


def test_subscribe_and_key(owner, configured):
    assert owner.get("/push/key").json() == {"key": "test-public-key"}
    assert owner.put("/push/subscription", json=SUB).status_code == 204
    # Subscribing the same endpoint again is an update, not a duplicate.
    assert owner.put("/push/subscription", json=SUB).status_code == 204


def test_a_device_that_changes_hands_moves_to_the_new_member(
    owner, parent, configured, outbox
):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB)  # same device, new login
    # Only the new member's test ping reaches it.
    assert owner.post("/push/test").json() == {"sent": 0}
    assert parent.post("/push/test").json() == {"sent": 1}


def test_unsubscribe_is_scoped_to_your_own_rows(owner, parent, configured, outbox):
    owner.put("/push/subscription", json=SUB)
    parent.request("DELETE", "/push/subscription", json={"endpoint": SUB["endpoint"]})
    assert owner.post("/push/test").json() == {"sent": 1}  # still there
    owner.request("DELETE", "/push/subscription", json={"endpoint": SUB["endpoint"]})
    assert owner.post("/push/test").json() == {"sent": 0}


def test_test_ping_hits_every_device_of_the_member(owner, configured, outbox):
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/subscription", json=SUB2)
    assert owner.post("/push/test").json() == {"sent": 2}
    assert sorted(outbox) == [SUB["endpoint"], SUB2["endpoint"]]


def test_a_dead_endpoint_is_dropped_on_send(owner, configured, monkeypatch):
    from pywebpush import WebPushException

    def gone(subscription_info, data, **kwargs):
        raise WebPushException("gone", response=SimpleNamespace(status_code=410))

    monkeypatch.setattr("pywebpush.webpush", gone)
    owner.put("/push/subscription", json=SUB)
    assert owner.post("/push/test").json() == {"sent": 0}

    # The row is gone: a working send afterwards has nothing to deliver to.
    monkeypatch.setattr("pywebpush.webpush", lambda subscription_info, data, **kw: None)
    assert owner.post("/push/test").json() == {"sent": 0}


# ---- the reminder engine -------------------------------------------------------


def _now_at(hour: int, minute: int) -> dt.datetime:
    return dt.datetime.combine(dt.date.today(), dt.time(hour, minute))


def test_reminds_assignees_before_a_timed_card(
    owner, parent, configured, outbox, engine_db
):
    kid_id = user_id(parent)
    parent.put("/push/subscription", json=SUB)
    res = owner.post(
        "/items",
        json={
            "kind": "appointment",
            "title": "Dentist",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "14:10:00",
            "end_time": "15:00:00",
            "assignee_ids": [kid_id],
        },
    )
    assert res.status_code == 201, res.text

    outbox.clear()  # setup's board-change push isn't under test here
    assert push_engine.reminder_tick(_now_at(14, 0)) == 1
    assert outbox == [SUB["endpoint"]]
    # Same window again: the log stops a duplicate.
    assert push_engine.reminder_tick(_now_at(14, 1)) == 0


def test_cards_outside_the_lead_window_wait_their_turn(
    owner, configured, outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    owner.post(
        "/items",
        json={
            "kind": "task",
            "title": "Take out bins",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "14:40:00",
        },
    )
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0  # 40 min out, lead is 15
    assert push_engine.reminder_tick(_now_at(14, 30)) == 1


def test_a_completed_card_is_not_reminded(owner, configured, outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    res = owner.post(
        "/items",
        json={
            "kind": "task",
            "title": "Call plumber",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "14:10:00",
        },
    )
    item_id = res.json()["id"]
    owner.post(f"/items/{item_id}/complete?date={dt.date.today().isoformat()}")
    outbox.clear()  # setup's board-change pushes aren't under test here
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0


def test_routine_reminders_reach_every_adult_participant(
    owner, parent, child, configured, outbox, engine_db
):
    # A routine is only ever checked off by an assigned kid, and kids take no
    # reminders, so every adult participant gets the heads-up.
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    res = owner.post(
        "/items",
        json={
            "kind": "routine",
            "title": "Evening reading",
            "time_of_day": "14:10:00",
            "assignee_ids": [user_id(owner), user_id(parent), user_id(child)],
            "repeat": {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
        },
    )
    assert res.status_code == 201, res.text

    outbox.clear()  # setup's board-change pushes aren't under test here
    assert push_engine.reminder_tick(_now_at(14, 0)) == 2
    assert sorted(outbox) == sorted([SUB["endpoint"], SUB2["endpoint"]])


def test_family_visible_unassigned_cards_notify_the_household(
    owner, parent, configured, outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    res = owner.post(
        "/items",
        json={
            "kind": "appointment",
            "title": "Grandma arrives",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "14:10:00",
            "end_time": "15:00:00",
            "visibility": "family",
        },
    )
    assert res.status_code == 201, res.text
    outbox.clear()  # setup's board-change pushes aren't under test here
    assert push_engine.reminder_tick(_now_at(14, 0)) == 2
    assert sorted(outbox) == [SUB["endpoint"], SUB2["endpoint"]]


def test_minors_get_no_card_reminders(owner, child, configured, outbox, engine_db):
    # Kid mode: nothing pushes to a minor, even one with a subscribed device
    # and a card of their own coming up.
    kid_id = user_id(child)
    child.put("/push/subscription", json=SUB2)
    res = owner.post(
        "/items",
        json={
            "kind": "appointment",
            "title": "Piano lesson",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "14:10:00",
            "end_time": "15:00:00",
            "assignee_ids": [kid_id],
        },
    )
    assert res.status_code == 201, res.text
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0
    assert outbox == []


def test_repeating_appointment_reminds_only_on_its_day(
    owner, parent, configured, outbox, engine_db
):
    parent.put("/push/subscription", json=SUB)
    today_wd = dt.date.today().weekday()
    off_day = (today_wd + 3) % 7
    res = owner.post(
        "/items",
        json={
            "kind": "appointment",
            "title": "Weekly work meeting",
            "time_of_day": "14:10:00",
            "end_time": "15:00:00",
            "assignee_ids": [user_id(parent)],
            "repeat": {"type": "weekly", "days": [off_day]},
        },
    )
    assert res.status_code == 201, res.text
    outbox.clear()  # setup's board-change pushes aren't under test here
    # Not scheduled today: silence (this used to fire daily for anything
    # with a repeat before repeating appointments existed).
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0

    owner.patch(f"/items/{res.json()['id']}", json={"repeat": {"type": "weekly", "days": [today_wd]}})
    outbox.clear()  # the reschedule itself notifies; drain that too
    assert push_engine.reminder_tick(_now_at(14, 0)) == 1
    assert outbox == [SUB["endpoint"]]


def test_repeating_appointment_called_off_today_stays_quiet(
    owner, parent, configured, outbox, engine_db
):
    parent.put("/push/subscription", json=SUB)
    today_wd = dt.date.today().weekday()
    res = owner.post(
        "/items",
        json={
            "kind": "appointment",
            "title": "Standup",
            "time_of_day": "14:10:00",
            "end_time": "14:30:00",
            "assignee_ids": [user_id(parent)],
            "repeat": {"type": "weekly", "days": [today_wd]},
        },
    )
    assert res.status_code == 201, res.text
    owner.post(f"/items/{res.json()['id']}/cancel?date={dt.date.today().isoformat()}")
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0


def test_a_carved_out_occurrence_is_never_reminded(
    owner, parent, configured, outbox, engine_db
):
    # Dropping the day removes it from the series everywhere, the reminder
    # loop included: the pattern still says today, the skip says no.
    parent.put("/push/subscription", json=SUB)
    today_wd = dt.date.today().weekday()
    res = owner.post(
        "/items",
        json={
            "kind": "appointment",
            "title": "Standup",
            "time_of_day": "14:10:00",
            "end_time": "14:30:00",
            "assignee_ids": [user_id(parent)],
            "repeat": {"type": "weekly", "days": [today_wd]},
        },
    )
    assert res.status_code == 201, res.text
    today = dt.date.today().isoformat()
    assert owner.delete(
        f"/items/{res.json()['id']}/occurrence?date={today}"
    ).status_code == 204
    outbox.clear()  # the board-change push isn't under test here
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0


# ---- catch-up: a start that slipped past while the server was down ----------------


def _dated_task(client, title, time_of_day, end_time=None):
    body = {
        "kind": "task",
        "title": title,
        "date_for": dt.date.today().isoformat(),
        "time_of_day": time_of_day,
    }
    if end_time is not None:
        body["kind"] = "appointment"
        body["end_time"] = end_time
    res = client.post("/items", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_a_missed_start_still_fires_within_the_catch_up_window(
    owner, configured, push_outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    _dated_task(owner, "Take out bins", "14:00:00")
    push_outbox.clear()
    # 14:20: the 14:00 start slipped past during downtime, still inside the
    # 30-minute catch-up. It fires, flagged with when it began.
    assert push_engine.reminder_tick(_now_at(14, 20)) == 1
    assert push_outbox[-1][1]["body"] == "Started at 2:00 PM"
    # The ReminderLog claim means a second tick sends nothing more.
    assert push_engine.reminder_tick(_now_at(14, 21)) == 0


def test_a_start_missed_by_more_than_thirty_minutes_stays_quiet(
    owner, configured, outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    _dated_task(owner, "Take out bins", "14:00:00")
    outbox.clear()
    assert push_engine.reminder_tick(_now_at(14, 45)) == 0  # 45 min late, past catch-up


def test_an_already_ended_event_does_not_fire_late(owner, configured, outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    _dated_task(owner, "Standup", "14:00:00", end_time="14:10:00")
    outbox.clear()
    # 14:20 is inside the catch-up window, but the event ended at 14:10 — a
    # late ping is only noise, so it stays quiet.
    assert push_engine.reminder_tick(_now_at(14, 20)) == 0


def test_an_on_time_fire_never_refires_as_late(owner, configured, outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    _dated_task(owner, "Take out bins", "14:10:00")
    outbox.clear()
    assert push_engine.reminder_tick(_now_at(14, 0)) == 1  # on time
    # 14:20 would be inside the catch-up window, but the on-time fire already
    # claimed the ReminderLog row.
    assert push_engine.reminder_tick(_now_at(14, 20)) == 0


# ---- the start push: appointments say when they begin --------------------------


def _appointment(client, title="Dentist", time_of_day="14:00:00", end_time="15:00:00", **extra):
    res = client.post(
        "/items",
        json={
            "kind": "appointment",
            "title": title,
            "date_for": dt.date.today().isoformat(),
            "time_of_day": time_of_day,
            "end_time": end_time,
            **extra,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_an_appointment_says_when_it_starts(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    _appointment(owner)
    push_outbox.clear()
    # 13:40 is inside the half-hour lead.
    assert push_engine.reminder_tick(_now_at(13, 40)) == 1
    assert push_outbox[-1][1]["body"] == "Coming up: 2:00 PM – 3:00 PM"
    # 14:00 is the start itself: a second push, claimed separately.
    assert push_engine.reminder_tick(_now_at(14, 0)) == 1
    assert push_outbox[-1][1]["body"] == "Starting now"
    # And only once.
    assert push_engine.reminder_tick(_now_at(14, 1)) == 0


def test_a_start_recovered_after_a_restart_says_when_it_began(
    owner, configured, push_outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    _appointment(owner)
    push_outbox.clear()
    # The server was down through the lead and the start; 20 minutes late it
    # still says so, but it doesn't pretend the appointment is starting now.
    assert push_engine.reminder_tick(_now_at(14, 20)) == 1
    assert push_outbox[-1][1]["body"] == "Started at 2:00 PM"


def test_an_appointment_already_over_never_gets_a_start_push(
    owner, configured, outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    _appointment(owner, time_of_day="14:00:00", end_time="14:10:00")
    outbox.clear()
    assert push_engine.reminder_tick(_now_at(14, 20)) == 0


def test_only_appointments_get_a_start_push(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.post(
        "/items",
        json={
            "kind": "activity",
            "title": "Soccer",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "14:00:00",
            "end_time": "15:00:00",
        },
    )
    push_outbox.clear()
    # An activity's lead fires at 13:45 (the short heads-up), and nothing more
    # at its start: only appointments get the second push.
    assert push_engine.reminder_tick(_now_at(13, 50)) == 1
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0
    assert push_engine.reminder_tick(_now_at(14, 1)) == 0


def test_a_routine_gets_no_start_push(owner, configured, outbox, engine_db):
    # Assigned to nobody, so the owner is its participant: a minor would get no
    # push at all and the second leg would be untestable.
    owner.put("/push/subscription", json=SUB)
    today_wd = dt.date.today().weekday()
    res = owner.post(
        "/items",
        json={
            "kind": "routine",
            "title": "Brush teeth",
            "time_of_day": "14:00:00",
            "end_time": "14:30:00",
            "repeat": {"type": "weekly", "days": [today_wd]},
        },
    )
    assert res.status_code == 201, res.text
    outbox.clear()
    assert push_engine.reminder_tick(_now_at(13, 50)) == 1  # the heads-up
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0  # no second push


def test_a_cancelled_appointment_never_announces_its_start(
    owner, configured, outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    item = _appointment(owner)
    owner.post(f"/items/{item['id']}/cancel?date={dt.date.today().isoformat()}")
    outbox.clear()
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0


def test_creating_a_card_timed_in_the_past_fires_nothing(
    owner, configured, outbox, engine_db, monkeypatch
):
    # The member just set this time themselves; catch-up is for reminders lost
    # to downtime, not edits into the past. Pin the items clock AFTER the
    # card's start so creation lands as an edit into the past and pre-claims.
    from app.routers import items as items_router

    monkeypatch.setattr(items_router, "_server_now", lambda: _now_at(14, 10))
    _dated_task(owner, "Take out bins", "14:00:00")
    outbox.clear()
    assert push_engine.reminder_tick(_now_at(14, 20)) == 0


def test_rescheduling_into_the_past_fires_nothing(
    owner, configured, outbox, engine_db, monkeypatch
):
    from app.routers import items as items_router

    # Created for the evening: no pre-claim at creation.
    item = _dated_task(owner, "Take out bins", "19:00:00")
    # Then, at 14:10, rescheduled onto a start that already passed.
    monkeypatch.setattr(items_router, "_server_now", lambda: _now_at(14, 10))
    res = owner.patch(f"/items/{item['id']}", json={"time_of_day": "14:00:00"})
    assert res.status_code == 200, res.text
    outbox.clear()  # the reschedule's own board push isn't under test
    assert push_engine.reminder_tick(_now_at(14, 20)) == 0


def test_a_failed_send_logs_the_user_and_tag(owner, configured, monkeypatch, caplog):
    def boom(subscription_info, data, **kwargs):
        from pywebpush import WebPushException

        raise WebPushException("boom", response=SimpleNamespace(status_code=500))

    monkeypatch.setattr("pywebpush.webpush", boom)
    owner.put("/push/subscription", json=SUB)
    uid = user_id(owner)
    with caplog.at_level("WARNING"):
        owner.post("/push/test")
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert f"push send failed for user {uid}" in msg
    assert "tag test" in msg  # the /push/test payload's tag rides the log line


# ---- board-change notifications --------------------------------------------------


def test_adding_a_card_notifies_once_with_its_name(owner, parent, child, configured, push_outbox, engine_db):
    parent.put("/push/subscription", json=SUB)
    child.put("/push/subscription", json=SUB2)
    res = owner.post(
        "/items",
        json={"kind": "task", "title": "Take out the trash", "visibility": "family"},
    )
    assert res.status_code == 201, res.text
    # ONE push per action for a family-visible card: the other adult's device.
    # Never the actor, never a kid — and the card's name rides in the title.
    assert [ep for ep, _ in push_outbox] == [SUB["endpoint"]]
    assert push_outbox[0][1]["title"] == "Owner added a task: Take out the trash"


def test_routine_actions_make_board_news(owner, parent, configured, outbox, engine_db):
    parent.put("/push/subscription", json=SUB)
    res = owner.post(
        "/items",
        json={
            "kind": "routine",
            "title": "Morning run",
            "visibility": "family",
            "repeat": {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
        },
    )
    assert res.status_code == 201, res.text
    item_id = res.json()["id"]
    owner.patch(f"/items/{item_id}", json={"time_of_day": "07:00:00"})
    owner.delete(f"/items/{item_id}")
    # Changing the household's rhythm is rare news, so it rings like any other
    # kind. Nothing fires on the rhythm itself, only on these actions.
    assert outbox == [SUB["endpoint"]] * 3


def test_a_family_card_with_assignees_still_reaches_the_other_parent(
    owner, parent, child, configured, outbox, engine_db
):
    # Naming someone on a family-board card used to silence the co-parent.
    parent.put("/push/subscription", json=SUB)
    res = owner.post(
        "/items",
        json={
            "kind": "task",
            "title": "Pack the lunches",
            "visibility": "family",
            "assignee_ids": [user_id(child)],
        },
    )
    assert res.status_code == 201, res.text
    assert outbox == [SUB["endpoint"]]


def test_an_assigned_private_card_still_stays_private(
    owner, parent, configured, outbox, engine_db
):
    parent.put("/push/subscription", json=SUB)
    res = owner.post(
        "/items",
        json={
            "kind": "task",
            "title": "Buy her gift",
            "visibility": "private",
            "assignee_ids": [user_id(owner)],
        },
    )
    assert res.status_code == 201, res.text
    assert outbox == []


def test_only_schedule_changes_notify(owner, parent, configured, outbox, engine_db):
    parent.put("/push/subscription", json=SUB)
    res = owner.post(
        "/items",
        json={"kind": "appointment", "title": "Dentist", "visibility": "family",
              "date_for": dt.date.today().isoformat(),
              "time_of_day": "14:00:00", "end_time": "15:00:00"},
    )
    item_id = res.json()["id"]
    outbox.clear()

    # A title tweak is quiet; moving the time speaks.
    owner.patch(f"/items/{item_id}", json={"title": "Dentist (Dr. Lee)"})
    assert outbox == []
    owner.patch(f"/items/{item_id}", json={"time_of_day": "15:00:00", "end_time": "16:00:00"})
    assert outbox == [SUB["endpoint"]]
    outbox.clear()

    owner.delete(f"/items/{item_id}")
    assert outbox == [SUB["endpoint"]]


def test_private_card_changes_stay_private(owner, parent, configured, outbox, engine_db):
    parent.put("/push/subscription", json=SUB)
    res = owner.post(
        "/items",
        json={"kind": "task", "title": "Buy her gift", "visibility": "private"},
    )
    assert res.status_code == 201
    assert outbox == []  # the other parent can't see it, so they don't hear about it


def test_appointments_get_a_half_hour_of_runway(owner, configured, outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.post(
        "/items",
        json={
            "kind": "appointment",
            "title": "Dentist",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "15:00:00",
            "end_time": "15:30:00",
        },
    )
    owner.post(
        "/items",
        json={
            "kind": "task",
            "title": "Take out bins",
            "date_for": dt.date.today().isoformat(),
            "time_of_day": "15:00:00",
        },
    )
    outbox.clear()
    # 14:20: too early for either lead window.
    assert push_engine.reminder_tick(_now_at(14, 20)) == 0
    # 14:40: the appointment is inside its half-hour lead, the task (15 min) is not.
    assert push_engine.reminder_tick(_now_at(14, 40)) == 1
    # 14:50: now the task's window opens too.
    assert push_engine.reminder_tick(_now_at(14, 50)) == 1


def test_a_synced_workout_tells_the_family(owner, parent, child, configured, push_outbox, engine_db):
    parent.put("/push/subscription", json=SUB)
    child.put("/push/subscription", json=SUB2)
    token = owner.post("/me/fitness/token").json()["token"]
    day = dt.date.today().isoformat()
    payload = {
        "data": {
            "workouts": [
                {
                    "id": "wk-push-1",
                    "name": "Outdoor Run",
                    "start": f"{day} 06:30:00 -0700",
                    "end": f"{day} 07:01:00 -0700",
                    "duration": 1860,
                },
                {
                    "id": "wk-push-2",
                    "name": "Cool Down",
                    "start": f"{day} 07:05:00 -0700",
                    "end": f"{day} 07:10:00 -0700",
                    "duration": 300,
                },
            ]
        }
    }
    res = owner.post(
        "/ingest/health", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    # One push for the real workout (the 5-minute cool-down is not news),
    # to the other adult only, never the kid, never the runner.
    assert [ep for ep, _ in push_outbox] == [SUB["endpoint"]]
    assert push_outbox[0][1]["title"] == "Owner completed a workout"
    assert push_outbox[0][1]["body"] == "Outdoor Run · 31 min"

    # The same window re-sent is an update, not news.
    res = owner.post(
        "/ingest/health", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    assert len(push_outbox) == 1


def test_workout_push_respects_the_pref(owner, parent, configured, push_outbox, engine_db):
    parent.put("/push/subscription", json=SUB)
    parent.put("/push/prefs", json={"prefs": {"workouts": False}})
    token = owner.post("/me/fitness/token").json()["token"]
    day = dt.date.today().isoformat()
    payload = {
        "data": {
            "workouts": [
                {
                    "id": "wk-push-3",
                    "name": "Outdoor Run",
                    "start": f"{day} 06:30:00 -0700",
                    "end": f"{day} 07:01:00 -0700",
                    "duration": 1860,
                }
            ]
        }
    }
    owner.post("/ingest/health", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert push_outbox == []
