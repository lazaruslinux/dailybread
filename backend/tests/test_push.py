"""Web Push: subscription management and the reminder engine.

pywebpush is patched with a recorder - no test talks to a real push service.
The reminder engine runs against the test database by pointing app.push's
SessionLocal at the same engine the API fixtures use.
"""

import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

import app.push as push_engine
from app.config import settings
from tests.conftest import user_id

SUB = {
    "endpoint": "https://push.example/device-1",
    "keys": {"p256dh": "client-public-key", "auth": "client-auth-secret"},
}
SUB2 = {
    "endpoint": "https://push.example/device-2",
    "keys": {"p256dh": "client-public-key-2", "auth": "client-auth-secret-2"},
}


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")


@pytest.fixture()
def outbox(monkeypatch):
    """Record every webpush() call instead of hitting a push service."""
    calls = []

    def fake_webpush(subscription_info, data, **kwargs):
        calls.append(subscription_info["endpoint"])

    monkeypatch.setattr("pywebpush.webpush", fake_webpush)
    return calls


@pytest.fixture()
def engine_db(app, monkeypatch):
    """Bind the reminder engine's own sessions to the test database."""
    TestingSession = sessionmaker(
        bind=app.state.test_engine, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(push_engine, "SessionLocal", TestingSession)
    return TestingSession


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
    owner, child, configured, outbox, engine_db
):
    kid_id = user_id(child)
    child.put("/push/subscription", json=SUB)
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
    assert push_engine.reminder_tick(_now_at(14, 0)) == 0


def test_routines_skip_participants_who_already_did_theirs(
    owner, child, configured, outbox, engine_db
):
    kid_id = user_id(child)
    owner.put("/push/subscription", json=SUB)
    child.put("/push/subscription", json=SUB2)
    res = owner.post(
        "/items",
        json={
            "kind": "routine",
            "title": "Evening reading",
            "time_of_day": "14:10:00",
            "assignee_ids": [user_id(owner), kid_id],
            "repeat": {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
        },
    )
    assert res.status_code == 201, res.text
    item_id = res.json()["id"]
    child.post(f"/items/{item_id}/complete?date={dt.date.today().isoformat()}")

    assert push_engine.reminder_tick(_now_at(14, 0)) == 1
    assert outbox == [SUB["endpoint"]]  # the owner's device, not the kid's


def test_family_visible_unassigned_cards_notify_the_household(
    owner, parent, child, configured, outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    child.put("/push/subscription", json=SUB2)
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
    assert push_engine.reminder_tick(_now_at(14, 0)) == 2
    assert sorted(outbox) == [SUB["endpoint"], SUB2["endpoint"]]
