"""The day's scheduled pushes: morning digest, mid-day check, evening check-in.

Morning: "Good morning, <name>! X items on today's board. Next up: <card> at
<time>. Tap to review & read your Daily Bread!" — open items only, Next up is
the next undone card whose time is still ahead. Midday and evening go only to
members actually using the food diary. Minors and empty boards stay silent,
and the claim log keeps each push to one per member per day whatever the
server does.
"""

import datetime as dt

import app.push as push_engine
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


def seed_day(owner):
    """A 6 AM routine (already passed at 7), an anytime task, a 3 PM visit."""
    make(
        owner,
        kind="routine",
        title="Morning run",
        time_of_day="06:00:00",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )
    make(owner, title="Call the plumber")
    make(
        owner,
        kind="appointment",
        title="Dentist",
        date_for=TODAY.isoformat(),
        time_of_day="15:00:00",
        end_time="15:30:00",
    )


def test_digest_summarizes_the_morning(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    seed_day(owner)

    assert push_engine.digest_tick(at(7)) == 1
    endpoint, payload = push_outbox[0]
    assert endpoint == SUB["endpoint"]
    assert payload["title"] == "Good morning, Owner!"
    # The 6 AM run already passed, so it counts but is never "next up".
    assert payload["body"] == (
        "3 items on today's board. Next up: Dentist at 3:00 PM."
        " Tap to review & read your Daily Bread!"
    )


def test_completed_items_do_not_count(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    seed_day(owner)
    # The run got done at 5:30, before the digest.
    feed = owner.get(f"/items/feed?date={TODAY.isoformat()}").json()
    run = next(i for i in feed["today"] if i["title"] == "Morning run")
    owner.post(f"/items/{run['id']}/complete?date={TODAY.isoformat()}")

    push_engine.digest_tick(at(7))
    assert "2 items on today's board" in push_outbox[0][1]["body"]
    assert "Morning run" not in push_outbox[0][1]["body"]


def test_one_digest_per_day(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    seed_day(owner)

    assert push_engine.digest_tick(at(7)) == 1
    assert push_engine.digest_tick(at(7, 6)) == 0
    assert push_engine.digest_tick(at(11)) == 0
    assert len(push_outbox) == 1


def test_morning_window_only(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    seed_day(owner)

    assert push_engine.digest_tick(at(6, 59)) == 0  # not yet
    assert push_engine.digest_tick(at(12)) == 0  # good morning is over
    assert push_outbox == []
    # A late server start still greets people mid-morning.
    assert push_engine.digest_tick(at(9)) == 1


def test_each_adult_gets_their_own(owner, parent, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    # One family-visible unassigned card: it's on everyone's board.
    make(owner, title="Grandma arrives", visibility="family", date_for=TODAY.isoformat())
    # And one private card of the owner's alone.
    make(owner, title="Sharpen the mower blade")

    assert push_engine.digest_tick(at(7)) == 2
    by_endpoint = dict(push_outbox)
    assert "2 items" in by_endpoint[SUB["endpoint"]]["body"]
    assert by_endpoint[SUB["endpoint"]]["title"] == "Good morning, Owner!"
    # The second parent sees only the family card — singular, and no Next up
    # since nothing of theirs carries a time.
    assert by_endpoint[SUB2["endpoint"]]["body"] == (
        "1 item on today's board. Tap to review & read your Daily Bread!"
    )
    assert by_endpoint[SUB2["endpoint"]]["title"] == "Good morning, Second!"


def test_minors_get_no_digest(owner, child, configured, push_outbox, engine_db):
    child.put("/push/subscription", json=SUB2)
    make(owner, title="Feed the dog", assignee_ids=[user_id(child)], date_for=TODAY.isoformat())

    assert push_engine.digest_tick(at(7)) == 0
    assert push_outbox == []


def test_empty_board_stays_quiet_all_morning(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)

    assert push_engine.digest_tick(at(7)) == 0
    # The claim landed with the empty board: a card added at 9 doesn't
    # trigger a belated "good morning" at 9:01.
    make(owner, title="Late addition")
    assert push_engine.digest_tick(at(9)) == 0
    assert push_outbox == []


def test_unsubscribed_members_are_skipped_but_not_burned(
    owner, parent, configured, push_outbox, engine_db
):
    # The second parent has no device yet at 7...
    owner.put("/push/subscription", json=SUB)
    make(owner, title="Grandma arrives", visibility="family", date_for=TODAY.isoformat())
    assert push_engine.digest_tick(at(7)) == 1

    # ...then enables push at 8 and still gets that day's digest.
    parent.put("/push/subscription", json=SUB2)
    assert push_engine.digest_tick(at(8)) == 1
    assert push_outbox[1][0] == SUB2["endpoint"]


# ---- the mid-day check and the evening check-in -------------------------------------

OATS = {
    "source": "usda",
    "source_id": "111222",
    "name": "Rolled Oats",
    "brand": "",
    "calories": 100.0,
    "protein_g": 10.0,
    "carbs_g": 20.0,
    "fat_g": 2.0,
    "sugar_g": 1.0,
}


def log_food(client, amount=100):
    res = client.post(
        "/diary",
        json={
            "date_for": TODAY.isoformat(),
            "slot": "breakfast",
            "amount": amount,
            "unit": "g",
            **OATS,
        },
    )
    assert res.status_code == 201, res.text


def test_midday_check_counts_calories_left(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    log_food(owner, amount=100)  # 100 kcal against the default 2,000 target

    assert push_engine.digest_tick(at(12)) == 1
    endpoint, payload = push_outbox[0]
    assert payload["title"] == "Mid-day check"
    assert payload["body"] == "What's for lunch? 1,900 calories left for the day."


def test_midday_over_budget_says_so(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    res = owner.put(
        "/diary/targets",
        json={"calories": 500, "protein_pct": 30, "carbs_pct": 40, "fat_pct": 30},
    )
    assert res.status_code == 200, res.text
    log_food(owner, amount=600)  # 600 kcal against a 500 target

    push_engine.digest_tick(at(12))
    assert push_outbox[0][1]["body"] == "What's for lunch? 100 calories over so far."


def test_midday_skips_non_trackers_for_good(owner, parent, configured, push_outbox, engine_db):
    # The second parent never logs food: no lunch nudge — and starting to log
    # AFTER noon doesn't trigger a belated one either (the claim landed).
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    log_food(owner)

    assert push_engine.digest_tick(at(12)) == 1
    log_food(parent)
    assert push_engine.digest_tick(at(13)) == 0
    assert [ep for ep, _ in push_outbox] == [SUB["endpoint"]]


def test_evening_checkin_asks_about_the_day(owner, parent, configured, push_outbox, engine_db):
    # Everyone's push, tracker or not - the day's sign-off.
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)

    assert push_engine.digest_tick(at(17)) == 0  # not yet: evenings start at 7
    assert push_engine.digest_tick(at(19)) == 2
    for _endpoint, payload in push_outbox:
        assert payload["title"] == "Evening check-in"
        assert payload["body"] == "How was your day?"
    # Once per evening.
    assert push_engine.digest_tick(at(20)) == 0
    assert len(push_outbox) == 2


def test_evening_window_closes_at_ten(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)

    assert push_engine.digest_tick(at(22)) == 0
    assert push_engine.digest_tick(at(21, 59)) == 1


def test_all_three_land_on_a_trackers_day(owner, configured, push_outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    seed_day(owner)
    log_food(owner)

    assert push_engine.digest_tick(at(7)) == 1
    assert push_engine.digest_tick(at(12, 30)) == 1
    assert push_engine.digest_tick(at(19)) == 1
    titles = [p["title"] for _, p in push_outbox]
    assert titles == ["Good morning, Owner!", "Mid-day check", "Evening check-in"]
