"""Board items: who can create, edit, delete, and check off what."""

import datetime as dt

from tests.conftest import user_id

TODAY = dt.date.today().isoformat()


def make_item(client, **overrides):
    payload = {"kind": "task", "title": "Test card", **overrides}
    res = client.post("/items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_child_cannot_create_edit_or_delete(owner, child):
    item = make_item(owner)
    assert child.post("/items", json={"kind": "task", "title": "Nope"}).status_code == 403
    assert child.patch(f"/items/{item['id']}", json={"title": "Nope"}).status_code == 403
    assert child.delete(f"/items/{item['id']}").status_code == 403


def test_anon_gets_401_everywhere(anon):
    assert anon.get(f"/items/feed?date={TODAY}").status_code == 401
    assert anon.post("/items", json={"kind": "task", "title": "X"}).status_code == 401


def test_routines_cannot_carry_a_date(owner):
    res = owner.post(
        "/items", json={"kind": "routine", "title": "Daily thing", "date_for": TODAY}
    )
    assert res.status_code == 400


def test_child_checks_cards_assigned_to_them(owner, child):
    kid_id = user_id(child)
    own = make_item(owner, assignee_ids=[kid_id])
    on_board = make_item(owner, assignee_ids=[kid_id], visibility="family")

    # Being assigned is what makes a card checkable, on the family board or not.
    assert child.post(f"/items/{own['id']}/complete?date={TODAY}").status_code == 200
    assert child.post(f"/items/{on_board['id']}/complete?date={TODAY}").status_code == 200


def test_child_cannot_see_someone_elses_card(owner, child):
    # A card assigned to the owner alone is invisible to the child, so checking
    # it 404s (looks like it doesn't exist) rather than merely 403.
    owners_card = make_item(owner, assignee_ids=[user_id(owner)])
    res = child.post(f"/items/{owners_card['id']}/complete?date={TODAY}")
    assert res.status_code == 404


def test_card_can_have_several_assignees(owner, child):
    kid_id = user_id(child)
    dad_id = user_id(owner)
    card = make_item(owner, assignee_ids=[dad_id, kid_id])

    # The feed echoes back both assignees.
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = next(i for i in feed["today"] if i["id"] == card["id"])
    assert {a["id"] for a in mine["assignees"]} == {dad_id, kid_id}

    # A child listed among several assignees may still check the card off.
    assert child.post(f"/items/{card['id']}/complete?date={TODAY}").status_code == 200


def test_editing_assignees_replaces_the_whole_set(owner, child):
    kid_id = user_id(child)
    card = make_item(owner, assignee_ids=[user_id(owner)])
    owner.patch(f"/items/{card['id']}", json={"assignee_ids": [kid_id]})

    # Now it's the child's, not the owner's: the owner is no longer an assignee.
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = next(i for i in feed["today"] if i["id"] == card["id"])
    assert [a["id"] for a in mine["assignees"]] == [kid_id]

    # Clearing to [] leaves the card owned by (and visible to) the owner alone.
    owner.patch(f"/items/{card['id']}", json={"assignee_ids": []})
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = next(i for i in feed["today"] if i["id"] == card["id"])
    assert mine["assignees"] == []


def test_uncomplete_reverses_a_checkoff(owner):
    item = make_item(owner)
    assert owner.post(f"/items/{item['id']}/complete?date={TODAY}").json()["completed"] is True
    assert owner.delete(f"/items/{item['id']}/complete?date={TODAY}").json()["completed"] is False


def test_a_missed_day_can_be_marked_on_its_own_day(owner, child):
    # The calendar's whole point: check a routine off on the day it actually
    # was. It then reads done on that day and stays open on the others.
    kid_id = user_id(child)
    routine = make_item(
        owner, kind="routine", title="Vitamins", assignee_ids=[kid_id],
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )
    three_ago = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    assert child.post(f"/items/{routine['id']}/complete?date={three_ago}").status_code == 200
    assert owner.post(
        f"/items/{routine['id']}/complete?date={three_ago}&for={kid_id}"
    ).status_code == 200

    back = owner.get(f"/items/calendar?start={three_ago}&end={three_ago}").json()
    assert next(i for i in back["days"][0]["items"] if i["id"] == routine["id"])["completed"] is True
    today_cal = owner.get(f"/items/calendar?start={TODAY}&end={TODAY}").json()
    assert next(i for i in today_cal["days"][0]["items"] if i["id"] == routine["id"])["completed"] is False


def test_cannot_complete_in_the_future(owner):
    ahead = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    appt = make_item(owner, kind="appointment", title="Later", date_for=ahead,
                     time_of_day="09:00", end_time="09:30")
    assert owner.post(f"/items/{appt['id']}/complete?date={ahead}").status_code == 400


def test_cannot_complete_too_far_back(owner):
    item = make_item(owner)
    ancient = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    assert owner.post(f"/items/{item['id']}/complete?date={ancient}").status_code == 400


def test_dated_completion_is_a_single_shot_across_days(owner):
    # A dated card is one-shot: cleared from the board's overdue list the check
    # lands on today, yet the card reads done on its own past day too, and
    # undoing from that day clears the single completion wherever it landed.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    appt = make_item(owner, title="Missed call", date_for=yesterday)
    owner.post(f"/items/{appt['id']}/complete?date={TODAY}")  # overdue-clear, recorded today

    back = owner.get(f"/items/calendar?start={yesterday}&end={yesterday}").json()
    assert next(i for i in back["days"][0]["items"] if i["id"] == appt["id"])["completed"] is True

    assert owner.delete(f"/items/{appt['id']}/complete?date={yesterday}").json()["completed"] is False
    back = owner.get(f"/items/calendar?start={yesterday}&end={yesterday}").json()
    assert next(i for i in back["days"][0]["items"] if i["id"] == appt["id"])["completed"] is False


def test_feed_rejects_faraway_dates(owner):
    far = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    assert owner.get(f"/items/feed?date={far}").status_code == 400


def test_checked_undated_todo_stays_crossed_out_for_the_day(owner):
    item = make_item(owner)  # undated task -> the "today" bucket
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == item["id"] for i in feed["today"])

    # Checked today: stays on the board, flagged completed (the client keeps it
    # crossed out in its Done section, then archives it tomorrow).
    owner.post(f"/items/{item['id']}/complete?date={TODAY}")
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = [i for i in feed["today"] if i["id"] == item["id"]]
    assert mine and mine[0]["completed"] is True


def test_undated_todo_completed_yesterday_is_archived(owner):
    item = make_item(owner)
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    owner.post(f"/items/{item['id']}/complete?date={yesterday}")

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == item["id"] for i in feed["today"])


def test_next7_has_a_horizon(owner):
    # The next-7-days list is bounded: a card one week out shows, one past that
    # does not (it lives only on the calendar), and nothing far off leaks in.
    within = (dt.date.today() + dt.timedelta(days=7)).isoformat()
    beyond = (dt.date.today() + dt.timedelta(days=8)).isoformat()
    a = make_item(owner, kind="appointment", title="In range", date_for=within,
                  time_of_day="09:00", end_time="10:00")
    b = make_item(owner, kind="appointment", title="Too far", date_for=beyond,
                  time_of_day="09:00", end_time="10:00")

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    def ids(bucket):
        return {i["id"] for i in feed[bucket]}
    assert a["id"] in ids("next7")
    assert b["id"] not in ids("next7") | ids("today") | ids("overdue")


