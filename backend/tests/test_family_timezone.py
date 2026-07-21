"""Families keep their own clock.

families.timezone (IANA name, nullable) localizes reminders and digests:
NULL means the server's clock, exactly the single-family behavior. The
wizards send the browser's zone; admins can change it later. Digest tests
pass timezone-AWARE datetimes so the assertions don't depend on the clock
of the machine running the tests.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import app.push as push_engine
from app.clock import family_now

SUB = {
    "endpoint": "https://push.example/dad-phone",
    "keys": {"p256dh": "k1", "auth": "a1"},
}
SUB2 = {
    "endpoint": "https://push.example/b-phone",
    "keys": {"p256dh": "k2", "auth": "a2"},
}


# ---- the clock helper ------------------------------------------------------------


def test_family_now_converts_and_falls_back():
    noon_utc = dt.datetime(2026, 7, 9, 19, 30, tzinfo=ZoneInfo("UTC"))
    # Phoenix is UTC-7 year round.
    assert family_now(noon_utc, "America/Phoenix") == dt.datetime(2026, 7, 9, 12, 30)
    # No zone, or a zone that fails to load: the server's clock, unchanged.
    assert family_now(noon_utc, None) is noon_utc
    assert family_now(noon_utc, "Not/AZone") is noon_utc


# ---- setting the zone ------------------------------------------------------------


def test_family_starts_on_the_server_clock(owner):
    assert owner.get("/families/me").json()["timezone"] is None


def test_admin_moves_the_family_to_its_own_clock(owner):
    res = owner.patch("/families/me", json={"name": "Home", "timezone": "America/New_York"})
    assert res.status_code == 200, res.text
    assert res.json()["timezone"] == "America/New_York"

    # Omitting the field leaves it alone; an explicit null clears it.
    assert owner.patch("/families/me", json={"name": "Home"}).json()["timezone"] == "America/New_York"
    assert owner.patch("/families/me", json={"name": "Home", "timezone": None}).json()["timezone"] is None


def test_a_typoed_zone_is_refused_not_stored(owner):
    res = owner.patch("/families/me", json={"name": "Home", "timezone": "America/Phenix"})
    assert res.status_code == 400
    assert owner.get("/families/me").json()["timezone"] is None


def test_bootstrap_takes_the_browsers_zone(app):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    res = client.post(
        "/auth/bootstrap",
        json={
            "username": "head", "display_name": "Head", "password": "a-solid-password",
            "family_name": "The Zs", "timezone": "Europe/Berlin",
        },
    )
    assert res.status_code == 201, res.text
    assert client.get("/families/me").json()["timezone"] == "Europe/Berlin"


def test_bootstrap_refuses_a_bad_zone(app):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    res = client.post(
        "/auth/bootstrap",
        json={
            "username": "head", "display_name": "Head", "password": "a-solid-password",
            "family_name": "The Zs", "timezone": "Mars/OlympusMons",
        },
    )
    assert res.status_code == 400
    # Nothing half-created: the wizard can simply run again.
    assert client.get("/auth/setup").json() == {"initialized": False}


def test_create_family_wizard_takes_a_zone(homeless):
    res = homeless.post("/families", json={"name": "The Bs", "timezone": "America/Chicago"})
    assert res.status_code == 201, res.text
    assert res.json()["timezone"] == "America/Chicago"


# ---- the schedule actually follows the family's clock ----------------------------


def test_evening_checkin_fires_on_each_familys_clock(
    owner, other, configured, outbox, engine_db
):
    """Two families, one install: family A on the server's clock, family B in
    Phoenix. At 19:30 UTC it's evening for A but lunchtime for B; seven hours
    later B has its evening and A (already claimed, and out of window) stays
    quiet."""
    owner.put("/push/subscription", json=SUB)
    other.put("/push/subscription", json=SUB2)
    other.patch("/families/me", json={"name": "The Bs", "timezone": "America/Phoenix"})

    at_1930_utc = dt.datetime(2026, 7, 9, 19, 30, tzinfo=ZoneInfo("UTC"))
    assert push_engine.digest_tick(at_1930_utc) == 1
    assert outbox == [SUB["endpoint"]]

    outbox.clear()
    at_0230_utc = dt.datetime(2026, 7, 10, 2, 30, tzinfo=ZoneInfo("UTC"))  # 19:30 in Phoenix
    assert push_engine.digest_tick(at_0230_utc) == 1
    assert outbox == [SUB2["endpoint"]]


def test_reminders_run_on_the_familys_clock(owner, other, configured, outbox, engine_db):
    """The same wall-clock card in two households reminds each on ITS OWN
    clock. At 14:50 UTC the card is 10 minutes ahead for family A (server
    clock) but midmorning for Phoenix's family B; at 21:50 UTC it's B's turn."""
    owner.put("/push/subscription", json=SUB)
    other.put("/push/subscription", json=SUB2)
    other.patch("/families/me", json={"name": "The Bs", "timezone": "America/Phoenix"})

    today = dt.date.today()
    for client in (owner, other):
        res = client.post(
            "/items",
            json={
                "kind": "appointment",
                "title": "School pickup",
                "date_for": today.isoformat(),
                "time_of_day": "15:00:00",
                "end_time": "15:15:00",
            },
        )
        assert res.status_code == 201, res.text
    outbox.clear()  # board-change pushes aren't under test here

    at_1450_utc = dt.datetime.combine(today, dt.time(14, 50), tzinfo=ZoneInfo("UTC"))
    assert push_engine.reminder_tick(at_1450_utc) == 1
    assert outbox == [SUB["endpoint"]]

    outbox.clear()
    # 14:50 in Phoenix, the same calendar day (UTC-7).
    at_2150_utc = dt.datetime.combine(today, dt.time(21, 50), tzinfo=ZoneInfo("UTC"))
    assert push_engine.reminder_tick(at_2150_utc) == 1
    assert outbox == [SUB2["endpoint"]]
