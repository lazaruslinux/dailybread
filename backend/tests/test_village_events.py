"""Shared village events: sharing gates, per-family RSVPs with attendee
lists, copy materialization and its organizer lock, timezone conversion,
propagation, cleanup, and the kid-avatar privacy wall."""

import datetime as dt

import pytest

from app import throttle
from app.clock import shift_schedule
from tests.conftest import CHILD, user_id

TODAY = dt.date.today()
TOMORROW = TODAY + dt.timedelta(days=1)


@pytest.fixture(autouse=True)
def _clean_throttle():
    throttle.clear()
    yield
    throttle.clear()


@pytest.fixture()
def village(owner, other):
    """Owner's family founds; family B (other/Josh) joins."""
    created = owner.post("/villages", json={"name": "Bread Circle"}).json()
    res = other.post("/villages/join", json={"code": created["invite_code"]})
    assert res.status_code == 200, res.text
    return created["id"]


def make_event(client, **overrides):
    payload = {
        "kind": "activity",
        "title": "Soccer practice",
        "visibility": "family",
        "date_for": TOMORROW.isoformat(),
        "time_of_day": "17:30",
        "end_time": "18:30",
        "location": "Riverside Park",
        **overrides,
    }
    res = client.post("/items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def share(client, village_id, item_id, expect=201):
    res = client.post(f"/villages/{village_id}/events", json={"item_id": item_id})
    assert res.status_code == expect, res.text
    return res.json() if expect == 201 else res


def rsvp(client, event_id, status_, attendees=None, expect=200):
    res = client.put(
        f"/villages/events/{event_id}/rsvp",
        json={"status": status_, "attendee_ids": attendees or []},
    )
    assert res.status_code == expect, res.text
    return res.json() if expect == 200 else res


def events(client):
    res = client.get("/villages/events")
    assert res.status_code == 200, res.text
    return res.json()


def feed_ids(client):
    feed = client.get(f"/items/feed?date={TODAY.isoformat()}").json()
    return {
        i["id"]: i
        for bucket in ("overdue", "today", "next7")
        for i in feed[bucket]
    }


def inbox_rows(client, kind=None):
    rows = client.get("/me/inbox").json()
    return [r for r in rows if kind is None or r["kind"] == kind]


# ---- sharing gates ---------------------------------------------------------------


def test_share_and_both_families_see_it(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    assert out["is_own"] is True and out["title"] == "Soccer practice"
    theirs = events(other)
    assert len(theirs) == 1
    ev = theirs[0]
    assert ev["is_own"] is False
    assert ev["organizer_family_name"] == "Home"
    assert ev["location"] == "Riverside Park"
    assert ev["my_rsvp"] is None and ev["rsvps"] == []


def test_share_guards(village, owner, other, child):
    item = make_event(owner)
    # kids never share
    assert child.post(f"/villages/{village}/events", json={"item_id": item["id"]}).status_code == 403
    # a village you're not in 404s
    assert owner.post("/villages/999/events", json={"item_id": item["id"]}).status_code == 404
    # another family's card 404s
    assert other.post(f"/villages/{village}/events", json={"item_id": item['id']}).status_code == 404
    # wrong kinds / undated / repeating are 400s
    task = owner.post("/items", json={"kind": "task", "title": "Nope"}).json()
    share(owner, village, task["id"], expect=400)
    # (an undated activity can't even be created — item validation upstream
    # already requires the date, so the share endpoint's own check is only
    # defense in depth)
    repeating_res = owner.post(
        "/items",
        json={
            "kind": "appointment", "title": "Weekly",
            "time_of_day": "10:00", "end_time": "10:30",
            "repeat": {"type": "weekly", "days": [TOMORROW.weekday()]},
        },
    )
    assert repeating_res.status_code == 201, repeating_res.text
    share(owner, village, repeating_res.json()["id"], expect=400)
    # double share 400s
    share(owner, village, item["id"])
    share(owner, village, item["id"], expect=400)


def test_private_card_shares_only_for_someone_who_can_see_it(village, owner, parent):
    """The share endpoint enforces the same visibility wall as every other
    item route: one parent's private card is invisible to the other parent,
    so it can't be published to a village by them either."""
    private = make_event(parent, visibility="private", title="Counseling")
    res = owner.post(f"/villages/{village}/events", json={"item_id": private["id"]})
    assert res.status_code == 404
    assert events(owner) == []
    # its owner can still share it (visible to them; village exposure is
    # their own explicit call)
    share(parent, village, private["id"])


def test_past_events_drop_off_the_list(village, owner, other):
    """The events list is upcoming-only end to end: the SQL cutoff prunes
    old history, the viewer-local filter trims yesterday, and direct paths
    (share/RSVP responses) still reach an old event by id."""
    old = make_event(owner, title="Long done", date_for=(TODAY - dt.timedelta(days=3)).isoformat())
    yesterday = make_event(owner, title="Just missed", date_for=(TODAY - dt.timedelta(days=1)).isoformat())
    out = share(owner, village, old["id"])  # share response reaches it by id
    share(owner, village, yesterday["id"])
    upcoming = make_event(owner)
    share(owner, village, upcoming["id"])
    assert [e["title"] for e in events(other)] == ["Soccer practice"]
    # RSVP on an old invite still answers (only_event_ids bypasses the cutoff)
    answered = rsvp(other, out["event_id"], "maybe")
    assert answered["title"] == "Long done"


def test_outsider_family_sees_nothing(village, owner, other, app):
    from tests.conftest import login

    item = make_event(owner)
    out = share(owner, village, item["id"])
    stranger_creds = {"username": "stranger", "display_name": "Stranger", "password": "stranger-pass-1"}
    res = owner.post("/auth/users", json={**stranger_creds, "role": "parent", "new_household": True})
    assert res.status_code == 201
    stranger = login(app, stranger_creds)
    stranger.post("/families", json={"name": "The Cs"})
    assert stranger.get("/villages/events").json() == []
    assert stranger.put(
        f"/villages/events/{out['event_id']}/rsvp", json={"status": "going", "attendee_ids": [user_id(stranger)]}
    ).status_code == 404
    assert stranger.delete(f"/villages/events/{out['event_id']}").status_code == 404


def test_minors_cannot_list_events(village, child):
    assert child.get("/villages/events").status_code == 403


# ---- RSVP lifecycle ---------------------------------------------------------------


def test_going_materializes_a_copy(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    assert ev["my_rsvp"] == "going"
    assert ev["my_item_id"] is not None
    copy = feed_ids(other)[ev["my_item_id"]]
    assert copy["title"] == "Soccer practice"
    assert copy["village_event_id"] == out["event_id"]
    assert copy["location"] == "Riverside Park"
    assert copy["visibility"] == "family"
    assert copy["assignees"] == []
    # the gold SHARED flag rides both sides: the copy and the source
    assert copy["village_shared"] is True
    assert feed_ids(owner)[item["id"]]["village_shared"] is True
    # an unshared card stays unflagged
    plain = make_event(owner, title="Just ours")
    assert feed_ids(owner)[plain["id"]]["village_shared"] is False
    # the organizer's own board is untouched (no duplicate)
    assert ev["my_item_id"] not in feed_ids(owner)


def test_leaving_going_removes_the_copy(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy_id = ev["my_item_id"]
    ev = rsvp(other, out["event_id"], "maybe")
    assert ev["my_rsvp"] == "maybe" and ev["my_item_id"] is None
    assert copy_id not in feed_ids(other)
    # back to going recreates the copy (sqlite may reuse the old row id)
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    assert ev["my_item_id"] is not None
    assert ev["my_item_id"] in feed_ids(other)


def test_rsvp_guards(village, owner, other, child):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    # host can't RSVP their own event
    rsvp(owner, out["event_id"], "going", [user_id(owner)], expect=400)
    # kids can't RSVP
    assert child.put(
        f"/villages/events/{out['event_id']}/rsvp", json={"status": "going", "attendee_ids": []}
    ).status_code == 403
    # going needs at least one attendee
    rsvp(other, out["event_id"], "going", [], expect=400)
    # attendees must be the answering family's own members
    rsvp(other, out["event_id"], "going", [user_id(owner)], expect=400)


def test_withdrawing_the_rsvp(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy_id = ev["my_item_id"]
    assert other.delete(f"/villages/events/{out['event_id']}/rsvp").status_code == 204
    assert copy_id not in feed_ids(other)
    assert events(other)[0]["my_rsvp"] is None
    # withdrawing again is a quiet no-op
    assert other.delete(f"/villages/events/{out['event_id']}/rsvp").status_code == 204


def test_second_parent_overwrites_the_family_answer(village, owner, other, app):
    from tests.conftest import login

    second = {"username": "beth", "display_name": "Beth B", "password": "beth-pass-1234"}
    assert other.post("/auth/users", json={**second, "role": "parent", "is_admin": False}).status_code == 201
    beth = login(app, second)
    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    ev = rsvp(beth, out["event_id"], "cant")
    mine = [r for r in ev["rsvps"] if r["family_id"] == user_id(beth) or True]
    ours = next(r for r in ev["rsvps"] if r["status"] == "cant")
    assert ours["set_by"] == "Beth"
    # one row per family: no lingering going entry
    assert len(ev["rsvps"]) == 1
    assert ev["my_item_id"] is None  # the copy left with the answer


# ---- attendees and the privacy wall ------------------------------------------------


def test_attendees_ship_shaped_by_the_kid_flag(village, owner, other, app):
    from tests.conftest import login

    kid = {"username": "bkid", "display_name": "Kenny B", "password": "bkid-pass-1234"}
    assert other.post("/auth/users", json={**kid, "role": "child"}).status_code == 201
    kid_id = other.get("/users?date=" + TODAY.isoformat()).json()
    kid_id = next(u["id"] for u in kid_id if u["display_name"] == "Kenny B")

    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other), kid_id])

    # The organizer's view: Josh whole, Kenny as a bare K.
    ev = next(e for e in events(owner) if e["event_id"] == out["event_id"])
    attendees = ev["rsvps"][0]["attendees"]
    parent_row = next(a for a in attendees if not a["is_minor"])
    kid_row = next(a for a in attendees if a["is_minor"])
    assert parent_row["name"] == "Josh" and parent_row["user_id"] == user_id(other)
    assert parent_row["avatar"] is True
    assert kid_row["user_id"] is None and kid_row["name"] is None
    assert kid_row["initial"] == "K" and kid_row["avatar"] is False

    # The answering family sees its own kid in full.
    ev_own = next(e for e in events(other) if e["event_id"] == out["event_id"])
    own_kid = next(a for a in ev_own["rsvps"][0]["attendees"] if a["is_minor"])
    assert own_kid["user_id"] == kid_id and own_kid["name"] == "Kenny B"

    # Opting the kid in changes what crosses the wall.
    assert other.put("/villages/kid-avatars", json={"shared": True}).status_code == 204
    ev = next(e for e in events(owner) if e["event_id"] == out["event_id"])
    kid_row = next(a for a in ev["rsvps"][0]["attendees"] if a["is_minor"])
    assert kid_row["user_id"] == kid_id and kid_row["name"] == "Kenny"
    assert kid_row["avatar"] is True


def test_kid_avatar_toggle_guards(village, owner, other, child):
    # kids can't flip the family switch
    assert child.put("/villages/kid-avatars", json={"shared": True}).status_code == 403
    # a parent flips their own household's switch
    assert owner.put("/villages/kid-avatars", json={"shared": True}).status_code == 204
    # and it's family-scoped: flipping OURS never opens the OTHER family's kids
    # (the shaped-attendees test pins the cross-family payload)
    assert owner.get("/families/me").json()["share_kid_avatars"] is True
    assert other.get("/families/me").json()["share_kid_avatars"] is False


def test_avatar_route_respects_the_kid_wall(village, owner, other, child, app, monkeypatch, tmp_path):
    from app import avatars
    from app.config import settings
    from sqlalchemy.orm import sessionmaker

    kid_id = user_id(child)
    # give the kid a stored avatar on disk + a version stamp
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    Session = sessionmaker(bind=app.state.test_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    from app.models import User as MUser

    kid = db.get(MUser, kid_id)
    kid.avatar_updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    path = avatars.avatar_path(kid_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png-bytes")
    db.close()

    # cross-family: sealed by default
    assert other.get(f"/users/{kid_id}/avatar").status_code == 404
    # opted in (family-wide switch): crosses the village wall
    assert owner.put("/villages/kid-avatars", json={"shared": True}).status_code == 204
    assert other.get(f"/users/{kid_id}/avatar").status_code == 200
    # own family always could
    assert owner.get(f"/users/{kid_id}/avatar").status_code == 200


# ---- the organizer lock on copies ---------------------------------------------------


def test_copies_are_managed_by_the_organizer(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy_id = ev["my_item_id"]
    assert other.patch(f"/items/{copy_id}", json={"title": "Ours now"}).status_code == 403
    assert other.delete(f"/items/{copy_id}").status_code == 403
    assert other.post(f"/items/{copy_id}/cancel?date={TOMORROW.isoformat()}").status_code == 403
    assert other.request("DELETE", f"/items/{copy_id}/cancel?date={TOMORROW.isoformat()}").status_code == 403
    # completion is the host's too: a copy can't be checked or unchecked, the
    # done mark mirrors down from the organizer.
    assert other.post(f"/items/{copy_id}/complete?date={TODAY.isoformat()}").status_code == 403
    assert other.request(
        "DELETE", f"/items/{copy_id}/complete?date={TODAY.isoformat()}"
    ).status_code == 403
    # the organizer's source stays fully editable
    assert owner.patch(f"/items/{item['id']}", json={"title": "Soccer scrimmage"}).status_code == 200


def _completions(app, item_id):
    from sqlalchemy.orm import sessionmaker

    from app.models import Completion

    Session = sessionmaker(bind=app.state.test_engine, expire_on_commit=False)
    with Session() as db:
        return db.query(Completion).filter_by(item_id=item_id).all()


def test_a_kid_cannot_check_a_managed_copy(village, owner, other, app):
    from tests.conftest import login

    kid = {"username": "bkid", "display_name": "Kenny B", "password": "bkid-pass-1234"}
    assert other.post("/auth/users", json={**kid, "role": "child"}).status_code == 201
    bkid = login(app, kid)

    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy_id = ev["my_item_id"]
    # the kid can see the family-visible copy but still can't touch it
    assert bkid.post(f"/items/{copy_id}/complete?date={TODAY.isoformat()}").status_code == 403


def test_organizer_done_mirrors_onto_copies_without_leaking(village, owner, other, app):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy_id = ev["my_item_id"]

    # the organizer marks their source done -> the copy shows done
    assert owner.post(f"/items/{item['id']}/complete?date={TODAY.isoformat()}").status_code == 200
    assert feed_ids(other)[copy_id]["completed"] is True
    # and the copy's completion carries NO cross-family user id
    rows = _completions(app, copy_id)
    assert len(rows) == 1 and rows[0].user_id is None and rows[0].cancelled is False

    # undoing on the source clears the copy again
    assert owner.request(
        "DELETE", f"/items/{item['id']}/complete?date={TODAY.isoformat()}"
    ).status_code == 200
    assert feed_ids(other)[copy_id]["completed"] is False
    assert _completions(app, copy_id) == []


def test_rsvp_after_source_done_is_born_done(village, owner, other, app):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    # the organizer completes BEFORE anyone RSVPs
    assert owner.post(f"/items/{item['id']}/complete?date={TODAY.isoformat()}").status_code == 200
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy_id = ev["my_item_id"]
    assert feed_ids(other)[copy_id]["completed"] is True
    rows = _completions(app, copy_id)
    assert len(rows) == 1 and rows[0].user_id is None and rows[0].cancelled is False


# ---- timezone conversion -------------------------------------------------------------


def test_shift_schedule_math():
    d = dt.date(2026, 7, 20)
    # NY evening -> LA afternoon, same date
    nd, ns, ne = shift_schedule(d, dt.time(20, 0), dt.time(21, 0), False, "America/New_York", "America/Los_Angeles")
    assert (nd, ns, ne) == (d, dt.time(17, 0), dt.time(18, 0))
    # NY small hours -> LA previous evening
    nd, ns, ne = shift_schedule(d, dt.time(1, 0), dt.time(2, 0), False, "America/New_York", "America/Los_Angeles")
    assert (nd, ns, ne) == (d - dt.timedelta(days=1), dt.time(22, 0), dt.time(23, 0))
    # LA late night -> NY next date
    nd, ns, ne = shift_schedule(d, dt.time(23, 0), dt.time(23, 30), False, "America/Los_Angeles", "America/New_York")
    assert (nd, ns, ne) == (d + dt.timedelta(days=1), dt.time(2, 0), dt.time(2, 30))
    # both zones unset: untouched
    assert shift_schedule(d, dt.time(9, 0), None, False, None, None) == (d, dt.time(9, 0), None)
    # all-day stays on its calendar day everywhere
    assert shift_schedule(d, None, None, True, "America/New_York", "Pacific/Auckland") == (d, None, None)
    # converted end crossing midnight clamps (event stays on one card date)
    nd, ns, ne = shift_schedule(d, dt.time(22, 0), dt.time(23, 30), False, "America/Los_Angeles", "America/New_York")
    assert nd == d + dt.timedelta(days=1) and ns == dt.time(1, 0) and ne == dt.time(2, 30)
    # a broken zone name leaves everything untouched
    assert shift_schedule(d, dt.time(9, 0), dt.time(10, 0), False, "Not/AZone", "America/New_York") == (
        d, dt.time(9, 0), dt.time(10, 0)
    )


def test_copies_land_on_the_attendee_familys_clock(village, owner, other):
    assert owner.patch(
        "/families/me", json={"name": "Home", "timezone": "America/New_York"}
    ).status_code == 200
    assert other.patch(
        "/families/me", json={"name": "The Bs", "timezone": "America/Los_Angeles"}
    ).status_code == 200
    item = make_event(owner, time_of_day="20:00", end_time="21:00")
    out = share(owner, village, item["id"])
    # the list already shows B their local time
    ev = next(e for e in events(other) if e["event_id"] == out["event_id"])
    assert ev["time_of_day"] == "17:00:00"
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy = feed_ids(other)[ev["my_item_id"]]
    assert copy["time_of_day"] == "17:00:00" and copy["end_time"] == "18:00:00"
    # the organizer keeps their own wall time
    src = feed_ids(owner)[item["id"]]
    assert src["time_of_day"] == "20:00:00"


# ---- propagation ----------------------------------------------------------------------


def test_reschedule_rewrites_copies_and_notifies_going_only(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.patch(
        f"/items/{item['id']}", json={"time_of_day": "18:00", "end_time": "19:00"}
    ).status_code == 200
    copy = feed_ids(other)[ev["my_item_id"]]
    assert copy["time_of_day"] == "18:00:00"
    lines = inbox_rows(other, "village")
    assert len(lines) == 1 and "Updated" in lines[0]["title"]


def test_shared_source_cannot_be_reshaped(village, owner, other):
    """A shared card must stay dated and non-repeating: reshaping it would
    strand every family's list and copies. Regression for the reviewer's
    repeat-conversion 500."""
    item = make_event(owner, kind="appointment")
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    res = owner.patch(
        f"/items/{item['id']}",
        json={"repeat": {"type": "weekly", "days": [0]}, "date_for": None},
    )
    assert res.status_code == 400
    assert "Unshare" in res.json()["detail"]
    # nothing broke for anyone
    assert owner.get("/villages/events").status_code == 200
    assert other.get("/villages/events").status_code == 200
    # unsharing frees the card to become whatever it likes
    assert owner.delete(f"/villages/events/{out['event_id']}").status_code == 204
    assert owner.patch(
        f"/items/{item['id']}",
        json={"repeat": {"type": "weekly", "days": [0]}, "date_for": None},
    ).status_code == 200


def test_title_edits_sync_silently(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.patch(f"/items/{item['id']}", json={"title": "Soccer scrimmage"}).status_code == 200
    copy = feed_ids(other)[ev["my_item_id"]]
    assert copy["title"] == "Soccer scrimmage"
    assert inbox_rows(other, "village") == []


def test_location_change_notifies(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.patch(f"/items/{item['id']}", json={"location": "Lions Field"}).status_code == 200
    lines = inbox_rows(other, "village")
    assert len(lines) == 1 and "Lions Field" in lines[0]["body"]


def test_maybe_families_hear_nothing_on_changes(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "maybe")
    other.post("/me/inbox/read")
    owner.patch(f"/items/{item['id']}", json={"time_of_day": "19:00", "end_time": "20:00"})
    assert inbox_rows(other, "village") == []


# ---- delete / unshare / cancel ----------------------------------------------------------


def test_organizer_delete_takes_everything_with_it(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.delete(f"/items/{item['id']}").status_code == 204
    assert events(other) == []
    assert ev["my_item_id"] not in feed_ids(other)
    lines = inbox_rows(other, "village")
    assert len(lines) == 1 and "Called off" in lines[0]["title"]


def test_unshare_keeps_the_source_card(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    # only the organizer family may unshare
    assert other.delete(f"/villages/events/{out['event_id']}").status_code == 404
    assert owner.delete(f"/villages/events/{out['event_id']}").status_code == 204
    assert events(other) == []
    assert ev["my_item_id"] not in feed_ids(other)
    assert item["id"] in feed_ids(owner)  # the family card survives


def test_cancel_mirrors_the_strikethrough(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.post(f"/items/{item['id']}/cancel?date={TOMORROW.isoformat()}").status_code == 200
    copy = feed_ids(other)[ev["my_item_id"]]
    assert copy["cancelled"] is True
    assert any("Called off" in r["title"] for r in inbox_rows(other, "village"))
    # and back on
    assert owner.request("DELETE", f"/items/{item['id']}/cancel?date={TOMORROW.isoformat()}").status_code == 200
    copy = feed_ids(other)[ev["my_item_id"]]
    assert copy["cancelled"] is False
    assert any("Back on" in r["title"] for r in inbox_rows(other, "village"))


def test_going_after_cancel_lands_a_struck_copy(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    owner.post(f"/items/{item['id']}/cancel?date={TOMORROW.isoformat()}")
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    copy = feed_ids(other)[ev["my_item_id"]]
    assert copy["cancelled"] is True


# ---- cleanup on leave / village delete -----------------------------------------------


def test_host_family_leaving_calls_off_its_events(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.delete(f"/villages/{village}/membership").status_code == 204
    assert events(other) == []
    assert ev["my_item_id"] not in feed_ids(other)
    assert any("Called off" in r["title"] for r in inbox_rows(other, "village"))
    # the organizer's own source card is untouched
    assert item["id"] in feed_ids(owner)


def test_attendee_family_leaving_takes_its_rsvp_and_copy(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    assert other.delete(f"/villages/{village}/membership").status_code == 204
    assert ev["my_item_id"] not in feed_ids(other)
    mine = next(e for e in events(owner) if e["event_id"] == out["event_id"])
    assert mine["rsvps"] == []  # the answer left with them


def test_village_delete_clears_the_boards(village, owner, other):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    ev = rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.delete(f"/villages/{village}").status_code == 204
    assert ev["my_item_id"] not in feed_ids(other)
    assert any("closed" in r["title"] for r in inbox_rows(other, "village"))


# ---- notifications and prefs -----------------------------------------------------------


def test_invite_lines_reach_other_families_only(village, owner, other, parent, child):
    item = make_event(owner)
    share(owner, village, item["id"])
    assert any("invited you" in r["title"] for r in inbox_rows(other, "invite"))
    # the organizer's own family gets no invite, and kids never do
    assert inbox_rows(parent, "invite") == []
    assert inbox_rows(child, "invite") == []


def test_rsvp_lines_reach_the_organizer_with_headcount(village, owner, other, parent):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    lines = inbox_rows(owner, "rsvp")
    assert len(lines) == 1 and "Going · 1" in lines[0]["title"]
    # the second parent of the organizer family hears too
    assert len(inbox_rows(parent, "rsvp")) == 1


def _push_device(client, endpoint):
    client.put("/push/subscription", json={
        "endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"},
    })


def test_rsvp_is_inbox_only_and_tells_the_co_parent(
    village, owner, other, app, configured, outbox
):
    from tests.conftest import login

    # A second parent in the ACTING family hears what their co-parent answered.
    creds = {"username": "bparent", "display_name": "Bea Parent", "password": "bea-pass-111"}
    assert other.post("/auth/users", json={**creds, "role": "parent"}).status_code == 201
    b_parent = login(app, creds)

    _push_device(owner, "https://push.example/organizer")
    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    # The organizer's inbox line lands, but the phone stays silent (his
    # policy: RSVP replies are history, not interruptions).
    assert any("Going · 1" in r["title"] for r in inbox_rows(owner, "rsvp"))
    assert outbox == []
    lines = inbox_rows(b_parent, "rsvp")
    assert len(lines) == 1 and "replied Going · 1" in lines[0]["title"]

    # Withdrawing follows the same channels.
    assert other.delete(f"/villages/events/{out['event_id']}/rsvp").status_code == 204
    assert outbox == []
    assert any("withdrew their RSVP" in r["title"] for r in inbox_rows(owner, "rsvp"))
    assert any("withdrew the RSVP" in r["title"] for r in inbox_rows(b_parent, "rsvp"))


def test_identical_rsvp_repeat_records_nothing(village, owner, other, app):
    from tests.conftest import login

    creds = {"username": "bparent2", "display_name": "Bea Parent", "password": "bea-pass-222"}
    assert other.post("/auth/users", json={**creds, "role": "parent"}).status_code == 201
    b_parent = login(app, creds)

    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    # The identical re-save changes nothing and records nothing (the
    # dinner-vote convention): still exactly one line on each side.
    rsvp(other, out["event_id"], "going", [user_id(other)])
    assert len(inbox_rows(owner, "rsvp")) == 1
    assert len(inbox_rows(b_parent, "rsvp")) == 1
    # A REAL change records again.
    rsvp(other, out["event_id"], "maybe")
    assert len(inbox_rows(owner, "rsvp")) == 2
    assert len(inbox_rows(b_parent, "rsvp")) == 2


def test_share_event_pushes_others_but_own_family_gets_inbox_only(
    village, owner, other, parent, configured, outbox
):
    # Subscribe AFTER the card exists so the board-change push from creating
    # it never muddies the assertion.
    item = make_event(owner)
    _push_device(other, "https://push.example/guest")
    _push_device(parent, "https://push.example/coparent")
    share(owner, village, item["id"])
    # The invite still PUSHES the other family; the co-parent's phone is
    # silent but their inbox says what went out.
    assert outbox == ["https://push.example/guest"]
    lines = inbox_rows(parent, "village")
    assert len(lines) == 1
    assert "shared to Bread Circle: Soccer practice" in lines[0]["title"]


def test_unshare_event_still_pushes_called_off(village, owner, other, configured, outbox):
    item = make_event(owner)
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    _push_device(other, "https://push.example/guest-off")
    assert owner.delete(f"/villages/events/{out['event_id']}").status_code == 204
    # Changes to an event you're going to keep their push (the demotion must
    # never over-reach into "Called off").
    assert outbox == ["https://push.example/guest-off"]
    assert any("Called off" in r["title"] for r in inbox_rows(other, "village"))


def test_village_pref_gates_the_push_not_the_inbox(village, owner, other, configured, outbox):
    other.put("/push/subscription", json={
        "endpoint": "https://push.example/village-device",
        "keys": {"p256dh": "k", "auth": "a"},
    })
    other.put("/push/prefs", json={"prefs": {"village": False}})
    item = make_event(owner)
    share(owner, village, item["id"])
    assert outbox == []  # pref silenced the phone
    assert any("invited you" in r["title"] for r in inbox_rows(other, "invite"))
    # pref accepted by the prefs endpoint
    assert other.get("/push/prefs").json()["prefs"]["village"] is False


def test_past_due_nags_the_source_but_never_the_copy(
    village, owner, other, configured, push_outbox, engine_db
):
    """A shared-event copy can't be acted on by its family, so it must never
    nag them as past due. The organizer's own source still nags its host."""
    import app.push as push_engine

    yesterday = TODAY - dt.timedelta(days=1)
    owner.put("/push/subscription", json={
        "endpoint": "https://push.example/host-device",
        "keys": {"p256dh": "k1", "auth": "a1"},
    })
    other.put("/push/subscription", json={
        "endpoint": "https://push.example/guest-device",
        "keys": {"p256dh": "k2", "auth": "a2"},
    })
    item = make_event(
        owner, kind="appointment", date_for=yesterday.isoformat(),
        time_of_day="09:00", end_time="10:00",
    )
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])  # the copy lands on B's board
    push_outbox.clear()

    # 25 hours after 9am yesterday: exactly one nudge, to the source's family.
    sent = push_engine.digest_tick(dt.datetime.combine(TODAY, dt.time(10, 5)))
    assert sent == 1
    endpoints = [ep for ep, _p in push_outbox]
    assert endpoints == ["https://push.example/host-device"]
    assert push_outbox[0][1]["title"] == "Past due: Soccer practice"


def test_location_validation_and_feed_exposure(owner):
    too_long = "x" * 121
    assert owner.post(
        "/items", json={"kind": "task", "title": "T", "location": too_long}
    ).status_code == 422
    item = make_event(owner)
    assert feed_ids(owner)[item["id"]]["location"] == "Riverside Park"
    assert owner.patch(f"/items/{item['id']}", json={"location": None}).status_code == 200
    assert feed_ids(owner)[item["id"]]["location"] is None


# ---- cross-timezone notification text ------------------------------------------------
# The schedule in an invite/change notification renders on each recipient
# family's own wall clock, not the organizer's. Same-tz families are unchanged.


def _tz(client, name):
    fam = client.get("/families/me").json()
    assert client.patch(
        "/families/me", json={"name": fam["name"], "timezone": name}
    ).status_code == 200


def test_same_tz_invite_body_is_byte_identical(village, owner, other):
    from types import SimpleNamespace

    from app.routers.items import _schedule_text

    item = make_event(owner)  # default families keep NULL tz
    share(owner, village, item["id"])
    ref = SimpleNamespace(
        repeat_type=None, date_for=TOMORROW, all_day=False,
        time_of_day=dt.time(17, 30), end_time=dt.time(18, 30),
    )
    expected = _schedule_text(ref) + " · Riverside Park"
    body = inbox_rows(other, "invite")[0]["body"]
    assert body == expected


def test_cross_tz_invite_body_shows_the_recipients_wall_clock(village, owner, other):
    _tz(owner, "America/New_York")
    _tz(other, "America/Phoenix")  # no DST, UTC-7 year round
    item = make_event(owner, time_of_day="18:00", end_time="19:00")
    share(owner, village, item["id"])
    body = inbox_rows(other, "invite")[0]["body"]
    # 6-7 PM in NY (EDT, UTC-4) is 3-4 PM in Phoenix on the same date
    assert "3:00 PM – 4:00 PM" in body
    assert "6:00 PM" not in body


def test_all_day_invite_body_keeps_the_calendar_date_everywhere(village, owner, other):
    _tz(owner, "America/New_York")
    _tz(other, "Pacific/Auckland")
    item = make_event(
        owner, kind="appointment", all_day=True, time_of_day=None, end_time=None
    )
    share(owner, village, item["id"])
    body = inbox_rows(other, "invite")[0]["body"]
    assert TOMORROW.strftime("%a %b %-d") in body and "all day" in body


def test_cross_tz_schedule_change_body_uses_the_recipients_clock(village, owner, other):
    _tz(owner, "America/New_York")
    _tz(other, "America/Phoenix")
    item = make_event(owner, time_of_day="17:30", end_time="18:30")
    out = share(owner, village, item["id"])
    rsvp(other, out["event_id"], "going", [user_id(other)])
    other.post("/me/inbox/read")
    assert owner.patch(
        f"/items/{item['id']}", json={"time_of_day": "18:00", "end_time": "19:00"}
    ).status_code == 200
    line = next(r for r in inbox_rows(other, "village") if "Updated" in r["title"])
    assert "3:00 PM – 4:00 PM" in line["body"]


def test_null_tz_zone_uses_the_dates_own_dst_offset(monkeypatch):
    """_zone(None) resolves the server's real IANA zone from TZ, so a NULL-tz
    family converts a schedule on the date's own offset, not today's."""
    monkeypatch.setenv("TZ", "America/New_York")
    jan = dt.date(2026, 1, 15)  # EST, UTC-5
    d, s, _ = shift_schedule(jan, dt.time(12, 0), None, False, None, "America/Phoenix")
    assert (d, s) == (jan, dt.time(10, 0))
    jul = dt.date(2026, 7, 15)  # EDT, UTC-4
    d, s, _ = shift_schedule(jul, dt.time(12, 0), None, False, None, "America/Phoenix")
    assert (d, s) == (jul, dt.time(9, 0))