def test_future_task_checked_ahead_shows_in_done_only_on_its_completion_day(owner):
    # Tasks are reminders: you can tick one off before its due date. It shows in
    # Done on the day you tick it (today, riding in next7), then leaves the board
    # entirely. The future branch keeps a completed card only on its own
    # completion day, so any later day it is gone.
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    day_after = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    task = make_item(owner, title="Return library books", date_for=day_after)

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == task["id"] for i in feed["next7"])

    res = owner.post(f"/items/{task['id']}/complete?date={TODAY}")
    assert res.status_code == 200 and res.json()["completed"] is True

    # Today: shows in next7, crossed out, the "I did it" payoff for the day.
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    done = [i for i in feed["next7"] if i["id"] == task["id"]]
    assert done and done[0]["completed"] is True

    # Tomorrow (a day later, still ahead of the due day): gone from the board.
    feed = owner.get(f"/items/feed?date={tomorrow}").json()
    assert not any(
        i["id"] == task["id"] for i in feed["overdue"] + feed["today"] + feed["next7"]
    )

    # The calendar still carries it on its own day, the recovery path for
    # un-checking an accidental early completion.
    cal = owner.get(f"/items/calendar?start={day_after}&end={day_after}").json()
    on_day = [i for i in cal["days"][0]["items"] if i["id"] == task["id"]]
    assert on_day and on_day[0]["completed"] is True


def test_task_checked_ahead_is_absent_when_its_due_day_arrives(owner):
    # A one-off due tomorrow, ticked today. On its due day (tomorrow) it has
    # already had its moment in Done, so the today branch drops it; the calendar
    # keeps it on its date as the recovery path.
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    task = make_item(owner, title="Vet visit", date_for=tomorrow)

    res = owner.post(f"/items/{task['id']}/complete?date={TODAY}")
    assert res.status_code == 200 and res.json()["completed"] is True

    feed = owner.get(f"/items/feed?date={tomorrow}").json()
    assert not any(
        i["id"] == task["id"] for i in feed["overdue"] + feed["today"] + feed["next7"]
    )

    cal = owner.get(f"/items/calendar?start={tomorrow}&end={tomorrow}").json()
    on_day = [i for i in cal["days"][0]["items"] if i["id"] == task["id"]]
    assert on_day and on_day[0]["completed"] is True


def test_task_due_today_checked_today_shows_done_today_then_drops(owner):
    # A one-off due today, checked today, sits in Done today (unchanged), then
    # leaves the board on the following day (existing past-branch behavior).
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    task = make_item(owner, title="Post the parcel", date_for=TODAY)

    owner.post(f"/items/{task['id']}/complete?date={TODAY}")
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = [i for i in feed["today"] if i["id"] == task["id"]]
    assert mine and mine[0]["completed"] is True

    feed = owner.get(f"/items/feed?date={tomorrow}").json()
    assert not any(
        i["id"] == task["id"] for i in feed["overdue"] + feed["today"] + feed["next7"]
    )


def test_future_task_with_pending_kid_mark_stays_on_the_board(owner, child):
    # A kid's tap on a future card is pending, not done. The guard keys strictly
    # on the completed state, so a pending future card is never skipped.
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    task = make_item(owner, title="Pack your bag", date_for=tomorrow,
                     assignee_ids=[user_id(child)])

    res = child.post(f"/items/{task['id']}/complete?date={TODAY}")
    assert res.status_code == 200 and res.json()["completed"] is False

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = [i for i in feed["next7"] if i["id"] == task["id"]]
    assert mine and mine[0]["completed"] is False
    assert mine[0]["pending_by"] == user_id(child)


def test_overdue_carries_past_due_tasks_forward(owner):
    # A TASK whose date slipped by keeps showing under "overdue" until done.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    task = make_item(owner, title="Call the plumber", date_for=yesterday)
    # Routines are habits, not one-offs, so a scheduled-yesterday routine is
    # never overdue; a card older than the 90-day lookback also drops off.
    make_item(owner, kind="routine", title="Daily",
              repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]})
    ancient = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    old = make_item(owner, title="Ancient", date_for=ancient)

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    overdue_ids = {i["id"] for i in feed["overdue"]}
    assert task["id"] in overdue_ids
    assert all(i["kind"] == "task" for i in feed["overdue"])
    assert old["id"] not in overdue_ids


def test_a_passed_appointment_or_activity_leaves_the_board(owner):
    # Calendar entries are not a to-do list: once their day has gone by they
    # simply stop showing. The calendar keeps the record.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    appt = make_item(owner, kind="appointment", title="Dentist", date_for=yesterday,
                     time_of_day="09:00", end_time="09:30")
    act = make_item(owner, kind="activity", title="Soccer", date_for=yesterday,
                    time_of_day="17:00", end_time="18:00")

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    shown = {i["id"] for i in feed["overdue"] + feed["today"] + feed["next7"]}
    assert appt["id"] not in shown and act["id"] not in shown

    cal = owner.get(f"/items/calendar?start={yesterday}&end={yesterday}").json()
    assert {i["id"] for i in cal["days"][0]["items"]} == {appt["id"], act["id"]}


def test_completing_an_overdue_card_archives_it_immediately(owner):
    # Checking off a past-due card removes it from the board at once — it
    # wasn't done today, so it doesn't sit in today's Done list. Its record
    # still shows, completed, on its own day in the calendar; undoing the
    # check brings it back to overdue.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    appt = make_item(owner, title="Late chore", date_for=yesterday)

    owner.post(f"/items/{appt['id']}/complete?date={TODAY}")
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(
        i["id"] == appt["id"] for i in feed["overdue"] + feed["today"] + feed["next7"]
    )
    cal = owner.get(f"/items/calendar?start={yesterday}&end={yesterday}").json()
    on_day = [i for i in cal["days"][0]["items"] if i["id"] == appt["id"]]
    assert on_day and on_day[0]["completed"] is True

    owner.delete(f"/items/{appt['id']}/complete?date={TODAY}")
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    back = [i for i in feed["overdue"] if i["id"] == appt["id"]]
    assert back and back[0]["completed"] is False


def _monday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())  # weekday(): Monday == 0


def test_calendar_expands_routines_and_places_dated_cards(owner):
    mon = _monday(dt.date.today())
    sun = mon + dt.timedelta(days=6)
    make_item(owner, kind="routine", title="Brush teeth",
              repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6], "interval": 1})
    make_item(owner, kind="routine", title="Trash night",
              repeat={"type": "weekly", "days": [0], "interval": 1})  # Mondays only
    wed = (mon + dt.timedelta(days=2)).isoformat()
    make_item(owner, kind="appointment", title="Dentist", date_for=wed,
              time_of_day="09:00", end_time="10:00")
    make_item(owner, kind="task", title="Someday")  # undated -> never on the calendar

    cal = owner.get(f"/items/calendar?start={mon}&end={sun}").json()
    days = {d["date"]: [i["title"] for i in d["items"]] for d in cal["days"]}
    assert len(cal["days"]) == 7
    assert all("Brush teeth" in titles for titles in days.values())  # daily
    assert sum("Trash night" in t for t in days.values()) == 1  # only Monday
    assert "Trash night" in days[mon.isoformat()]
    assert sum("Dentist" in t for t in days.values()) == 1  # only its date
    assert "Dentist" in days[wed]
    assert all("Someday" not in t for t in days.values())  # undated excluded


