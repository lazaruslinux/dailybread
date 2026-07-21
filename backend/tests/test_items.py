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


def test_a_missed_day_can_be_marked_on_its_own_day(owner):
    # The calendar's whole point: check a routine off on the day it actually
    # was. It then reads done on that day and stays open on the others.
    routine = make_item(
        owner, kind="routine", title="Vitamins",
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )
    three_ago = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    assert owner.post(f"/items/{routine['id']}/complete?date={three_ago}").status_code == 200

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
    appt = make_item(owner, kind="appointment", title="Missed call", date_for=yesterday,
                     time_of_day="09:00", end_time="09:30")
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
    task = make_item(owner, kind="appointment", title="Dentist", date_for=TODAY,
                     time_of_day="09:00", end_time="09:30")

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


def test_overdue_carries_past_due_oneoffs_forward(owner):
    # A one-off whose date slipped by keeps showing under "overdue" until done.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    appt = make_item(owner, kind="appointment", title="Missed call", date_for=yesterday,
                     time_of_day="09:00", end_time="09:30")
    # Routines are habits, not one-offs, so a scheduled-yesterday routine is
    # never overdue; a card older than the 90-day lookback also drops off.
    make_item(owner, kind="routine", title="Daily",
              repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]})
    ancient = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    old = make_item(owner, kind="appointment", title="Ancient", date_for=ancient,
                    time_of_day="09:00", end_time="09:30")

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    overdue_ids = {i["id"] for i in feed["overdue"]}
    assert appt["id"] in overdue_ids
    assert all(i["kind"] != "routine" for i in feed["overdue"])
    assert old["id"] not in overdue_ids


def test_completing_an_overdue_card_archives_it_immediately(owner):
    # Checking off a past-due card removes it from the board at once — it
    # wasn't done today, so it doesn't sit in today's Done list. Its record
    # still shows, completed, on its own day in the calendar; undoing the
    # check brings it back to overdue.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    appt = make_item(owner, kind="appointment", title="Late chore", date_for=yesterday,
                     time_of_day="09:00", end_time="09:30")

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


# ---- visibility (private by default) -----------------------------------------


def test_new_card_is_private_by_default(owner, child):
    card = make_item(owner)  # no assignees, no visibility stated
    assert card["visibility"] == "private"

    # The child neither sees it on their board nor can check it off.
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == card["id"] for i in feed["today"])
    assert child.post(f"/items/{card['id']}/complete?date={TODAY}").status_code == 404


def test_assigning_members_keeps_a_card_private(owner, child):
    # Assigning is about who does it, not who sees it: it stays private (the
    # owner plus the assignee) unless put on the family board.
    card = make_item(owner, assignee_ids=[user_id(child)])
    assert card["visibility"] == "private"
    assert [a["id"] for a in card["assignees"]] == [user_id(child)]


def test_family_board_card_is_visible_to_all(owner, child):
    card = make_item(owner, visibility="family")
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == card["id"] for i in feed["today"])


def test_family_board_card_is_read_only_for_non_assignees(owner, child):
    # The "solo run" case: a routine the owner does alone, shown to the whole
    # family. Everyone sees it; only the owner (its sole participant) checks it.
    today_wd = dt.date.today().weekday()
    run = make_item(
        owner, kind="routine", title="Morning run", visibility="family",
        repeat={"type": "weekly", "days": [today_wd]},
    )
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == run["id"] for i in feed["today"])  # child sees it
    assert child.post(f"/items/{run['id']}/complete?date={TODAY}").status_code == 403  # read-only
    assert owner.post(f"/items/{run['id']}/complete?date={TODAY}").status_code == 200  # owner does it


def test_family_task_not_assigned_is_read_only_for_child(owner, child):
    task = make_item(owner, visibility="family")  # on the board, assigned to no one
    feed = child.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == task["id"] for i in feed["today"])
    assert child.post(f"/items/{task['id']}/complete?date={TODAY}").status_code == 403


