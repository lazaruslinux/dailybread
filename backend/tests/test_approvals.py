"""Kid mode approvals: a minor's check-off waits for a parent.

The kid's tap creates a PENDING completion (never counted as done, streaks
untouched) and pushes to every parent. A parent then approves — promoting the
very same row in place — or puts it back, which deletes the row so the kid
can try again. Minors may withdraw their own pending mark but can't un-tick
anything a parent has approved.
"""

import datetime as dt

from tests.conftest import user_id

TODAY = dt.date.today()
YESTERDAY = TODAY - dt.timedelta(days=1)

SUB = {
    "endpoint": "https://push.example/parent-phone",
    "keys": {"p256dh": "k1", "auth": "a1"},
}
SUB2 = {
    "endpoint": "https://push.example/parent-tablet",
    "keys": {"p256dh": "k2", "auth": "a2"},
}


def make_item(client, **overrides):
    payload = {"kind": "task", "title": "Test card", **overrides}
    res = client.post("/items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def daily_routine(client, **overrides):
    return make_item(
        client,
        kind="routine",
        title="Make bed",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
        **overrides,
    )


def card(client, item_id, date=TODAY.isoformat()):
    feed = client.get(f"/items/feed?date={date}")
    assert feed.status_code == 200, feed.text
    for section in feed.json().values():
        if isinstance(section, list):
            for item in section:
                if item["id"] == item_id:
                    return item
    return None


def complete(client, item_id, date=TODAY.isoformat(), for_user=None, approved=None):
    url = f"/items/{item_id}/complete?date={date}"
    if for_user is not None:
        url += f"&for={for_user}"
    if approved is not None:
        url += f"&approved={approved}"
    return client.post(url)


def completion_dates(app, item_id):
    """Every completion row's date_for for an item, read straight from the DB."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from app.models import Completion

    Session = sessionmaker(bind=app.state.test_engine)
    with Session() as db:
        return sorted(
            db.scalars(select(Completion.date_for).where(Completion.item_id == item_id))
        )


def uncomplete(client, item_id, date=TODAY.isoformat(), for_user=None):
    url = f"/items/{item_id}/complete?date={date}"
    if for_user is not None:
        url += f"&for={for_user}"
    return client.delete(url)


# ---- the kid's tap ------------------------------------------------------------------


def test_minor_tap_is_pending_not_done(owner, child):
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])

    res = complete(child, routine["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    # The kid sees a waiting mark, not a done one; the streak hasn't moved.
    assert body["completed"] is False
    assert body["pending"] is True
    mine = next(c for c in body["assignee_completions"] if c["user_id"] == kid_id)
    assert mine == {"user_id": kid_id, "completed": False, "streak": 0, "pending": True}

    # The parents' board shows the same pending state, not Done.
    seen = card(owner, routine["id"])
    theirs = next(c for c in seen["assignee_completions"] if c["user_id"] == kid_id)
    assert theirs["pending"] is True and theirs["completed"] is False


def test_minor_tap_on_a_one_shot_is_pending(owner, child):
    kid_id = user_id(child)
    task = make_item(owner, assignee_ids=[kid_id], date_for=TODAY.isoformat())

    body = complete(child, task["id"]).json()
    assert body["completed"] is False
    assert body["pending"] is True
    assert body["pending_by"] == kid_id


def test_child_with_adult_birthdate_still_needs_approval(owner, grown_child):
    # The headline of role-driven kid mode: age never bypasses the queue.
    task = make_item(owner, assignee_ids=[user_id(grown_child)], date_for=TODAY.isoformat())
    body = complete(grown_child, task["id"]).json()
    assert body["completed"] is False
    assert body["pending"] is True
    assert owner.get("/items/pending").json() != []


def test_kid_tap_pushes_to_every_parent_device(owner, parent, child, configured, outbox):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    routine = daily_routine(owner, assignee_ids=[user_id(child)])
    outbox.clear()  # the routine's own board-change push isn't under test

    complete(child, routine["id"])
    # One push per parent device: both parents' phones, nothing to the kid.
    assert sorted(outbox) == sorted([SUB["endpoint"], SUB2["endpoint"]])

    # Approving is quiet — no second round of notifications.
    complete(owner, routine["id"], for_user=user_id(child))
    assert len(outbox) == 2


# ---- approve / put back -------------------------------------------------------------


def test_parent_approval_promotes_the_same_row(owner, child):
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])
    complete(child, routine["id"])

    # Approve via the same complete endpoint a parent already uses for ?for=.
    # Promote-in-place: were this an INSERT, (item, member, day) would collide.
    res = complete(owner, routine["id"], for_user=kid_id)
    assert res.status_code == 200, res.text
    theirs = next(
        c for c in res.json()["assignee_completions"] if c["user_id"] == kid_id
    )
    assert theirs["completed"] is True
    assert theirs["pending"] is False
    assert theirs["streak"] == 1

    # Settled: nothing waiting anymore.
    assert owner.get("/items/pending").json() == []


def test_parent_completing_a_one_shot_with_a_pending_mark_approves_it(owner, child):
    kid_id = user_id(child)
    task = make_item(owner, assignee_ids=[kid_id], date_for=TODAY.isoformat())
    complete(child, task["id"])

    body = complete(owner, task["id"]).json()
    assert body["completed"] is True
    assert body["pending"] is False
    assert owner.get("/items/pending").json() == []


def test_dated_oneoff_approval_redates_the_row_to_the_approval_day(app, owner, child):
    # A kid taps a future one-off on day D; a parent approves on D+1. The
    # promoted row moves to the approval day so the card shows in Done then and
    # clears the next day, exactly like a card ticked directly. Here D is
    # YESTERDAY so both feed days stay inside the board's today +/- 1 window.
    kid_id = user_id(child)
    due = (TODAY + dt.timedelta(days=1)).isoformat()  # D+2, still ahead at approval
    task = make_item(owner, assignee_ids=[kid_id], date_for=due)

    complete(child, task["id"], date=YESTERDAY.isoformat())  # tap on day D
    assert completion_dates(app, task["id"]) == [YESTERDAY]

    res = complete(
        owner, task["id"], date=YESTERDAY.isoformat(), for_user=kid_id,
        approved=TODAY.isoformat(),
    )
    assert res.status_code == 200 and res.json()["completed"] is True
    assert completion_dates(app, task["id"]) == [TODAY]  # re-dated to the approval day

    # D+1 (the approval day): the card sits in Done. D+2 (its due day): gone.
    shown = card(owner, task["id"], date=TODAY.isoformat())
    assert shown is not None and shown["completed"] is True
    assert card(owner, task["id"], date=due) is None


def test_same_day_approval_leaves_the_completion_on_that_day(app, owner, child):
    # Approving on the tap day is a no-op re-date: the card is in Done today and
    # gone tomorrow, the unchanged baseline.
    kid_id = user_id(child)
    task = make_item(owner, assignee_ids=[kid_id], date_for=TODAY.isoformat())

    complete(child, task["id"])
    complete(owner, task["id"], for_user=kid_id, approved=TODAY.isoformat())
    assert completion_dates(app, task["id"]) == [TODAY]

    shown = card(owner, task["id"], date=TODAY.isoformat())
    assert shown is not None and shown["completed"] is True
    tomorrow = (TODAY + dt.timedelta(days=1)).isoformat()
    assert card(owner, task["id"], date=tomorrow) is None


def test_routine_approval_on_a_later_day_keeps_the_tap_day(app, owner, child):
    # Routines are day-keyed: re-dating would mark the wrong slot done, so the
    # promoted row keeps the kid's tap day even when `approved` is sent.
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])
    complete(child, routine["id"], date=YESTERDAY.isoformat())

    complete(
        owner, routine["id"], date=YESTERDAY.isoformat(), for_user=kid_id,
        approved=TODAY.isoformat(),
    )
    assert completion_dates(app, routine["id"]) == [YESTERDAY]


def test_approval_without_the_approved_param_leaves_the_date_unchanged(app, owner, child):
    # Older clients omit `approved`; the row stays on the tap day rather than
    # being guessed with server time.
    kid_id = user_id(child)
    due = (TODAY + dt.timedelta(days=1)).isoformat()
    task = make_item(owner, assignee_ids=[kid_id], date_for=due)

    complete(child, task["id"], date=YESTERDAY.isoformat())
    complete(owner, task["id"], date=YESTERDAY.isoformat(), for_user=kid_id)
    assert completion_dates(app, task["id"]) == [YESTERDAY]


def test_board_checkbox_approval_without_for_redates(app, owner, child):
    # A parent tapping a kid's pending dated one-off directly on the board sends
    # no `for`; the item-wide lookup still finds the pending row and the parent
    # promotes it, so the re-date must fire on this shape too.
    kid_id = user_id(child)
    due = (TODAY + dt.timedelta(days=1)).isoformat()
    task = make_item(owner, assignee_ids=[kid_id], date_for=due)
    complete(child, task["id"], date=YESTERDAY.isoformat())

    res = complete(owner, task["id"], date=YESTERDAY.isoformat(), approved=TODAY.isoformat())
    assert res.status_code == 200 and res.json()["completed"] is True
    assert completion_dates(app, task["id"]) == [TODAY]


def test_approval_rejects_a_far_off_approved_date(owner, child):
    # `approved` is the parent's clock, clamped to today +/- 1 like `date`: a
    # bogus far date is refused rather than parking the row in another year.
    kid_id = user_id(child)
    task = make_item(owner, assignee_ids=[kid_id], date_for=TODAY.isoformat())
    complete(child, task["id"])
    far = (TODAY + dt.timedelta(days=400)).isoformat()
    assert complete(owner, task["id"], for_user=kid_id, approved=far).status_code == 400


def test_kid_passing_approved_on_a_retap_has_no_effect(app, owner, child):
    # A minor can't promote, so an `approved` on their own re-tap changes nothing:
    # the mark stays pending on the tap day.
    kid_id = user_id(child)
    task = make_item(owner, assignee_ids=[kid_id], date_for=TODAY.isoformat())
    complete(child, task["id"])

    tomorrow = (TODAY + dt.timedelta(days=1)).isoformat()
    complete(child, task["id"], approved=tomorrow)
    assert completion_dates(app, task["id"]) == [TODAY]
    assert owner.get("/items/pending").json() != []  # still waiting


def test_undated_task_approval_keeps_the_tap_day(app, owner, child):
    # Undated tasks are day-keyed like routines, so `approved` never moves them.
    kid_id = user_id(child)
    task = make_item(owner, assignee_ids=[kid_id])  # no date_for
    complete(child, task["id"], date=YESTERDAY.isoformat())

    complete(
        owner, task["id"], date=YESTERDAY.isoformat(), for_user=kid_id,
        approved=TODAY.isoformat(),
    )
    assert completion_dates(app, task["id"]) == [YESTERDAY]


def test_reject_deletes_and_the_kid_can_try_again(owner, child):
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])
    complete(child, routine["id"])

    # "Put back": the parent's normal un-check, aimed at the kid's mark.
    res = uncomplete(owner, routine["id"], for_user=kid_id)
    assert res.status_code == 200, res.text
    assert owner.get("/items/pending").json() == []
    mine = next(
        c
        for c in card(child, routine["id"])["assignee_completions"]
        if c["user_id"] == kid_id
    )
    assert mine["pending"] is False and mine["completed"] is False

    # A fresh tap starts the cycle over (the deleted row can't collide).
    body = complete(child, routine["id"]).json()
    assert body["pending"] is True


def test_kid_withdraws_their_own_pending_mark(owner, child):
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])
    complete(child, routine["id"])

    res = uncomplete(child, routine["id"])
    assert res.status_code == 200, res.text
    assert owner.get("/items/pending").json() == []


def test_kid_cannot_untick_an_approved_completion(owner, child):
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])
    complete(child, routine["id"])
    complete(owner, routine["id"], for_user=kid_id)  # approve

    uncomplete(child, routine["id"])  # a minor can't take back a parent's word
    mine = next(
        c
        for c in card(child, routine["id"])["assignee_completions"]
        if c["user_id"] == kid_id
    )
    assert mine["completed"] is True


# ---- the waiting-on-you list --------------------------------------------------------


def test_pending_list_is_parent_only(owner, parent, child):
    assert child.get("/items/pending").status_code == 403
    # Any parent, admin or not, answers approvals.
    assert parent.get("/items/pending").status_code == 200
    assert owner.get("/items/pending").status_code == 200


def test_pending_list_spans_days_and_carries_the_kid(owner, child):
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])
    # Yesterday's occurrence, marked late — today's feed would never show it.
    complete(child, routine["id"], date=YESTERDAY.isoformat())
    complete(child, routine["id"], date=TODAY.isoformat())

    waiting = owner.get("/items/pending").json()
    assert [w["date_for"] for w in waiting] == [
        YESTERDAY.isoformat(),
        TODAY.isoformat(),
    ]
    assert all(w["item_id"] == routine["id"] for w in waiting)
    assert all(w["user"]["id"] == kid_id for w in waiting)
    assert all(w["title"] == "Make bed" for w in waiting)

    # Approving yesterday's from the list works the same as any approval.
    complete(owner, routine["id"], date=YESTERDAY.isoformat(), for_user=kid_id)
    assert len(owner.get("/items/pending").json()) == 1


def test_pending_list_is_family_scoped(owner, child, other):
    routine = daily_routine(owner, assignee_ids=[user_id(child)])
    complete(child, routine["id"])
    assert other.get("/items/pending").json() == []


def test_unassigning_a_kid_clears_their_orphaned_pending(owner, child):
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id, user_id(owner)])
    complete(child, routine["id"])
    assert len(owner.get("/items/pending").json()) == 1

    # The kid comes off the card; their unapprovable mark goes with them.
    res = owner.patch(f"/items/{routine['id']}", json={"assignee_ids": [user_id(owner)]})
    assert res.status_code == 200, res.text
    assert owner.get("/items/pending").json() == []


# ---- side effects -------------------------------------------------------------------


def test_pending_mark_suppresses_the_kids_reminder(
    app, owner, child, configured, outbox, monkeypatch
):
    import app.push as push_engine
    from sqlalchemy.orm import sessionmaker

    kid_id = user_id(child)
    routine = daily_routine(
        owner, assignee_ids=[kid_id, user_id(owner)], time_of_day="14:10:00"
    )
    complete(child, routine["id"])  # pending — the kid already acted

    TestingSession = sessionmaker(
        bind=app.state.test_engine, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(push_engine, "SessionLocal", TestingSession)
    owner.put("/push/subscription", json=SUB)  # subscribe AFTER the tap
    child.put("/push/subscription", json=SUB2)

    now = dt.datetime.combine(TODAY, dt.time(14, 0))
    assert push_engine.reminder_tick(now) == 1
    assert outbox == [SUB["endpoint"]]  # the owner is nagged; the kid is not


def test_unconfigured_push_never_blocks_the_checkoff(owner, child):
    # No VAPID keys at all: the tap must still land as pending.
    routine = daily_routine(owner, assignee_ids=[user_id(child)])
    assert complete(child, routine["id"]).status_code == 200
    assert len(owner.get("/items/pending").json()) == 1


# ---- rows left over from before the completion rework -------------------------------


def seed_pending(app, item_id, member_id, date=TODAY):
    """A kid's waiting mark written straight to the DB. Appointments and
    activities refuse new marks now, but rows tapped before the rework are
    still in the queue and both answers have to reach them."""
    from sqlalchemy.orm import sessionmaker

    from app.models import Completion

    Session = sessionmaker(bind=app.state.test_engine)
    with Session() as db:
        db.add(
            Completion(item_id=item_id, user_id=member_id, date_for=date, pending=True)
        )
        db.commit()


def dated_appointment(client, **overrides):
    return make_item(
        client, kind="appointment", title="Dentist", visibility="family",
        date_for=TODAY.isoformat(), time_of_day="14:00", end_time="15:00",
        **overrides,
    )


def test_a_waiting_mark_on_an_appointment_can_still_be_approved(app, owner, child):
    kid_id = user_id(child)
    appt = dated_appointment(owner, assignee_ids=[kid_id])
    seed_pending(app, appt["id"], kid_id)
    assert owner.get("/items/pending").json() != []

    res = complete(owner, appt["id"])
    assert res.status_code == 200, res.text
    assert res.json()["completed"] is True
    assert owner.get("/items/pending").json() == []


def test_a_waiting_mark_on_an_appointment_can_still_be_put_back(app, owner, child):
    kid_id = user_id(child)
    appt = dated_appointment(owner, assignee_ids=[kid_id])
    seed_pending(app, appt["id"], kid_id)

    res = uncomplete(owner, appt["id"])
    assert res.status_code == 200, res.text
    assert completion_dates(app, appt["id"]) == []
    assert owner.get("/items/pending").json() == []


def test_a_fresh_mark_on_an_appointment_is_still_refused(owner, child):
    # Answering history is allowed; making new history is not.
    appt = dated_appointment(owner, assignee_ids=[user_id(child)])
    assert complete(child, appt["id"]).status_code == 400
    assert complete(owner, appt["id"]).status_code == 400
    assert uncomplete(owner, appt["id"]).status_code == 400


def test_the_second_parent_to_approve_gets_a_quiet_no_op(app, owner, parent, child):
    # Both parents answer the same row moments apart: the loser must not meet
    # a 400 telling them routines aren't theirs to check.
    kid_id = user_id(child)
    routine = daily_routine(owner, assignee_ids=[kid_id])
    complete(child, routine["id"])
    assert complete(owner, routine["id"], for_user=kid_id).status_code == 200

    res = complete(parent, routine["id"], for_user=kid_id)
    assert res.status_code == 200, res.text
    theirs = next(c for c in res.json()["assignee_completions"] if c["user_id"] == kid_id)
    assert theirs["completed"] is True and theirs["pending"] is False
    assert completion_dates(app, routine["id"]) == [TODAY]  # no second row