def test_calendar_reflects_completion(owner):
    d = dt.date.today().isoformat()
    task = make_item(owner, title="Pay bills", date_for=d)
    owner.post(f"/items/{task['id']}/complete?date={d}")
    cal = owner.get(f"/items/calendar?start={d}&end={d}").json()
    card = next(i for i in cal["days"][0]["items"] if i["id"] == task["id"])
    assert card["completed"] is True


def test_calendar_rejects_bad_range(owner):
    today = dt.date.today().isoformat()
    later = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    far = (dt.date.today() + dt.timedelta(days=60)).isoformat()
    assert owner.get(f"/items/calendar?start={later}&end={today}").status_code == 400
    assert owner.get(f"/items/calendar?start={today}&end={far}").status_code == 400


def test_calendar_hides_other_familys_cards(owner, child):
    # A child is in the owner's family; a card private to the owner still shows
    # for family visibility only. Cross-family isolation is covered in tenancy
    # tests; here just confirm a private card doesn't leak to a non-assignee.
    d = dt.date.today().isoformat()
    make_item(owner, kind="appointment", title="Owner only", date_for=d,
              time_of_day="09:00", end_time="10:00", visibility="private")
    cal = child.get(f"/items/calendar?start={d}&end={d}").json()
    assert all("Owner only" != i["title"] for i in cal["days"][0]["items"])


def test_activity_and_appointment_need_a_date_and_time(owner):
    # Missing both, or missing the time, is rejected.
    assert owner.post("/items", json={"kind": "activity", "title": "Gym"}).status_code == 400
    assert (
        owner.post(
            "/items", json={"kind": "appointment", "title": "Dentist", "date_for": TODAY}
        ).status_code
        == 400
    )
    # A start alone isn't enough for an activity; it needs an end too.
    assert (
        owner.post(
            "/items",
            json={"kind": "activity", "title": "Gym", "date_for": TODAY, "time_of_day": "17:00"},
        ).status_code
        == 400
    )
    ok = owner.post(
        "/items",
        json={
            "kind": "activity", "title": "Gym", "date_for": TODAY,
            "time_of_day": "17:00", "end_time": "18:00",
        },
    )
    assert ok.status_code == 201, ok.text


def test_editing_cannot_strand_an_appointment(owner):
    card = make_item(
        owner, kind="appointment", title="Dentist", date_for=TODAY,
        time_of_day="09:00", end_time="09:30",
    )
    # Clearing the date on an appointment leaves it invalid, so it's refused.
    assert owner.patch(f"/items/{card['id']}", json={"date_for": None}).status_code == 400
    # Renaming it (leaving date/time intact) is fine.
    assert owner.patch(f"/items/{card['id']}", json={"title": "Dentist checkup"}).status_code == 200


# ---- visibility (the family board by default) --------------------------------


def test_new_card_goes_on_the_family_board_by_default(owner, child):
    card = make_item(owner)  # no assignees, no visibility stated
    assert card["visibility"] == "family"

    # An unassigned family card is everyone's business, the child included.
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == card["id"] for i in feed["today"])


def test_explicit_private_is_kept(owner, child):
    # Opting a card out is what keeps it off the household's board: the owner
    # plus anyone assigned, and nobody else.
    card = make_item(owner, visibility="private")
    assert card["visibility"] == "private"

    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == card["id"] for i in feed["today"])
    assert child.post(f"/items/{card['id']}/complete?date={TODAY}").status_code == 404


def test_assigning_members_does_not_change_visibility(owner, child):
    # Assigning is about who does it, not who sees it: an assigned card that
    # was opted out stays private (the owner plus the assignee).
    card = make_item(owner, assignee_ids=[user_id(child)], visibility="private")
    assert card["visibility"] == "private"
    assert [a["id"] for a in card["assignees"]] == [user_id(child)]


def test_family_board_card_is_visible_to_all(owner, child):
    card = make_item(owner, visibility="family")
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == card["id"] for i in feed["today"])


def test_family_board_card_is_read_only_for_non_assignees(owner, child):
    # The "solo run" case: a routine the owner does alone, shown to the whole
    # family. Everyone sees it; a non-participant can't touch it, and since
    # routines are the kids' to check, neither can the adult who owns it.
    today_wd = dt.date.today().weekday()
    run = make_item(
        owner, kind="routine", title="Morning run", visibility="family",
        repeat={"type": "weekly", "days": [today_wd]},
    )
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == run["id"] for i in feed["today"])  # child sees it
    assert child.post(f"/items/{run['id']}/complete?date={TODAY}").status_code == 403  # read-only
    assert owner.post(f"/items/{run['id']}/complete?date={TODAY}").status_code == 400


def test_family_task_not_assigned_is_read_only_for_child(owner, child):
    task = make_item(owner, visibility="family")  # on the board, assigned to no one
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == task["id"] for i in feed["today"])
    assert child.post(f"/items/{task['id']}/complete?date={TODAY}").status_code == 403


def test_either_parent_can_check_a_family_board_card(owner, parent):
    # A co-parent can complete a family-board task the other parent added,
    # even though they're neither its owner nor an assignee.
    task = make_item(owner, title="Book the school photos", visibility="family",
                     date_for=TODAY)
    assert parent.post(f"/items/{task['id']}/complete?date={TODAY}").status_code == 200


def test_parent_cannot_check_a_private_card_they_are_not_on(owner, parent):
    # Private to the owner; the co-parent can't even see it.
    card = make_item(owner, visibility="private")
    assert parent.post(f"/items/{card['id']}/complete?date={TODAY}").status_code == 404


