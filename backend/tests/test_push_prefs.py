"""Per-kind push preferences, and the four notification kinds they gate:
the past-due sweep, the dinner-time reminder, the sync-went-quiet nudge, and
the verse-streak-at-risk word. Prefs subtract from a default of everything-on;
a missing key always reads as on, so new kinds never need a backfill.
"""

import datetime as dt

import app.push as push_engine
from app.models import DigestLog, IngestToken, VerseCheck
from tests.conftest import user_id

TODAY = dt.date.today()

SUB = {
    "endpoint": "https://push.example/dad-phone",
    "keys": {"p256dh": "k1", "auth": "a1"},
}
SUB2 = {
    "endpoint": "https://push.example/mom-phone",
    "keys": {"p256dh": "k2", "auth": "a2"},
}


def at(hour, minute=5):
    return dt.datetime.combine(TODAY, dt.time(hour, minute))


def make(client, **overrides):
    payload = {"kind": "task", "title": "Card", **overrides}
    res = client.post("/items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


# ---- the prefs endpoint ---------------------------------------------------------


def test_prefs_default_to_everything_on(owner):
    res = owner.get("/push/prefs")
    assert res.status_code == 200
    prefs = res.json()["prefs"]
    assert set(prefs) == set(push_engine.PREF_KINDS)
    assert all(prefs.values())


def test_flipping_one_kind_keeps_the_rest(owner):
    res = owner.put("/push/prefs", json={"prefs": {"midday": False}})
    assert res.status_code == 200
    prefs = res.json()["prefs"]
    assert prefs["midday"] is False
    assert prefs["morning"] is True
    # A second partial update doesn't resurrect the first.
    owner.put("/push/prefs", json={"prefs": {"family": False}})
    prefs = owner.get("/push/prefs").json()["prefs"]
    assert prefs == {**prefs, "midday": False, "family": False}
    # And flipping back on really clears it.
    owner.put("/push/prefs", json={"prefs": {"midday": True, "family": True}})
    assert all(owner.get("/push/prefs").json()["prefs"].values())


def test_unknown_kinds_are_refused(owner):
    res = owner.put("/push/prefs", json={"prefs": {"carrier-pigeon": False}})
    assert res.status_code == 400
    assert "carrier-pigeon" in res.json()["detail"]


# ---- prefs gate the existing sends ----------------------------------------------


def test_timed_off_silences_only_that_member(owner, parent, configured, outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    parent.put("/push/prefs", json={"prefs": {"timed": False}})
    make(
        owner,
        kind="appointment",
        title="Grandma arrives",
        date_for=TODAY.isoformat(),
        time_of_day="14:10:00",
        end_time="15:00:00",
        visibility="family",
    )
    outbox.clear()  # setup's board-change push isn't under test here
    assert push_engine.reminder_tick(at(14, 0)) == 1
    assert outbox == [SUB["endpoint"]]


def test_family_off_silences_board_changes(owner, parent, configured, outbox, engine_db):
    parent.put("/push/subscription", json=SUB)
    parent.put("/push/prefs", json={"prefs": {"family": False}})
    make(owner, title="Morning run", visibility="family", date_for=TODAY.isoformat())
    assert outbox == []


def test_approvals_off_silences_kid_checkoffs(owner, child, configured, outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/prefs", json={"prefs": {"approvals": False}})
    item = make(
        owner,
        kind="routine",
        title="Brush teeth",
        assignee_ids=[user_id(child)],
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )
    outbox.clear()
    child.post(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    assert outbox == []


def test_digest_off_claims_quietly(owner, configured, push_outbox, engine_db):
    # Off at 7, flipped back on at 8: the morning claim already landed, so
    # there's no belated good-morning (same rule as an empty board).
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/prefs", json={"prefs": {"morning": False}})
    make(owner, title="Call the plumber")

    assert push_engine.digest_tick(at(7)) == 0
    owner.put("/push/prefs", json={"prefs": {"morning": True}})
    assert push_engine.digest_tick(at(8)) == 0
    assert push_outbox == []


# ---- the past-due sweep ---------------------------------------------------------


def test_overdue_sweep_lists_what_slipped(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    make(
        owner,
        kind="appointment",
        title="Dentist",
        date_for=TODAY.isoformat(),
        time_of_day="14:00:00",
        end_time="14:30:00",
    )
    make(owner, title="Call the plumber", date_for=TODAY.isoformat(), time_of_day="09:00:00")

    assert push_engine.digest_tick(at(15, 59)) == 0  # not yet: the sweep is at 4
    assert push_engine.digest_tick(at(16)) == 1
    _endpoint, payload = push_outbox[0]
    assert payload["title"] == "A few things slipped past"
    assert payload["body"] == "Still open from today: Call the plumber, Dentist."
    # Once per day, whatever the server does.
    assert push_engine.digest_tick(at(17)) == 0
    assert len(push_outbox) == 1


def test_overdue_caps_at_three_titles(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    for hour in (8, 9, 10, 11):
        make(owner, title=f"Chore {hour}", date_for=TODAY.isoformat(), time_of_day=f"{hour:02d}:00:00")

    push_engine.digest_tick(at(16))
    body = push_outbox[0][1]["body"]
    assert body == "Still open from today: Chore 8, Chore 9, Chore 10 and 1 more."


def test_overdue_skips_done_future_and_routines(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    done = make(owner, title="Done thing", date_for=TODAY.isoformat(), time_of_day="09:00:00")
    owner.post(f"/items/{done['id']}/complete?date={TODAY.isoformat()}")
    make(owner, title="Tonight thing", date_for=TODAY.isoformat(), time_of_day="20:00:00")
    make(
        owner,
        kind="routine",
        title="Morning run",
        time_of_day="06:00:00",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )

    # The done card, the still-ahead card, and the routine are all left be —
    # and with nothing overdue the sweep claims quietly, so a card going
    # overdue at 17:30 doesn't ring a belated sweep.
    assert push_engine.digest_tick(at(16)) == 0
    assert push_outbox == []
    assert push_engine.digest_tick(at(18)) == 0


def test_overdue_respects_the_pref(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/prefs", json={"prefs": {"overdue": False}})
    make(owner, title="Slipped", date_for=TODAY.isoformat(), time_of_day="09:00:00")
    assert push_engine.digest_tick(at(16)) == 0


# ---- the evening's tomorrow preview ---------------------------------------------


def test_evening_previews_tomorrow(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    tomorrow = TODAY + dt.timedelta(days=1)
    make(
        owner,
        kind="appointment",
        title="Dentist",
        date_for=tomorrow.isoformat(),
        time_of_day="09:00:00",
        end_time="09:30:00",
    )
    make(
        owner,
        kind="appointment",
        title="Parent-teacher night",
        date_for=tomorrow.isoformat(),
        time_of_day="18:00:00",
        end_time="19:00:00",
    )

    assert push_engine.digest_tick(at(19)) == 1
    body = push_outbox[0][1]["body"]
    assert body == "How was your day? Tomorrow: Dentist at 9:00 AM (+1 more)."


def test_evening_stays_plain_when_tomorrow_is_clear(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    assert push_engine.digest_tick(at(19)) == 1
    assert push_outbox[0][1]["body"] == "How was your day?"


# ---- the dinner-time reminder ---------------------------------------------------


def set_dinner(owner, time="18:00:00", title="Tacos"):
    res = owner.put(
        "/meals",
        json={"date_for": TODAY.isoformat(), "slot": "dinner", "custom_title": title},
    )
    assert res.status_code == 200, res.text
    res = owner.put(
        "/meals/time",
        json={"date_for": TODAY.isoformat(), "slot": "dinner", "time_of_day": time},
    )
    assert res.status_code == 200, res.text


def test_dinner_reminder_rings_the_household_once(
    owner, parent, child, configured, push_outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    child.put("/push/subscription", json={"endpoint": "https://push.example/kid", "keys": {"p256dh": "k3", "auth": "a3"}})
    set_dinner(owner)

    assert push_engine.digest_tick(at(17, 15)) == 0  # 45 min out, lead is 30
    assert push_engine.digest_tick(at(17, 40)) == 2  # both adults, never the kid
    payloads = {ep: p for ep, p in push_outbox}
    assert payloads[SUB["endpoint"]]["title"] == "Dinner at 6:00 PM"
    assert payloads[SUB["endpoint"]]["body"] == "Tacos"
    # Once per evening, even while still inside the window.
    assert push_engine.digest_tick(at(17, 50)) == 0
    # And not after dinner time itself.
    assert push_engine.digest_tick(at(18, 10)) == 0


def test_dinner_reminder_respects_the_pref(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/prefs", json={"prefs": {"dinner": False}})
    set_dinner(owner)
    assert push_engine.digest_tick(at(17, 40)) == 0


def test_a_time_only_plan_still_reminds(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    res = owner.put(
        "/meals/time",
        json={"date_for": TODAY.isoformat(), "slot": "dinner", "time_of_day": "18:00:00"},
    )
    assert res.status_code == 200, res.text
    assert push_engine.digest_tick(at(17, 40)) == 1
    assert push_outbox[0][1]["title"] == "Dinner at 6:00 PM"
    assert push_outbox[0][1]["body"] == ""


# ---- the sync-went-quiet nudge --------------------------------------------------


def stale_token(client, engine_db, days=3):
    assert client.post("/me/fitness/token").status_code == 200
    with engine_db() as db:
        token = db.get(IngestToken, user_id(client))
        token.last_used_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        db.commit()


def test_quiet_sync_nudges_its_owner_weekly(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    stale_token(owner, engine_db)

    assert push_engine.digest_tick(at(7)) == 1
    _endpoint, payload = push_outbox[0]
    assert payload["title"] == "Health sync has gone quiet"
    assert payload["body"] == (
        "No health data from your phone in 3 days."
        " Open your sync app and check its automation."
    )
    assert push_engine.digest_tick(at(8)) == 0  # claimed for the day

    # Days later it's still stale — but a nudge in the last week keeps quiet.
    with engine_db() as db:
        row = db.query(DigestLog).filter_by(kind="sync").one()
        row.date_for = TODAY - dt.timedelta(days=2)
        db.commit()
    assert push_engine.digest_tick(at(9)) == 0
    # Once the last nudge is over a week old, it speaks again.
    with engine_db() as db:
        row = db.query(DigestLog).filter_by(kind="sync").one()
        row.date_for = TODAY - dt.timedelta(days=8)
        db.commit()
    assert push_engine.digest_tick(at(10)) == 1


def test_fresh_sync_and_no_token_stay_quiet(owner, parent, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)  # never minted a token
    stale_token(owner, engine_db, days=0)  # synced just now

    assert push_engine.digest_tick(at(7)) == 0
    assert push_outbox == []


def test_sync_nudge_respects_the_pref(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/prefs", json={"prefs": {"sync": False}})
    stale_token(owner, engine_db)
    assert push_engine.digest_tick(at(7)) == 0


# ---- the verse-streak-at-risk word ----------------------------------------------


def seed_streak(client, engine_db, days_back=(1, 2)):
    assert client.put("/me/verses/settings", json={"enabled": True}).status_code == 200
    with engine_db() as db:
        for back in days_back:
            for idx in range(3):
                db.add(
                    VerseCheck(
                        user_id=user_id(client),
                        date_for=TODAY - dt.timedelta(days=back),
                        verse_idx=idx,
                    )
                )
        db.commit()


def test_streak_at_risk_gets_an_evening_word(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    seed_streak(owner, engine_db)  # yesterday + the day before: a 2-day chain

    assert push_engine.digest_tick(at(19)) == 2  # the check-in and the word
    titles = {p["title"]: p for _, p in push_outbox}
    assert titles["Tonight's reading"]["body"] == "Your 2-day verse streak ends at midnight."
    assert push_engine.digest_tick(at(20)) == 0  # once per evening


def test_verses_already_read_stay_quiet(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    seed_streak(owner, engine_db, days_back=(0, 1, 2))  # today's done too

    assert push_engine.digest_tick(at(19)) == 1  # just the evening check-in
    assert push_outbox[0][1]["title"] == "Evening check-in"


def test_a_phone_already_past_midnight_counts_as_read(owner, configured, push_outbox, engine_db):
    # The member's phone checked off "tomorrow" (one day of drift is allowed
    # on writes): the chain is safe, so no midnight warning tonight.
    owner.put("/push/subscription", json=SUB)
    seed_streak(owner, engine_db, days_back=(-1, 1, 2))

    assert push_engine.digest_tick(at(19)) == 1
    assert push_outbox[0][1]["title"] == "Evening check-in"


def test_short_streaks_and_non_readers_are_left_alone(
    owner, parent, configured, push_outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    seed_streak(owner, engine_db, days_back=(1,))  # a 1-day chain: not yet a streak
    # The second parent never opted into verses at all.

    assert push_engine.digest_tick(at(19)) == 2  # two evening check-ins, no words
    assert {p["title"] for _, p in push_outbox} == {"Evening check-in"}


def test_verse_word_respects_the_pref(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/prefs", json={"prefs": {"verse": False}})
    seed_streak(owner, engine_db)

    assert push_engine.digest_tick(at(19)) == 1
    assert push_outbox[0][1]["title"] == "Evening check-in"