def test_either_parent_can_check_a_family_board_card(owner, parent):
    # A co-parent can complete a family-board appointment the other parent added,
    # even though they're neither its owner nor an assignee.
    appt = make_item(
        owner, kind="appointment", title="School pickup", visibility="family",
        date_for=TODAY, time_of_day="15:00", end_time="15:30",
    )
    assert parent.post(f"/items/{appt['id']}/complete?date={TODAY}").status_code == 200


def test_parent_cannot_check_a_private_card_they_are_not_on(owner, parent):
    card = make_item(owner)  # private to the owner; the co-parent can't even see it
    assert parent.post(f"/items/{card['id']}/complete?date={TODAY}").status_code == 404


def test_parent_can_check_a_childs_routine_on_behalf(owner, child):
    today_wd = dt.date.today().weekday()
    kid = user_id(child)
    routine = make_item(
        owner, kind="routine", title="Kid brush", assignee_ids=[kid],
        visibility="family", repeat={"type": "weekly", "days": [today_wd]},
    )
    # Without 'for', the parent isn't a participant, so there's nothing to check.
    assert owner.post(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 403
    # With 'for', the parent checks it off on the child's behalf.
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


def test_routine_rejects_an_end_time(owner):
    res = owner.post(
        "/items",
        json={
            "kind": "routine", "title": "Stretch", "time_of_day": "07:00", "end_time": "07:30",
            "repeat": {"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
        },
    )
    assert res.status_code == 400


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


# ---- per-person vs shared completion -----------------------------------------


def test_routine_completion_is_per_person(owner, parent):
    dad_id, kid_id = user_id(owner), user_id(parent)
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner,
        kind="routine",
        title="Make bed",
        assignee_ids=[dad_id, kid_id],
        repeat={"type": "weekly", "days": [today_wd]},
    )

    # The second parent checks their own occurrence.
    assert parent.post(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 200

    # On the owner's board the other parent is done but the owner is not.
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    card = next(i for i in feed["today"] if i["id"] == routine["id"])
    states = {c["user_id"]: c["completed"] for c in card["assignee_completions"]}
    assert states[kid_id] is True
    assert states[dad_id] is False
    assert card["completed"] is False  # the owner's own headline state


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


def test_repeating_appointment_completes_per_occurrence(owner):
    meeting = make_item(
        owner, kind="appointment", title="Daily sync",
        time_of_day="09:00", end_time="09:30", repeat=all_days(),
    )
    assert owner.post(f"/items/{meeting['id']}/complete?date={TODAY}").json()["completed"] is True
    # Yesterday's occurrence is untouched by today's check.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    cal = owner.get(f"/items/calendar?start={yesterday}&end={yesterday}").json()
    row = next(i for i in cal["days"][0]["items"] if i["id"] == meeting["id"])
    assert row["completed"] is False


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


def test_cancel_replaces_a_done_mark_and_is_parent_only(owner, child):
    appt = make_item(owner, kind="appointment", title="Recital", date_for=TODAY,
                     time_of_day="14:00", end_time="15:00", visibility="family")
    owner.post(f"/items/{appt['id']}/complete?date={TODAY}")
    res = owner.post(f"/items/{appt['id']}/cancel?date={TODAY}")
    assert res.json()["cancelled"] is True
    assert res.json()["completed"] is False
    assert child.post(f"/items/{appt['id']}/cancel?date={TODAY}").status_code == 403


def test_a_cancelled_occurrence_refuses_a_done_mark(owner):
    appt = make_item(owner, kind="appointment", title="Dentist", date_for=TODAY,
                     time_of_day="14:00", end_time="15:00")
    owner.post(f"/items/{appt['id']}/cancel?date={TODAY}")
    res = owner.post(f"/items/{appt['id']}/complete?date={TODAY}")
    assert res.status_code == 400
    # Put it back on, and it completes like normal again.
    owner.delete(f"/items/{appt['id']}/cancel?date={TODAY}")
    res = owner.post(f"/items/{appt['id']}/complete?date={TODAY}")
    assert res.status_code == 200
    assert res.json()["completed"] is True


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