def test_parent_approves_a_childs_routine_but_cannot_check_it_first(owner, child):
    today_wd = dt.date.today().weekday()
    kid = user_id(child)
    routine = make_item(
        owner, kind="routine", title="Kid brush", assignee_ids=[kid],
        visibility="family", repeat={"type": "weekly", "days": [today_wd]},
    )
    # Without 'for', the parent isn't a participant, so there's nothing to check.
    assert owner.post(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 403
    # With 'for' but nothing waiting, a routine still isn't an adult's to check.
    res = owner.post(f"/items/{routine['id']}/complete?date={TODAY}&for={kid}")
    assert res.status_code == 400
    assert "approve" in res.json()["detail"]
    # The kid taps; the very same call is now the parent's approval.
    assert child.post(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 200
    assert owner.post(f"/items/{routine['id']}/complete?date={TODAY}&for={kid}").status_code == 200

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    card = next(i for i in feed["today"] if i["id"] == routine["id"])
    assert {c["user_id"]: c["completed"] for c in card["assignee_completions"]}[kid] is True


def test_child_cannot_check_on_behalf_of_another(owner, child):
    today_wd = dt.date.today().weekday()
    dad = user_id(owner)
    routine = make_item(
        owner, kind="routine", title="Family stretch", assignee_ids=[dad, user_id(child)],
        visibility="family", repeat={"type": "weekly", "days": [today_wd]},
    )
    # A child can check their own, but not someone else's, occurrence.
    assert child.post(f"/items/{routine['id']}/complete?date={TODAY}&for={dad}").status_code == 403
    assert child.post(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 200


# ---- event times: from/to + all-day -------------------------------------------


def test_appointment_can_be_all_day(owner):
    card = make_item(owner, kind="appointment", title="Birthday", date_for=TODAY, all_day=True)
    assert card["all_day"] is True
    assert card["time_of_day"] is None and card["end_time"] is None


def test_all_day_appointment_rejects_times(owner):
    res = owner.post(
        "/items",
        json={"kind": "appointment", "title": "Trip", "date_for": TODAY, "all_day": True, "time_of_day": "09:00"},
    )
    assert res.status_code == 400


def test_event_end_must_be_after_start(owner):
    res = owner.post(
        "/items",
        json={"kind": "activity", "title": "Run", "date_for": TODAY, "time_of_day": "18:00", "end_time": "17:00"},
    )
    assert res.status_code == 400


def test_activity_can_be_all_day(owner):
    card = make_item(owner, kind="activity", title="Fair day", date_for=TODAY, all_day=True)
    assert card["all_day"] is True
    assert card["time_of_day"] is None and card["end_time"] is None


def test_all_day_activity_rejects_times(owner):
    res = owner.post(
        "/items",
        json={
            "kind": "activity", "title": "Fair day", "date_for": TODAY,
            "all_day": True, "time_of_day": "09:00", "end_time": "10:00",
        },
    )
    assert res.status_code == 400


# ---- multi-day spans ----------------------------------------------------------

TOMORROW = (dt.date.today() + dt.timedelta(days=1)).isoformat()
YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def test_activity_can_span_days(owner):
    trip = make_item(
        owner, kind="activity", title="Camping", date_for=TODAY, end_date=TOMORROW,
        time_of_day="09:00", end_time="16:00",
    )
    assert trip["date_for"] == TODAY and trip["end_date"] == TOMORROW


def test_span_end_cannot_land_before_the_start(owner):
    res = owner.post(
        "/items",
        json={
            "kind": "activity", "title": "Backwards", "date_for": TODAY, "end_date": YESTERDAY,
            "time_of_day": "09:00", "end_time": "16:00",
        },
    )
    assert res.status_code == 400


def test_overnight_needs_the_next_day_as_its_end(owner):
    overnight = {
        "kind": "activity", "title": "Stargazing", "date_for": TODAY,
        "time_of_day": "22:00", "end_time": "02:00",
    }
    # On a single day 10 PM to 2 AM is still backwards.
    assert owner.post("/items", json=overnight).status_code == 400
    # Saying it ends the next day is what makes it read forwards.
    assert owner.post("/items", json={**overnight, "end_date": TOMORROW}).status_code == 201


def test_a_span_is_capped_at_the_boards_lookback(owner):
    """90 days is how far back the feed fetches dated cards, so a longer span
    could still be running while off the board entirely."""
    ninety = (dt.date.today() + dt.timedelta(days=90)).isoformat()
    ninety_one = (dt.date.today() + dt.timedelta(days=91)).isoformat()
    span = {
        "kind": "activity", "title": "Long haul", "date_for": TODAY,
        "time_of_day": "09:00", "end_time": "16:00",
    }
    assert owner.post("/items", json={**span, "end_date": ninety}).status_code == 201
    res = owner.post("/items", json={**span, "end_date": ninety_one})
    assert res.status_code == 400
    assert res.json()["detail"] == "A card can span up to 90 days"


def test_only_dated_event_kinds_take_a_span(owner):
    assert owner.post(
        "/items", json={"kind": "task", "title": "Nope", "date_for": TODAY, "end_date": TOMORROW}
    ).status_code == 400
    assert owner.post(
        "/items",
        json={
            "kind": "routine", "title": "Nope", "end_date": TOMORROW,
            "repeat": {"type": "weekly", "days": [0]},
        },
    ).status_code == 400
    # A repeating appointment recurs; the span belongs to a one-off.
    assert owner.post(
        "/items",
        json={
            "kind": "appointment", "title": "Nope", "end_date": TOMORROW,
            "time_of_day": "09:00", "end_time": "10:00",
            "repeat": {"type": "weekly", "days": [0]},
        },
    ).status_code == 400
    # An appointment on its own date may span, though.
    assert owner.post(
        "/items",
        json={
            "kind": "appointment", "title": "Conference", "date_for": TODAY,
            "end_date": TOMORROW, "time_of_day": "09:00", "end_time": "17:00",
        },
    ).status_code == 201


def test_a_span_is_on_the_board_every_day_it_runs(owner):
    trip = make_item(
        owner, kind="activity", title="Camping", date_for=YESTERDAY, end_date=TOMORROW,
        time_of_day="09:00", end_time="16:00",
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    # Mid-run: on today's board, not carried forward as overdue.
    assert any(i["id"] == trip["id"] for i in feed["today"])
    assert not any(i["id"] == trip["id"] for i in feed["overdue"])
    # And still there on its last day.
    later = owner.get(f"/items/feed?date={TOMORROW}").json()
    assert any(i["id"] == trip["id"] for i in later["today"])


def test_a_finished_span_leaves_the_board(owner):
    # A trip that ended yesterday is over, not overdue: only tasks carry
    # forward, and a span is always an activity or appointment.
    over = make_item(
        owner, kind="activity", title="Was camping",
        date_for=(dt.date.today() - dt.timedelta(days=3)).isoformat(), end_date=YESTERDAY,
        time_of_day="09:00", end_time="16:00",
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(
        i["id"] == over["id"] for i in feed["overdue"] + feed["today"] + feed["next7"]
    )


def test_a_spans_later_days_sort_like_all_day(owner):
    trip = make_item(
        owner, kind="activity", title="Camping", date_for=YESTERDAY, end_date=TOMORROW,
        time_of_day="09:00", end_time="16:00",
    )
    early = make_item(
        owner, kind="appointment", title="Dentist", date_for=TODAY,
        time_of_day="08:00", end_time="08:30",
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    order = [i["id"] for i in feed["today"]]
    # The trip's 9 AM start belonged to the day it began, so today it reads as
    # a continuing card and sits above the morning's timed appointment.
    assert order.index(trip["id"]) < order.index(early["id"])


def test_calendar_draws_a_span_on_every_day_including_one_it_started_before(owner):
    start = dt.date.today() - dt.timedelta(days=2)
    end = dt.date.today() + dt.timedelta(days=2)
    make_item(
        owner, kind="activity", title="Camping", date_for=start.isoformat(),
        end_date=end.isoformat(), time_of_day="09:00", end_time="16:00",
    )
    # A window that opens AFTER the trip began still finds it.
    win_start = dt.date.today().isoformat()
    cal = owner.get(f"/items/calendar?start={win_start}&end={end.isoformat()}").json()
    days = {d["date"]: [i["title"] for i in d["items"]] for d in cal["days"]}
    assert len(days) == 3
    assert all("Camping" in titles for titles in days.values())
    # And it stops the day after it ends.
    after = (end + dt.timedelta(days=1)).isoformat()
    cal2 = owner.get(f"/items/calendar?start={after}&end={after}").json()
    assert cal2["days"][0]["items"] == []


def test_a_span_can_be_extended_and_cleared(owner):
    trip = make_item(
        owner, kind="activity", title="Camping", date_for=TODAY, end_date=TOMORROW,
        time_of_day="09:00", end_time="16:00",
    )
    longer = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    res = owner.patch(f"/items/{trip['id']}", json={"end_date": longer})
    assert res.status_code == 200 and res.json()["end_date"] == longer
    # Clearing it puts the card back on its single day.
    back = owner.patch(f"/items/{trip['id']}", json={"end_date": None})
    assert back.status_code == 200 and back.json()["end_date"] is None
    # And it can't be moved before the start.
    assert owner.patch(
        f"/items/{trip['id']}", json={"end_date": YESTERDAY}
    ).status_code == 400


def test_a_span_is_never_checked_off(owner):
    trip = make_item(
        owner, kind="activity", title="Camping", date_for=YESTERDAY, end_date=TOMORROW,
        time_of_day="09:00", end_time="16:00",
    )
    assert owner.post(f"/items/{trip['id']}/complete?date={TODAY}").status_code == 400
    cal = owner.get(f"/items/calendar?start={YESTERDAY}&end={TOMORROW}").json()
    for day in cal["days"]:
        card = next(i for i in day["items"] if i["id"] == trip["id"])
        assert card["completed"] is False


def test_routine_takes_a_start_and_end_time(owner):
    # "Workout 8:00-8:30" is a routine with a block, not an appointment.
    card = make_item(
        owner, kind="routine", title="Stretch", time_of_day="07:00", end_time="07:30",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )
    assert card["end_time"] == "07:30:00"


def test_routine_end_time_needs_a_start_and_must_come_after_it(owner):
    everyday = {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]}
    dangling = owner.post(
        "/items",
        json={"kind": "routine", "title": "Stretch", "end_time": "07:30", "repeat": everyday},
    )
    assert dangling.status_code == 400
    backwards = owner.post(
        "/items",
        json={
            "kind": "routine", "title": "Stretch", "time_of_day": "07:30",
            "end_time": "07:00", "repeat": everyday,
        },
    )
    assert backwards.status_code == 400


def test_appointment_keeps_start_and_end(owner):
    card = make_item(
        owner, kind="appointment", title="Dentist", date_for=TODAY,
        time_of_day="09:00", end_time="09:45",
    )
    assert card["time_of_day"] == "09:00:00" and card["end_time"] == "09:45:00"
    assert card["all_day"] is False


# ---- recurrence --------------------------------------------------------------


def test_routine_requires_a_repeat_schedule(owner):
    res = owner.post("/items", json={"kind": "routine", "title": "No schedule"})
    assert res.status_code == 400


def test_weekly_routine_shows_only_on_scheduled_days(owner):
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner, kind="routine", title="Brush teeth", repeat={"type": "weekly", "days": [today_wd]}
    )
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    today_feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == routine["id"] for i in today_feed["today"])

    # Tomorrow is a different weekday, so the routine is not scheduled then.
    tomorrow_feed = owner.get(f"/items/feed?date={tomorrow}").json()
    assert not any(i["id"] == routine["id"] for i in tomorrow_feed["today"])


def test_a_repeat_that_ended_yesterday_is_off_the_board(owner):
    routine = make_item(
        owner, kind="routine", title="Daily thing",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6], "until": YESTERDAY},
    )
    assert routine["repeat"]["until"] == YESTERDAY
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == routine["id"] for i in feed["today"])
    # Its last day still has it, in the calendar's record.
    cal = owner.get(f"/items/calendar?start={YESTERDAY}&end={YESTERDAY}").json()
    assert any(i["id"] == routine["id"] for i in cal["days"][0]["items"])


