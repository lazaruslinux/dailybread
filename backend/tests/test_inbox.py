"""The Inbox: history rows land at the curated event sites (independently of
push config and prefs), unread counts and read-all behave, kids read their
own, families never see each other's, and retention prunes."""

import datetime as dt

from sqlalchemy.orm import sessionmaker

import app.push as push_engine
from app import inbox as inbox_engine
from app.models import InboxEntry, User
from tests.conftest import user_id

TODAY = dt.date.today()

SUB = {
    "endpoint": "https://push.example/inbox-device",
    "keys": {"p256dh": "client-public-key", "auth": "client-auth-secret"},
}


def entries(client) -> list[dict]:
    res = client.get("/me/inbox")
    assert res.status_code == 200, res.text
    return res.json()


def unread(client) -> int:
    res = client.get("/me/inbox/unread")
    assert res.status_code == 200, res.text
    return res.json()["count"]


def make_item(client, **overrides):
    # Family-visible: a private card has no audience, so nothing would record.
    payload = {"kind": "task", "title": "Rake the yard", "visibility": "family", **overrides}
    res = client.post("/items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def complete(client, item_id, for_user=None):
    url = f"/items/{item_id}/complete?date={TODAY.isoformat()}"
    if for_user is not None:
        url += f"&for={for_user}"
    res = client.post(url)
    assert res.status_code == 200, res.text
    return res.json()


# ---- board changes ---------------------------------------------------------------


def test_board_add_lands_in_the_other_parents_inbox(owner, parent, child):
    make_item(owner)
    # The `child` fixture also left a `member` line for the parent; filter to
    # the board line under test.
    rows = [r for r in entries(parent) if r["kind"] == "board"]
    assert len(rows) == 1
    assert "added a task: Rake the yard" in rows[0]["title"]
    assert rows[0]["read"] is False
    # The actor doesn't hear their own news; kids aren't in the board audience.
    assert [r for r in entries(owner) if r["kind"] == "board"] == []
    assert entries(child) == []


def test_reschedule_and_delete_each_write_a_line(owner, parent):
    item = make_item(owner, date_for=TODAY.isoformat())
    owner.patch(f"/items/{item['id']}", json={"date_for": (TODAY + dt.timedelta(days=1)).isoformat()})
    owner.delete(f"/items/{item['id']}")
    titles = [r["title"] for r in entries(parent)]
    assert len(titles) == 3  # added, rescheduled, removed — newest first
    assert "removed" in titles[0]
    assert "rescheduled" in titles[1]


def test_routines_write_board_history(owner, parent):
    # Routines are the board's daily heartbeat: they never PUSH, but they DO
    # write Inbox history now (create, then an adult completion).
    res = owner.post(
        "/items",
        json={
            "kind": "routine",
            "title": "Brush teeth",
            "visibility": "family",
            "repeat": {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
        },
    )
    assert res.status_code == 201, res.text
    complete(owner, res.json()["id"])
    rows = [r for r in entries(parent) if r["kind"] == "board"]
    assert len(rows) == 2  # "added a routine", then "completed a routine"
    assert all("routine" in r["title"] for r in rows)


# ---- dinner ------------------------------------------------------------------------


def test_dinner_lock_writes_a_line_for_the_family_adults(owner, parent, child):
    res = owner.put("/meals", json={"date_for": TODAY.isoformat(), "custom_title": "Tacos"})
    assert res.status_code == 200, res.text
    rows = [r for r in entries(parent) if r["kind"] == "dinner"]
    assert len(rows) == 1
    assert "locked in dinner" in rows[0]["title"]
    assert rows[0]["body"] == "Tacos"
    assert [r for r in entries(owner) if r["kind"] == "dinner"] == []
    assert entries(child) == []


# ---- workouts ----------------------------------------------------------------------


def _workout_payload(duration_s: int) -> dict:
    stamp = lambda hhmmss: f"{TODAY.isoformat()} {hhmmss} -0700"
    return {
        "data": {
            "workouts": [
                {
                    "id": f"wk-inbox-{duration_s}",
                    "name": "Outdoor Run",
                    "start": stamp("06:30:00"),
                    "end": stamp("07:05:00"),
                    "duration": duration_s,
                }
            ]
        }
    }


def test_workout_sync_writes_family_line_and_athletes_crumb_line(owner, parent, child):
    token = owner.post("/me/fitness/token").json()["token"]
    res = owner.post(
        "/ingest/health",
        json=_workout_payload(2100),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    rows = [r for r in entries(parent) if r["kind"] == "workout"]
    assert len(rows) == 1
    assert "completed a workout" in rows[0]["title"]
    assert entries(child) == []
    mine = entries(owner)
    assert len(mine) == 1
    assert mine[0]["kind"] == "crumb"
    assert mine[0]["title"] == "+3 crumbs"
    assert mine[0]["body"] == "You finished a workout"
    # The re-sync neither pays nor repeats.
    owner.post(
        "/ingest/health",
        json=_workout_payload(2100),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(entries(owner)) == 1
    assert len([r for r in entries(parent) if r["kind"] == "workout"]) == 1


# ---- approvals and the kid payoff ---------------------------------------------------


def test_kid_checkoff_lands_pending_in_every_parents_inbox(owner, parent, child):
    item = make_item(owner, assignee_ids=[user_id(child)])
    for c in (owner, parent):
        c.post("/me/inbox/read")  # clear the "added" line
    complete(child, item["id"])
    for c in (owner, parent):
        rows = [r for r in entries(c) if r["kind"] == "pending"]
        assert len(rows) == 1
        assert "finished: Rake the yard" in rows[0]["title"]
        assert rows[0]["body"] == "Waiting on your approval"


def test_approval_writes_the_kids_payoff_line(owner, child):
    item = make_item(owner, assignee_ids=[user_id(child)])
    complete(child, item["id"])
    assert entries(child) == []  # nothing yet — pending is the parents' news
    complete(owner, item["id"])  # the approval
    rows = entries(child)
    # The payoff line plus the kid's own +1 crumb line, newest first is fine
    # either way — assert by kind.
    kinds = {r["kind"] for r in rows}
    assert "approved" in kinds
    payoff = next(r for r in rows if r["kind"] == "approved")
    assert "approved: Rake the yard" in payoff["title"]
    assert payoff["body"] == "+1 crumb"
    # Completing an already-official card again writes nothing more.
    complete(owner, item["id"])
    assert len(entries(child)) == len(rows)


def test_parent_completing_for_a_kid_writes_the_kids_line(owner, child):
    # ?for= is a routine-only power; on other kinds the tap is the tapper's.
    routine = make_item(
        owner,
        kind="routine",
        title="Rake the yard",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
        assignee_ids=[user_id(child)],
    )
    complete(owner, routine["id"], for_user=user_id(child))
    rows = [r for r in entries(child) if r["kind"] == "approved"]
    assert len(rows) == 1
    assert "checked off: Rake the yard" in rows[0]["title"]
    assert rows[0]["body"] == "+1 crumb"


# ---- crumb earns ---------------------------------------------------------------------


def test_verse_and_diary_crumbs_write_lines_but_login_does_not(owner):
    owner.get("/auth/me")  # the daily login +1
    assert entries(owner) == []  # login is deliberately silent
    assert owner.put("/me/verses/settings", json={"enabled": True}).status_code == 200
    for idx in range(3):
        owner.post("/me/verses/check", json={"date_for": TODAY.isoformat(), "verse_idx": idx})
    rows = entries(owner)
    assert len(rows) == 1
    assert rows[0]["kind"] == "crumb"
    assert rows[0]["title"] == "+3 crumbs"
    assert rows[0]["body"] == "You read the daily verses"
    # Diary lock pays +2 and says so.
    owner.post(
        "/diary",
        json={
            "date_for": TODAY.isoformat(),
            "slot": "breakfast",
            "amount": 100,
            "unit": "g",
            "source": "usda",
            "source_id": "111222",
            "name": "Rolled Oats",
            "brand": "",
            "calories": 100.0,
            "protein_g": 10.0,
            "carbs_g": 20.0,
            "fat_g": 2.0,
        },
    )
    owner.post(f"/diary/lock?date={TODAY.isoformat()}")
    rows = entries(owner)
    assert rows[0]["title"] == "+2 crumbs"
    assert rows[0]["body"] == "You locked in your day"


# ---- independence from push ----------------------------------------------------------


def test_prefs_off_still_records_history(owner, parent, configured, outbox):
    parent.put("/push/subscription", json=SUB)
    parent.put("/push/prefs", json={"prefs": {"family": False}})
    make_item(owner)
    assert outbox == []  # the pref silenced the phone
    assert len(entries(parent)) == 1  # but history still happened


def test_reminders_and_digests_write_no_history(owner, configured, outbox, engine_db):
    owner.put("/push/subscription", json=SUB)
    make_item(owner, date_for=TODAY.isoformat(), time_of_day="09:00")
    before = unread(owner)
    now = dt.datetime.now()
    push_engine.reminder_tick(now)
    push_engine.digest_tick(now.replace(hour=7, minute=0))
    assert unread(owner) == before


# ---- unread / read-all ------------------------------------------------------------


def test_unread_counts_and_read_all_clears(owner, parent):
    make_item(owner)
    make_item(owner, title="Water the garden")
    assert unread(parent) == 2
    assert all(r["read"] is False for r in entries(parent))
    res = parent.post("/me/inbox/read")
    assert res.status_code == 204
    assert unread(parent) == 0
    assert all(r["read"] is True for r in entries(parent))
    # And the actor's own unread stayed untouched throughout.
    assert unread(owner) == 0


def test_minors_can_read_their_inbox(child):
    assert child.get("/me/inbox").status_code == 200
    assert child.get("/me/inbox/unread").status_code == 200
    assert child.post("/me/inbox/read").status_code == 204


def test_families_never_see_each_others_history(owner, parent, other):
    make_item(owner)
    assert entries(other) == []
    assert unread(other) == 0


# ---- clear -----------------------------------------------------------------------


def test_clear_deletes_only_my_rows(owner, parent):
    make_item(owner)  # a board line for the other parent
    make_item(parent)  # a board line back for the owner
    assert len(entries(parent)) == 1
    assert len(entries(owner)) == 1
    assert parent.delete("/me/inbox").status_code == 204
    assert entries(parent) == []
    # the other member's history is untouched
    assert len(entries(owner)) == 1


def test_a_minor_clears_their_own_inbox(owner, child):
    item = make_item(owner, assignee_ids=[user_id(child)])
    complete(child, item["id"])  # pending -> parents
    complete(owner, item["id"])  # approval -> the kid's payoff line
    assert unread(child) >= 1
    assert child.delete("/me/inbox").status_code == 204
    assert entries(child) == []
    assert unread(child) == 0


def test_clearing_an_empty_inbox_is_still_204(owner):
    assert entries(owner) == []  # the actor hears none of their own news
    assert owner.delete("/me/inbox").status_code == 204
    assert owner.delete("/me/inbox").status_code == 204


# ---- board: edits, uncomplete, uncancel, withdrawal, privacy ----------------------


def test_title_only_edit_writes_one_line(owner, parent):
    item = make_item(owner, date_for=TODAY.isoformat())
    parent.delete("/me/inbox")  # drop the "added" line
    owner.patch(f"/items/{item['id']}", json={"title": "Rake the leaves"})
    rows = [r for r in entries(parent) if r["kind"] == "board"]
    assert len(rows) == 1
    assert "edited a task: Rake the leaves" in rows[0]["title"]
    assert rows[0]["body"] == 'Was "Rake the yard"'


def test_reschedule_plus_title_in_one_patch_writes_only_one_line(owner, parent):
    item = make_item(owner, date_for=TODAY.isoformat())
    parent.delete("/me/inbox")
    owner.patch(
        f"/items/{item['id']}",
        json={"title": "New name", "date_for": (TODAY + dt.timedelta(days=1)).isoformat()},
    )
    rows = [r for r in entries(parent) if r["kind"] == "board"]
    assert len(rows) == 1  # the reschedule wins; never a second edit line
    assert "rescheduled" in rows[0]["title"]


def test_uncomplete_and_uncancel_record(owner, parent):
    item = make_item(
        owner, kind="activity", title="Park day", date_for=TODAY.isoformat(),
        time_of_day="10:00:00", end_time="12:00:00",
    )
    complete(owner, item["id"])
    parent.delete("/me/inbox")
    owner.delete(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    rows = [r for r in entries(parent) if r["kind"] == "board"]
    assert len(rows) == 1
    assert "unchecked an activity: Park day" in rows[0]["title"]

    owner.post(f"/items/{item['id']}/cancel?date={TODAY.isoformat()}")
    parent.delete("/me/inbox")
    owner.delete(f"/items/{item['id']}/cancel?date={TODAY.isoformat()}")
    rows = [r for r in entries(parent) if r["kind"] == "board"]
    assert len(rows) == 1
    assert "put back on: Park day" in rows[0]["title"]


def test_kid_withdrawal_notifies_every_parent(owner, parent, child):
    item = make_item(owner, assignee_ids=[user_id(child)])
    complete(child, item["id"])  # pending
    for c in (owner, parent):
        c.delete("/me/inbox")
    child.delete(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    for c in (owner, parent):
        rows = [r for r in entries(c) if r["kind"] == "board"]
        assert len(rows) == 1
        assert "withdrew their check-off: Rake the yard" in rows[0]["title"]


def test_kid_routine_approval_adds_no_extra_board_line(owner, parent, child):
    routine = make_item(
        owner,
        kind="routine",
        assignee_ids=[user_id(child)],
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )
    complete(child, routine["id"])  # pending -> parents
    for c in (owner, parent):
        c.delete("/me/inbox")
    complete(owner, routine["id"], for_user=user_id(child))  # the approval
    # The kid gets the payoff line; the other parent gets NO board line.
    assert [r for r in entries(parent) if r["kind"] == "board"] == []
    assert any(r["kind"] == "approved" for r in entries(child))


def test_private_card_edits_and_unchecks_leak_nothing(owner, parent):
    res = owner.post(
        "/items", json={"kind": "task", "title": "Secret gift", "date_for": TODAY.isoformat()}
    )
    item = res.json()  # private to the owner
    owner.patch(f"/items/{item['id']}", json={"title": "Secret present"})
    complete(owner, item["id"])
    owner.delete(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    assert entries(parent) == []  # the other parent can't see it, so hears nothing


# ---- grocery ----------------------------------------------------------------------


def test_grocery_add_and_delete_record_to_the_other_parent(owner, parent, child):
    item_id = owner.post("/grocery", json={"title": "Milk"}).json()["id"]
    rows = [r for r in entries(parent) if r["kind"] == "grocery"]
    assert len(rows) == 1
    assert "added to groceries: Milk" in rows[0]["title"]
    assert rows[0]["body"] == "General"
    # The actor never hears their own, and a kid is never in the grocery audience.
    assert [r for r in entries(owner) if r["kind"] == "grocery"] == []
    assert entries(child) == []

    parent.delete("/me/inbox")
    owner.delete(f"/grocery/{item_id}")
    rows = [r for r in entries(parent) if r["kind"] == "grocery"]
    assert len(rows) == 1
    assert "removed from groceries: Milk" in rows[0]["title"]


def test_grocery_patch_toggle_records_nothing(owner, parent):
    item_id = owner.post("/grocery", json={"title": "Eggs"}).json()["id"]
    parent.delete("/me/inbox")
    owner.patch(f"/grocery/{item_id}", json={"checked": True})
    assert [r for r in entries(parent) if r["kind"] == "grocery"] == []


def test_stores_and_clear_checked_record(owner, parent):
    store = owner.post("/grocery/lists", json={"name": "Costco"}).json()
    rows = [r for r in entries(parent) if r["kind"] == "grocery"]
    assert any("added a store: Costco" in r["title"] for r in rows)

    owner.post("/grocery", json={"title": "Bread", "list_id": store["id"]})
    item2 = owner.post("/grocery", json={"title": "Butter", "list_id": store["id"]}).json()
    owner.patch(f"/grocery/{item2['id']}", json={"checked": True})
    parent.delete("/me/inbox")
    owner.post(f"/grocery/clear-checked?list_id={store['id']}")
    rows = [r for r in entries(parent) if r["kind"] == "grocery"]
    assert len(rows) == 1
    assert "cleared checked-off groceries" in rows[0]["title"]
    assert rows[0]["body"] == "1 item · Costco"

    parent.delete("/me/inbox")
    owner.delete(f"/grocery/lists/{store['id']}")
    rows = [r for r in entries(parent) if r["kind"] == "grocery"]
    assert len(rows) == 1
    assert "removed a store: Costco" in rows[0]["title"]
    assert rows[0]["body"] == "Its items moved to General"


def test_empty_clear_checked_records_nothing(owner, parent):
    parent.delete("/me/inbox")
    assert owner.post("/grocery/clear-checked").status_code == 200
    assert [r for r in entries(parent) if r["kind"] == "grocery"] == []


# ---- meals: votes, times, unplan --------------------------------------------------


def test_kid_dinner_vote_records_to_both_parents(owner, parent, child):
    for c in (owner, parent):
        c.delete("/me/inbox")
    res = child.put(
        f"/meals/plan?date={TODAY.isoformat()}",
        json={"choice": "go_out", "detail": "Pizza place", "recipe_id": None},
    )
    assert res.status_code == 200, res.text
    for c in (owner, parent):
        rows = [r for r in entries(c) if r["kind"] == "dinner"]
        assert len(rows) == 1
        assert "voted for dinner" in rows[0]["title"]
        assert "Going out" in rows[0]["body"] and "Pizza place" in rows[0]["body"]

    # Re-casting the identical ballot is not news: no second line.
    for c in (owner, parent):
        c.delete("/me/inbox")
    res = child.put(
        f"/meals/plan?date={TODAY.isoformat()}",
        json={"choice": "go_out", "detail": "Pizza place", "recipe_id": None},
    )
    assert res.status_code == 200, res.text
    for c in (owner, parent):
        assert [r for r in entries(c) if r["kind"] == "dinner"] == []


def test_retract_dinner_vote_records(owner, parent):
    owner.put(
        f"/meals/plan?date={TODAY.isoformat()}",
        json={"choice": "self_serve", "detail": "", "recipe_id": None},
    )
    parent.delete("/me/inbox")
    owner.delete(f"/meals/plan?date={TODAY.isoformat()}")
    rows = [r for r in entries(parent) if r["kind"] == "dinner"]
    assert len(rows) == 1
    assert "took back their dinner vote" in rows[0]["title"]


def test_meal_time_set_and_clear_record(owner, parent):
    parent.delete("/me/inbox")
    owner.put(
        "/meals/time",
        json={"date_for": TODAY.isoformat(), "slot": "dinner", "time_of_day": "18:00"},
    )
    rows = [r for r in entries(parent) if r["kind"] == "dinner"]
    assert len(rows) == 1
    assert "set a dinner time" in rows[0]["title"]

    parent.delete("/me/inbox")
    owner.put(
        "/meals/time",
        json={"date_for": TODAY.isoformat(), "slot": "dinner", "time_of_day": None},
    )
    rows = [r for r in entries(parent) if r["kind"] == "dinner"]
    assert len(rows) == 1
    assert "cleared the dinner time" in rows[0]["title"]


def test_unplanning_a_picked_night_records(owner, parent):
    owner.put("/meals", json={"date_for": TODAY.isoformat(), "custom_title": "Tacos"})
    parent.delete("/me/inbox")
    owner.delete(f"/meals?date={TODAY.isoformat()}")
    rows = [r for r in entries(parent) if r["kind"] == "dinner"]
    assert len(rows) == 1
    assert "unplanned dinner" in rows[0]["title"]
    assert rows[0]["body"].startswith("Tacos")


def test_breakfast_plan_records_but_never_pushes(owner, parent, configured, push_outbox):
    parent.put("/push/subscription", json=SUB)
    owner.put(
        "/meals",
        json={"date_for": TODAY.isoformat(), "slot": "breakfast", "custom_title": "Oatmeal"},
    )
    assert push_outbox == []  # only dinner is a lock-in that rings
    rows = [r for r in entries(parent) if r["kind"] == "dinner"]
    assert len(rows) == 1
    assert "planned breakfast: Oatmeal" in rows[0]["title"]

    # Re-saving the same pick is not news: no second line.
    parent.delete("/me/inbox")
    owner.put(
        "/meals",
        json={"date_for": TODAY.isoformat(), "slot": "breakfast", "custom_title": "Oatmeal"},
    )
    assert [r for r in entries(parent) if r["kind"] == "dinner"] == []


def test_dinner_lock_still_pushes(owner, parent, configured, push_outbox):
    parent.put("/push/subscription", json=SUB)
    owner.put("/meals", json={"date_for": TODAY.isoformat(), "custom_title": "Tacos"})
    assert [ep for ep, _ in push_outbox] == [SUB["endpoint"]]
    assert "locked in dinner" in push_outbox[0][1]["title"]


# ---- recipes ----------------------------------------------------------------------


def _make_recipe(client, name="Taco Bowls"):
    line = {
        "source": "usda", "source_id": "12345", "name": "Beef", "brand": "",
        "calories": 250.0, "protein_g": 26.0, "carbs_g": 0.0, "fat_g": 17.0,
        "amount": 200, "unit": "g",
    }
    res = client.post(
        "/recipes",
        json={"name": name, "servings": 4, "steps": "Cook.", "ingredients": [line]},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_recipe_create_rename_delete_record(owner, parent):
    made = _make_recipe(owner, name="Chili")
    rows = [r for r in entries(parent) if r["kind"] == "recipe"]
    assert len(rows) == 1
    assert "added a recipe: Chili" in rows[0]["title"]

    parent.delete("/me/inbox")
    owner.patch(f"/recipes/{made['id']}", json={"name": "Beef Chili"})
    rows = [r for r in entries(parent) if r["kind"] == "recipe"]
    assert len(rows) == 1
    assert "edited a recipe: Beef Chili" in rows[0]["title"]
    assert rows[0]["body"] == 'Was "Chili"'

    # A re-save that changes nothing is not an edit: no second line.
    parent.delete("/me/inbox")
    owner.patch(f"/recipes/{made['id']}", json={"name": "Beef Chili", "steps": "Cook."})
    assert [r for r in entries(parent) if r["kind"] == "recipe"] == []

    parent.delete("/me/inbox")
    owner.delete(f"/recipes/{made['id']}")
    rows = [r for r in entries(parent) if r["kind"] == "recipe"]
    assert len(rows) == 1
    assert "removed a recipe: Beef Chili" in rows[0]["title"]


def test_send_recipe_to_grocery_records_the_count(owner, parent):
    made = _make_recipe(owner)
    parent.delete("/me/inbox")
    res = owner.post(f"/recipes/{made['id']}/grocery", json={})
    assert res.status_code == 200, res.text
    rows = [r for r in entries(parent) if r["kind"] == "grocery"]
    assert len(rows) == 1
    assert "sent Taco Bowls to groceries" in rows[0]["title"]
    assert rows[0]["body"] == "1 ingredient"


# ---- village + family membership --------------------------------------------------


def _villaged(owner, other, name="Bread Circle"):
    created = owner.post("/villages", json={"name": name}).json()
    res = other.post("/villages/join", json={"code": created["invite_code"]})
    assert res.status_code == 200, res.text
    return created["id"]


def test_village_join_notifies_the_existing_family_only(owner, other):
    created = owner.post("/villages", json={"name": "Bread Circle"}).json()
    other.post("/villages/join", json={"code": created["invite_code"]})
    rows = [r for r in entries(owner) if r["kind"] == "village"]
    assert len(rows) == 1
    assert "The Bs joined Bread Circle" in rows[0]["title"]
    # The joining family hears nothing about its own arrival.
    assert [r for r in entries(other) if r["kind"] == "village"] == []


def test_share_recipe_notifies_the_other_family_only(owner, other):
    vid = _villaged(owner, other)
    made = _make_recipe(owner, name="Pancakes")
    owner.delete("/me/inbox")
    res = owner.post(f"/villages/{vid}/recipes", json={"recipe_id": made["id"]})
    assert res.status_code == 201, res.text
    rows = [r for r in entries(other) if r["kind"] == "village"]
    assert len(rows) == 1
    assert "shared a recipe: Pancakes" in rows[0]["title"]
    assert rows[0]["body"] == "On Bread Circle's shelf"
    assert [r for r in entries(owner) if r["kind"] == "village"] == []


def test_save_a_copy_notifies_the_sharer_inbox_only(owner, other, configured, push_outbox):
    owner.put("/push/subscription", json=SUB)
    vid = _villaged(owner, other)
    made = _make_recipe(owner, name="Pancakes")
    entry = owner.post(f"/villages/{vid}/recipes", json={"recipe_id": made["id"]}).json()
    owner.delete("/me/inbox")
    push_outbox.clear()
    res = other.post(f"/villages/shelf/{entry['share_id']}/copy")
    assert res.status_code == 201, res.text
    rows = [r for r in entries(owner) if r["kind"] == "recipe"]
    assert len(rows) == 1
    assert "The Bs saved your recipe: Pancakes" in rows[0]["title"]
    assert push_outbox == []  # a quiet payoff, never a push


def test_unshare_is_silent(owner, other):
    vid = _villaged(owner, other)
    made = _make_recipe(owner, name="Pancakes")
    entry = owner.post(f"/villages/{vid}/recipes", json={"recipe_id": made["id"]}).json()
    owner.delete("/me/inbox")
    other.delete("/me/inbox")
    assert owner.delete(f"/villages/shelf/{entry['share_id']}").status_code == 204
    assert entries(owner) == []
    assert [r for r in entries(other) if r["kind"] == "village"] == []


def test_new_member_records_for_the_other_parent_only(owner, parent):
    for c in (owner, parent):
        c.delete("/me/inbox")
    res = owner.post(
        "/auth/users",
        json={
            "username": "auntie", "display_name": "Auntie May",
            "password": "auntie-pass-1", "role": "parent",
        },
    )
    assert res.status_code == 201, res.text
    rows = [r for r in entries(parent) if r["kind"] == "member"]
    assert len(rows) == 1
    assert "Auntie May joined the family" in rows[0]["title"]
    assert rows[0]["body"] == "Added by Owner"
    # The admin who added them is not told, and it's inbox-only anyway.
    assert [r for r in entries(owner) if r["kind"] == "member"] == []


def test_new_household_records_nothing(owner):
    owner.delete("/me/inbox")
    res = owner.post(
        "/auth/users",
        json={
            "username": "newhh", "display_name": "New Household",
            "password": "newhh-pass-1", "role": "parent", "new_household": True,
        },
    )
    assert res.status_code == 201, res.text
    assert entries(owner) == []


# ---- retention -----------------------------------------------------------------------


def test_retention_keeps_the_newest_three_hundred(app, owner):
    uid = user_id(owner)
    Session = sessionmaker(bind=app.state.test_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        fid = db.get(User, uid).family_id
        # One commit per record, mirroring the real call sites — the prune
        # reads committed rows, so a single mega-transaction would dodge it.
        for n in range(305):
            inbox_engine.record(db, uid, fid, "board", f"Line {n}")
            db.commit()
        kept = db.query(InboxEntry).filter(InboxEntry.user_id == uid).count()
        assert kept == inbox_engine.MAX_PER_USER == 300
        oldest = (
            db.query(InboxEntry)
            .filter(InboxEntry.user_id == uid)
            .order_by(InboxEntry.id.asc())
            .first()
        )
        assert oldest.title == "Line 5"
    finally:
        db.close()
