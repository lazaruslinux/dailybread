"""Per-kind push preferences and the scheduled kinds they gate: past-due
alerts, the check-ins, the sync timeout, and the streak reminder. Prefs
subtract from a default of everything-on; a missing key always reads as on,
so new kinds never need a backfill.
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
    res = owner.put("/push/prefs", json={"prefs": {"evening": False}})
    assert res.status_code == 200
    prefs = res.json()["prefs"]
    assert prefs["evening"] is False
    assert prefs["morning"] is True
    # A second partial update doesn't resurrect the first.
    owner.put("/push/prefs", json={"prefs": {"family": False}})
    prefs = owner.get("/push/prefs").json()["prefs"]
    assert prefs == {**prefs, "evening": False, "family": False}
    # And flipping back on really clears it.
    owner.put("/push/prefs", json={"prefs": {"evening": True, "family": True}})
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


# ---- past-due alerts ------------------------------------------------------------


YESTERDAY = TODAY - dt.timedelta(days=1)


def test_past_due_alert_fires_a_day_later_once(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    make(
        owner,
        title="Call the plumber",
        date_for=YESTERDAY.isoformat(),
        time_of_day="09:00:00",
    )
    push_outbox.clear()  # setup's board-change push isn't under test here
    assert push_engine.digest_tick(at(8)) == 0  # 23 hours: not yet
    assert push_engine.digest_tick(at(10)) == 1  # 25 hours: the nudge
    _ep, payload = push_outbox[0]
    assert payload["title"] == "Past due: Call the plumber"
    assert payload["body"] == "Was due yesterday at 9:00 AM and it's still open."
    assert push_engine.digest_tick(at(11)) == 0  # once, ever


def test_done_and_ancient_cards_never_alert(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    done = make(owner, title="Handled", date_for=YESTERDAY.isoformat(), time_of_day="09:00:00")
    owner.post(f"/items/{done['id']}/complete?date={TODAY.isoformat()}")
    push_outbox.clear()
    assert push_engine.digest_tick(at(10)) == 0

    # A card whose alert moment is itself more than a day old claims quietly:
    # the feature arriving over a backlog must not dogpile.
    with engine_db() as db:
        from app.models import Item as _Item

        row = db.query(_Item).filter_by(title="Handled").one()
        row.date_for = TODAY - dt.timedelta(days=3)
        db.commit()
    assert push_engine.digest_tick(at(10)) == 0


def test_past_due_alert_respects_the_pref(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    owner.put("/push/prefs", json={"prefs": {"overdue": False}})
    make(owner, title="Slipped", date_for=YESTERDAY.isoformat(), time_of_day="09:00:00")
    push_outbox.clear()
    assert push_engine.digest_tick(at(10)) == 0


# ---- the evening check-in ---------------------------------------------------


def test_evening_is_a_plain_question(owner, configured, push_outbox, engine_db):
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
    push_outbox.clear()
    assert push_engine.digest_tick(at(19)) == 1
    # No tomorrow preview, no agenda: the evening is for review, not planning.
    assert push_outbox[0][1]["body"] == "How was your day?"


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


def test_a_rescheduled_overdue_card_reminds_again(owner, configured, push_outbox, engine_db):
    """Moving an overdue card to a new day clears its ReminderLog claims: the
    past-due nudge held (item, today), which would otherwise swallow the fresh
    heads-up when the card is rescheduled onto today."""
    owner.put("/push/subscription", json=SUB)
    card = make(
        owner,
        title="Call the plumber",
        date_for=YESTERDAY.isoformat(),
        time_of_day="09:00:00",
    )
    push_outbox.clear()
    assert push_engine.digest_tick(at(10)) == 1  # the past-due nudge claims (item, TODAY)

    res = owner.patch(
        f"/items/{card['id']}",
        json={"date_for": TODAY.isoformat(), "time_of_day": "18:00:00"},
    )
    assert res.status_code == 200, res.text
    push_outbox.clear()  # the reschedule board-change push isn't under test

    assert push_engine.reminder_tick(dt.datetime.combine(TODAY, dt.time(17, 50))) == 1
    assert push_outbox[0][1]["title"] == "Call the plumber"