def test_a_count_resolves_into_an_end_date(owner):
    monday = _monday(dt.date.today())
    routine = make_item(
        owner, kind="routine", title="Three Mondays",
        repeat={"type": "weekly", "days": [0], "anchor": monday.isoformat(), "count": 3},
    )
    # The third Monday from the anchor is the last day it may land on.
    assert routine["repeat"]["until"] == (monday + dt.timedelta(days=14)).isoformat()


def test_a_count_without_an_anchor_is_stamped_with_today(owner):
    routine = make_item(
        owner, kind="routine", title="Two days",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6], "count": 2},
    )
    # Walked from today (the stamped anchor): today and tomorrow.
    assert routine["repeat"]["until"] == TOMORROW


def test_a_count_reaching_past_the_walk_limit_is_refused(owner):
    res = owner.post(
        "/items",
        json={
            "kind": "routine", "title": "Forever and ever",
            "repeat": {
                "type": "monthly", "month_day": 1, "interval": 52,
                "anchor": "2026-01-01", "count": 4,
            },
        },
    )
    assert res.status_code == 400
    assert "too far out" in res.json()["detail"]


def test_a_repeat_ends_by_date_or_after_a_count_but_not_both(owner):
    res = owner.post(
        "/items",
        json={
            "kind": "routine", "title": "Both",
            "repeat": {"type": "weekly", "days": [0], "until": TOMORROW, "count": 3},
        },
    )
    assert res.status_code == 422


def test_a_repeat_cannot_end_before_its_anchor(owner):
    res = owner.post(
        "/items",
        json={
            "kind": "routine", "title": "Backwards",
            "repeat": {"type": "weekly", "days": [0], "anchor": TODAY, "until": YESTERDAY},
        },
    )
    assert res.status_code == 400


# ---- per-person vs shared completion -----------------------------------------


def test_routine_completion_is_per_person(owner, child, grown_child):
    kid_id, sibling_id = user_id(child), user_id(grown_child)
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner,
        kind="routine",
        title="Make bed",
        assignee_ids=[kid_id, sibling_id],
        repeat={"type": "weekly", "days": [today_wd]},
    )

    # One kid does theirs and a parent makes it official; the sibling's slot
    # is untouched.
    assert child.post(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 200
    assert owner.post(
        f"/items/{routine['id']}/complete?date={TODAY}&for={kid_id}"
    ).status_code == 200

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    card = next(i for i in feed["today"] if i["id"] == routine["id"])
    states = {c["user_id"]: c["completed"] for c in card["assignee_completions"]}
    assert states[kid_id] is True
    assert states[sibling_id] is False
    assert card["completed"] is False  # not everyone is done


def test_an_adults_routine_carries_no_completion_state(owner, parent):
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner,
        kind="routine",
        title="Morning pages",
        assignee_ids=[user_id(owner), user_id(parent)],
        repeat={"type": "weekly", "days": [today_wd]},
    )

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    card = next(i for i in feed["today"] if i["id"] == routine["id"])
    # Grown-ups can't check a routine off, so there is nothing to track: no
    # per-person rows, no count, no waiting state.
    assert card["assignee_completions"] is None
    assert card["completed"] is False
    assert card["pending"] is False
    assert card["streak"] is None


