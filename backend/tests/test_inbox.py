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
    rows = entries(parent)
    assert len(rows) == 1
    assert rows[0]["kind"] == "board"
    assert "added a task: Rake the yard" in rows[0]["title"]
    assert rows[0]["read"] is False
    # The actor doesn't hear their own news; kids aren't in the board audience.
    assert entries(owner) == []
    assert entries(child) == []


def test_reschedule_and_delete_each_write_a_line(owner, parent):
    item = make_item(owner, date_for=TODAY.isoformat())
    owner.patch(f"/items/{item['id']}", json={"date_for": (TODAY + dt.timedelta(days=1)).isoformat()})
    owner.delete(f"/items/{item['id']}")
    titles = [r["title"] for r in entries(parent)]
    assert len(titles) == 3  # added, rescheduled, removed — newest first
    assert "removed" in titles[0]
    assert "rescheduled" in titles[1]


def test_routines_stay_out_of_the_inbox(owner, parent):
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
    assert entries(parent) == []


# ---- dinner ------------------------------------------------------------------------


def test_dinner_lock_writes_a_line_for_the_family_adults(owner, parent, child):
    res = owner.put("/meals", json={"date_for": TODAY.isoformat(), "custom_title": "Tacos"})
    assert res.status_code == 200, res.text
    rows = entries(parent)
    assert len(rows) == 1
    assert rows[0]["kind"] == "dinner"
    assert "locked in dinner" in rows[0]["title"]
    assert rows[0]["body"] == "Tacos"
    assert entries(owner) == []
    assert entries(child) == []
    # Clearing the meal says nothing, same as push.
    owner.delete(f"/meals?date={TODAY.isoformat()}")
    assert len(entries(parent)) == 1


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
    rows = entries(parent)
    assert len(rows) == 1
    assert rows[0]["kind"] == "workout"
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
    assert len(entries(parent)) == 1


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


# ---- retention -----------------------------------------------------------------------


def test_retention_keeps_the_newest_hundred(app, owner):
    uid = user_id(owner)
    Session = sessionmaker(bind=app.state.test_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        fid = db.get(User, uid).family_id
        # One commit per record, mirroring the real call sites — the prune
        # reads committed rows, so a single mega-transaction would dodge it.
        for n in range(105):
            inbox_engine.record(db, uid, fid, "board", f"Line {n}")
            db.commit()
        kept = db.query(InboxEntry).filter(InboxEntry.user_id == uid).count()
        assert kept == inbox_engine.MAX_PER_USER
        oldest = (
            db.query(InboxEntry)
            .filter(InboxEntry.user_id == uid)
            .order_by(InboxEntry.id.asc())
            .first()
        )
        assert oldest.title == "Line 5"
    finally:
        db.close()