def test_a_mixed_routine_tracks_only_the_kids(owner, child, parent):
    kid_id = user_id(child)
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner,
        kind="routine",
        title="Feed the dog",
        assignee_ids=[kid_id, user_id(parent)],
        repeat={"type": "weekly", "days": [today_wd]},
    )

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    card = next(i for i in feed["today"] if i["id"] == routine["id"])
    assert [c["user_id"] for c in card["assignee_completions"]] == [kid_id]
    assert card["completed"] is False

    child.post(f"/items/{routine['id']}/complete?date={TODAY}")
    owner.post(f"/items/{routine['id']}/complete?date={TODAY}&for={kid_id}")
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    card = next(i for i in feed["today"] if i["id"] == routine["id"])
    # The one tracked row is done, so the card is: the adult on it never counted.
    assert card["completed"] is True


def test_shared_task_completion_is_single(owner, child):
    dad_id, kid_id = user_id(owner), user_id(child)
    task = make_item(owner, assignee_ids=[dad_id, kid_id])

    owner.post(f"/items/{task['id']}/complete?date={TODAY}")

    # The child sees it done too: one shared check, not a per-person one.
    feed = child.get(f"/items/feed?date={TODAY}").json()
    card = next(i for i in feed["today"] if i["id"] == task["id"])
    assert card["completed"] is True
    assert card["assignee_completions"] is None


def test_calendar_query_count_does_not_scale_with_the_span(app, owner):
    # The calendar assembles every card once per day of the range; completions
    # are prefetched in ONE query, so a month must cost the same number of
    # queries as a single day. Counting real cursor executions pins the N+1
    # regression this guards against.
    from sqlalchemy import event

    make_item(owner, kind="routine", title="Brush teeth",
              repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6], "interval": 1})
    make_item(owner, kind="appointment", title="Dentist", date_for=TODAY,
              time_of_day="09:00", end_time="09:30")
    owner.post(f"/items/{1}/complete?date={TODAY}")

    counts: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        counts.append(statement)

    engine = app.state.test_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        start = dt.date.today()
        owner.get(f"/items/calendar?start={start}&end={start}").raise_for_status()
        one_day = len(counts)
        counts.clear()
        end = start + dt.timedelta(days=27)
        owner.get(f"/items/calendar?start={start}&end={end}").raise_for_status()
        four_weeks = len(counts)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert four_weeks == one_day


# ---- kid mode: a minor's slice of the board ----------------------------------------


def feed_ids(client, date=TODAY):
    res = client.get(f"/items/feed?date={date}")
    assert res.status_code == 200, res.text
    body = res.json()
    return {i["id"] for section in body.values() if isinstance(section, list) for i in section}


def calendar_ids(client, date=TODAY):
    res = client.get(f"/items/calendar?start={date}&end={date}")
    assert res.status_code == 200, res.text
    return {i["id"] for day in res.json()["days"] for i in day["items"]}


def test_minor_sees_unassigned_family_cards_but_cannot_check_them(owner, child):
    notice = make_item(owner, title="Grandma arrives", visibility="family", date_for=TODAY)

    assert notice["id"] in feed_ids(child)
    assert notice["id"] in calendar_ids(child)
    # Visible is not checkable: the card is nobody's to do, least of all a
    # minor's (same 403 any uninvolved child gets).
    res = child.post(f"/items/{notice['id']}/complete?date={TODAY}")
    assert res.status_code == 403


def test_minor_cannot_see_family_cards_assigned_to_others(owner, child):
    mom_card = make_item(
        owner,
        title="Pick up prescriptions",
        visibility="family",
        assignee_ids=[user_id(owner)],
        date_for=TODAY,
    )

    assert mom_card["id"] not in feed_ids(child)
    assert mom_card["id"] not in calendar_ids(child)
    # Hidden means gone: completing it 404s like the card doesn't exist.
    assert child.post(f"/items/{mom_card['id']}/complete?date={TODAY}").status_code == 404
    # The parent still sees their own card - the narrowing applies to
    # child accounts alone.
    assert mom_card["id"] in feed_ids(owner)


def test_child_with_adult_birthdate_gets_the_narrowed_board(owner, grown_child):
    # Kid mode follows the role, so age never widens the board.
    mom_card = make_item(
        owner,
        title="Family dinner",
        visibility="family",
        assignee_ids=[user_id(owner)],
        date_for=TODAY,
    )
    assert mom_card["id"] not in feed_ids(grown_child)


def test_minor_sees_own_and_assigned_cards(owner, child):
    kid_id = user_id(child)
    mine = make_item(owner, title="Feed the dog", assignee_ids=[kid_id], date_for=TODAY)
    shared = make_item(
        owner,
        title="Soccer practice",
        visibility="family",
        assignee_ids=[kid_id, user_id(owner)],
        date_for=TODAY,
    )

    ids = feed_ids(child)
    assert mine["id"] in ids
    assert shared["id"] in ids


# ---- repeating appointments -----------------------------------------------------


def all_days():
    return {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]}


def test_repeating_appointment_lands_on_its_days(owner):
    today_wd = dt.date.today().weekday()
    meeting = make_item(
        owner, kind="appointment", title="Team standup",
        time_of_day="09:00", end_time="09:30",
        repeat={"type": "weekly", "days": [today_wd]},
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == meeting["id"] for i in feed["today"])
    # On a day the schedule skips, the card simply isn't there — and it is
    # never "overdue".
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    feed = owner.get(f"/items/feed?date={tomorrow}").json()
    assert not any(i["id"] == meeting["id"] for i in feed["today"])
    assert not any(i["id"] == meeting["id"] for i in feed["overdue"])


def test_repeating_appointment_is_never_checked_off(owner):
    meeting = make_item(
        owner, kind="appointment", title="Daily sync",
        time_of_day="09:00", end_time="09:30", repeat=all_days(),
    )
    res = owner.post(f"/items/{meeting['id']}/complete?date={TODAY}")
    assert res.status_code == 400
    assert res.json()["detail"] == "Appointments aren't checked off; they pass on their own"
    # Cancelling one occurrence is still how a meeting is called off.
    assert owner.post(f"/items/{meeting['id']}/cancel?date={TODAY}").json()["cancelled"] is True


def test_repeating_appointment_validation(owner):
    base = {"kind": "appointment", "title": "Bad", "repeat": all_days()}
    # Repeats and a fixed date are mutually exclusive.
    res = owner.post("/items", json={**base, "date_for": TODAY,
                                     "time_of_day": "09:00", "end_time": "09:30"})
    assert res.status_code == 400
    # A repeating appointment needs times, and can't be all-day.
    assert owner.post("/items", json=base).status_code == 400
    assert owner.post("/items", json={**base, "all_day": True}).status_code == 400
    # Tasks and activities still don't repeat.
    assert owner.post("/items", json={"kind": "task", "title": "No", "repeat": all_days()}).status_code == 400
    assert owner.post(
        "/items",
        json={"kind": "activity", "title": "No", "date_for": TODAY,
              "time_of_day": "09:00", "end_time": "10:00", "repeat": all_days()},
    ).status_code == 400


# ---- cancelling ------------------------------------------------------------------


def test_cancel_an_appointment(owner):
    appt = make_item(owner, kind="appointment", title="Dentist", date_for=TODAY,
                     time_of_day="14:00", end_time="15:00")
    res = owner.post(f"/items/{appt['id']}/cancel?date={TODAY}")
    assert res.status_code == 200
    body = res.json()
    assert body["cancelled"] is True
    assert body["completed"] is False
    # Back on: the mark lifts cleanly.
    res = owner.delete(f"/items/{appt['id']}/cancel?date={TODAY}")
    assert res.json()["cancelled"] is False


def test_cancel_is_parent_only(owner, child):
    appt = make_item(owner, kind="appointment", title="Recital", date_for=TODAY,
                     time_of_day="14:00", end_time="15:00", visibility="family")
    res = owner.post(f"/items/{appt['id']}/cancel?date={TODAY}")
    assert res.json()["cancelled"] is True
    assert res.json()["completed"] is False
    assert child.post(f"/items/{appt['id']}/cancel?date={TODAY}").status_code == 403


def test_only_events_cancel(owner):
    task = make_item(owner, kind="task", title="Chore")
    assert owner.post(f"/items/{task['id']}/cancel?date={TODAY}").status_code == 400


def test_cancelling_one_occurrence_leaves_the_rest(owner):
    meeting = make_item(owner, kind="appointment", title="Standup",
                        time_of_day="09:00", end_time="09:30", repeat=all_days())
    assert owner.post(f"/items/{meeting['id']}/cancel?date={TODAY}").json()["cancelled"] is True
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    cal = owner.get(f"/items/calendar?start={yesterday}&end={yesterday}").json()
    row = next(i for i in cal["days"][0]["items"] if i["id"] == meeting["id"])
    assert row["cancelled"] is False and row["completed"] is False


def test_cancel_accepts_a_future_day(owner):
    # Next week's dentist gets called off today. Completing stays refused
    # ahead of time; cancelling is the one mark that may land in the future.
    ahead = (dt.date.today() + dt.timedelta(days=6)).isoformat()
    meeting = make_item(owner, kind="appointment", title="Standup",
                        time_of_day="09:00", end_time="09:30", repeat=all_days())
    assert owner.post(f"/items/{meeting['id']}/cancel?date={ahead}").json()["cancelled"] is True
    # Today's occurrence is untouched; the cancelled day reads cancelled.
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not next(i for i in feed["today"] if i["id"] == meeting["id"])["cancelled"]
    assert next(i for i in feed["next7"] if i["date_for"] == ahead)["cancelled"]
    # And it can be put back on, still ahead of time.
    assert owner.delete(f"/items/{meeting['id']}/cancel?date={ahead}").status_code == 200


def test_cancel_refuses_a_day_past_the_horizon(owner):
    appt = make_item(owner, kind="appointment", title="Far off",
                     date_for=TODAY, time_of_day="09:00", end_time="10:00")
    way_out = (dt.date.today() + dt.timedelta(days=500)).isoformat()
    assert owner.post(f"/items/{appt['id']}/cancel?date={way_out}").status_code == 400


# ---- one occurrence of a repeating appointment -------------------------------------


def standup(client, **overrides):
    return make_item(client, kind="appointment", title="Standup", time_of_day="09:00",
                     end_time="09:30", repeat=all_days(), **overrides)


def day_after(n: int) -> str:
    return (dt.date.today() + dt.timedelta(days=n)).isoformat()


def test_deleting_one_occurrence_carves_out_that_day(owner):
    meeting = standup(owner)
    gone = day_after(2)
    assert owner.delete(f"/items/{meeting['id']}/occurrence?date={gone}").status_code == 204

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    days = [i["date_for"] for i in feed["next7"] if i["id"] == meeting["id"]]
    assert gone not in days
    assert day_after(1) in days and day_after(3) in days
    # Today's occurrence, and every other day, are untouched.
    assert any(i["id"] == meeting["id"] for i in feed["today"])
    cal = owner.get(f"/items/calendar?start={gone}&end={gone}").json()
    assert not any(i["id"] == meeting["id"] for i in cal["days"][0]["items"])


def test_deleting_the_same_occurrence_twice_is_refused(owner):
    meeting = standup(owner)
    assert owner.delete(f"/items/{meeting['id']}/occurrence?date={TODAY}").status_code == 204
    res = owner.delete(f"/items/{meeting['id']}/occurrence?date={TODAY}")
    assert res.status_code == 400
    assert res.json()["detail"] == "No occurrence on that day"


def test_a_carved_out_day_cannot_be_cancelled(owner):
    meeting = standup(owner)
    assert owner.delete(f"/items/{meeting['id']}/occurrence?date={TODAY}").status_code == 204
    assert owner.post(f"/items/{meeting['id']}/cancel?date={TODAY}").status_code == 400


def test_only_repeating_appointments_drop_an_occurrence(owner, child):
    one_off = make_item(owner, kind="appointment", title="Dentist", date_for=TODAY,
                        time_of_day="14:00", end_time="15:00")
    routine = make_item(owner, kind="routine", title="Brush teeth",
                        assignee_ids=[user_id(child)], repeat=all_days())
    for item in (one_off, routine):
        res = owner.delete(f"/items/{item['id']}/occurrence?date={TODAY}")
        assert res.status_code == 400
        assert res.json()["detail"] == "Only repeating appointments can drop a single occurrence"


def test_dropping_an_occurrence_is_parent_only(owner, child):
    meeting = standup(owner, visibility="family")
    assert child.delete(f"/items/{meeting['id']}/occurrence?date={TODAY}").status_code == 403


def test_dropping_an_occurrence_refuses_a_day_past_the_horizon(owner):
    meeting = standup(owner)
    way_out = (dt.date.today() + dt.timedelta(days=500)).isoformat()
    assert owner.delete(f"/items/{meeting['id']}/occurrence?date={way_out}").status_code == 400


def test_detaching_an_occurrence_leaves_a_standalone_card(owner):
    meeting = standup(owner)
    res = owner.post(
        f"/items/{meeting['id']}/occurrence?date={TODAY}",
        json={"kind": "appointment", "title": "Standup (moved)", "date_for": TODAY,
              "time_of_day": "11:00", "end_time": "11:30"},
    )
    assert res.status_code == 201, res.text
    detached = res.json()
    assert detached["id"] != meeting["id"]
    assert detached["repeat"] is None

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    today_ids = [i["id"] for i in feed["today"]]
    assert detached["id"] in today_ids
    assert meeting["id"] not in today_ids
    # The series keeps every other day.
    days = [i["date_for"] for i in feed["next7"] if i["id"] == meeting["id"]]
    assert days == [day_after(n) for n in range(1, 8)]


def test_detaching_carries_a_call_off_across(owner):
    meeting = standup(owner)
    assert owner.post(f"/items/{meeting['id']}/cancel?date={TODAY}").json()["cancelled"] is True
    res = owner.post(
        f"/items/{meeting['id']}/occurrence?date={TODAY}",
        json={"kind": "appointment", "title": "Standup", "date_for": TODAY,
              "time_of_day": "09:00", "end_time": "09:30"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["cancelled"] is True


def test_a_detached_occurrence_cannot_repeat(owner):
    meeting = standup(owner)
    res = owner.post(
        f"/items/{meeting['id']}/occurrence?date={TODAY}",
        json={"kind": "appointment", "title": "Standup", "time_of_day": "09:00",
              "end_time": "09:30", "repeat": all_days()},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "A detached appointment doesn't repeat"
    # And the day it would have carved out is still on the board.
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == meeting["id"] for i in feed["today"])


def test_reshaping_the_pattern_drops_its_carved_out_days(owner):
    # A skip is an exception to ONE pattern. Edit the pattern and it means
    # nothing, so it goes rather than leaving an invisible hole in the series.
    meeting = standup(owner)
    assert owner.delete(f"/items/{meeting['id']}/occurrence?date={TODAY}").status_code == 204
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == meeting["id"] for i in feed["today"])

    today_wd = dt.date.today().weekday()
    res = owner.patch(
        f"/items/{meeting['id']}",
        json={"repeat": {"type": "weekly", "days": [today_wd]}},
    )
    assert res.status_code == 200, res.text
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == meeting["id"] for i in feed["today"])


def test_a_time_only_edit_keeps_the_carved_out_days(owner):
    # Moving the meeting an hour later doesn't reshape which days it lands on,
    # so the week it isn't happening stays carved out.
    meeting = standup(owner)
    assert owner.delete(f"/items/{meeting['id']}/occurrence?date={TODAY}").status_code == 204
    res = owner.patch(
        f"/items/{meeting['id']}", json={"time_of_day": "10:00", "end_time": "10:30"}
    )
    assert res.status_code == 200, res.text
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == meeting["id"] for i in feed["today"])


def test_detaching_a_day_the_series_skips_is_refused(owner):
    landing = dt.date.today() + dt.timedelta(days=3)
    off_day = (landing + dt.timedelta(days=1)).isoformat()
    meeting = make_item(owner, kind="appointment", title="Weekly sync",
                        time_of_day="09:00", end_time="09:30",
                        repeat={"type": "weekly", "days": [landing.weekday()]})
    res = owner.post(
        f"/items/{meeting['id']}/occurrence?date={off_day}",
        json={"kind": "appointment", "title": "Weekly sync", "date_for": off_day,
              "time_of_day": "09:00", "end_time": "09:30"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "No occurrence on that day"


# ---- repeating appointments in the next 7 days -------------------------------------


def test_a_weekly_appointment_shows_on_its_own_day_in_next7(owner):
    # A repeating appointment is a calendar entry, so each occurrence inside
    # the window lists on the day it lands and carries that day as its date.
    landing = dt.date.today() + dt.timedelta(days=3)
    meeting = make_item(
        owner, kind="appointment", title="Team standup",
        time_of_day="09:00", end_time="09:30",
        repeat={"type": "weekly", "days": [landing.weekday()]},
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    rows = [i for i in feed["next7"] if i["id"] == meeting["id"]]
    assert len(rows) == 1
    assert rows[0]["date_for"] == landing.isoformat()
    assert not any(i["id"] == meeting["id"] for i in feed["today"])


def test_a_daily_appointment_lists_one_row_per_occurrence_day(owner):
    meeting = make_item(
        owner, kind="appointment", title="Daily sync",
        time_of_day="09:00", end_time="09:30", repeat=all_days(),
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    days = [i["date_for"] for i in feed["next7"] if i["id"] == meeting["id"]]
    assert days == [
        (dt.date.today() + dt.timedelta(days=n)).isoformat() for n in range(1, 8)
    ]
    # Today's occurrence sits in today, and is not repeated in next7.
    assert any(i["id"] == meeting["id"] for i in feed["today"])


def test_a_repeating_appointment_stops_at_its_repeat_end(owner):
    stop = dt.date.today() + dt.timedelta(days=2)
    meeting = make_item(
        owner, kind="appointment", title="Standup", time_of_day="09:00",
        end_time="09:30", repeat={**all_days(), "until": stop.isoformat()},
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    days = [i["date_for"] for i in feed["next7"] if i["id"] == meeting["id"]]
    assert days == [(dt.date.today() + dt.timedelta(days=n)).isoformat() for n in (1, 2)]


def test_routines_stay_out_of_the_next_seven_days(owner, child):
    # His call: the daily rhythm would fill the section seven times over.
    routine = make_item(
        owner, kind="routine", title="Brush teeth",
        assignee_ids=[user_id(child)], repeat=all_days(),
    )
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == routine["id"] for i in feed["next7"])
    assert any(i["id"] == routine["id"] for i in feed["today"])


def test_a_cancelled_future_occurrence_still_shows(owner):
    # The board shows it with a Cancelled chip rather than dropping it.
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    meeting = make_item(
        owner, kind="appointment", title="Standup", time_of_day="09:00",
        end_time="09:30", repeat=all_days(),
    )
    assert owner.post(
        f"/items/{meeting['id']}/cancel?date={tomorrow.isoformat()}"
    ).status_code == 200
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    row = next(
        i for i in feed["next7"]
        if i["id"] == meeting["id"] and i["date_for"] == tomorrow.isoformat()
    )
    assert row["cancelled"] is True


# ---- the completion model: only tasks are a to-do list -----------------------------


def test_appointments_and_activities_are_never_checked_off(owner):
    appt = make_item(owner, kind="appointment", title="Dentist", date_for=TODAY,
                     time_of_day="14:00", end_time="15:00")
    act = make_item(owner, kind="activity", title="Soccer", date_for=TODAY,
                    time_of_day="17:00", end_time="18:00")
    for item, kinds in ((appt, "Appointments"), (act, "Activities")):
        res = owner.post(f"/items/{item['id']}/complete?date={TODAY}")
        assert res.status_code == 400
        assert res.json()["detail"] == f"{kinds} aren't checked off; they pass on their own"
        assert owner.delete(f"/items/{item['id']}/complete?date={TODAY}").status_code == 400


def test_an_assigned_kid_cannot_check_an_appointment_either(owner, child):
    # Not a permission question: nobody checks a calendar entry off.
    appt = make_item(owner, kind="appointment", title="Checkup", visibility="family",
                     assignee_ids=[user_id(child)], date_for=TODAY,
                     time_of_day="14:00", end_time="15:00")
    assert child.post(f"/items/{appt['id']}/complete?date={TODAY}").status_code == 400


def test_an_adults_own_routine_is_not_checkable(owner, parent):
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner, kind="routine", title="Stretch", assignee_ids=[user_id(parent)],
        visibility="family", repeat={"type": "weekly", "days": [today_wd]},
    )
    res = parent.post(f"/items/{routine['id']}/complete?date={TODAY}")
    assert res.status_code == 400
    assert "approve" in res.json()["detail"]


def test_an_assigned_minor_still_checks_their_routine(owner, child):
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner, kind="routine", title="Feed the dog", assignee_ids=[user_id(child)],
        visibility="family", repeat={"type": "weekly", "days": [today_wd]},
    )
    res = child.post(f"/items/{routine['id']}/complete?date={TODAY}")
    assert res.status_code == 200 and res.json()["pending"] is True
    # And they can still withdraw their own waiting mark.
    assert child.delete(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 200
    assert owner.get("/items/pending").json() == []
