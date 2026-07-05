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
    mine = next(i for i in feed["anytime"] if i["id"] == card["id"])
    assert {a["id"] for a in mine["assignees"]} == {dad_id, kid_id}

    # A child listed among several assignees may still check the card off.
    assert child.post(f"/items/{card['id']}/complete?date={TODAY}").status_code == 200


def test_editing_assignees_replaces_the_whole_set(owner, child):
    kid_id = user_id(child)
    card = make_item(owner, assignee_ids=[user_id(owner)])
    owner.patch(f"/items/{card['id']}", json={"assignee_ids": [kid_id]})

    # Now it's the child's, not the owner's: the owner is no longer an assignee.
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = next(i for i in feed["anytime"] if i["id"] == card["id"])
    assert [a["id"] for a in mine["assignees"]] == [kid_id]

    # Clearing to [] leaves the card owned by (and visible to) the owner alone.
    owner.patch(f"/items/{card['id']}", json={"assignee_ids": []})
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = next(i for i in feed["anytime"] if i["id"] == card["id"])
    assert mine["assignees"] == []


def test_uncomplete_reverses_a_checkoff(owner):
    item = make_item(owner)
    assert owner.post(f"/items/{item['id']}/complete?date={TODAY}").json()["completed"] is True
    assert owner.delete(f"/items/{item['id']}/complete?date={TODAY}").json()["completed"] is False


def test_feed_rejects_faraway_dates(owner):
    far = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    assert owner.get(f"/items/feed?date={far}").status_code == 400


def test_checked_undated_todo_stays_crossed_out_for_the_day(owner):
    item = make_item(owner)  # undated todo -> "anytime" bucket
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == item["id"] for i in feed["anytime"])

    # Checked today: stays on the board, flagged completed, sorted last.
    owner.post(f"/items/{item['id']}/complete?date={TODAY}")
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    mine = [i for i in feed["anytime"] if i["id"] == item["id"]]
    assert mine and mine[0]["completed"] is True
    assert feed["anytime"][-1]["id"] == item["id"]


def test_undated_todo_completed_yesterday_is_archived(owner):
    item = make_item(owner)
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    owner.post(f"/items/{item['id']}/complete?date={yesterday}")

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == item["id"] for i in feed["anytime"])


def test_upcoming_has_no_horizon(owner):
    far = (dt.date.today() + dt.timedelta(days=45)).isoformat()
    item = make_item(owner, kind="appointment", title="Vacation", date_for=far, time_of_day="09:00")

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == item["id"] for i in feed["upcoming"])


def test_activity_and_appointment_need_a_date_and_time(owner):
    # Missing both, or missing the time, is rejected.
    assert owner.post("/items", json={"kind": "activity", "title": "Gym"}).status_code == 400
    assert (
        owner.post(
            "/items", json={"kind": "appointment", "title": "Dentist", "date_for": TODAY}
        ).status_code
        == 400
    )
    ok = owner.post(
        "/items",
        json={"kind": "activity", "title": "Gym", "date_for": TODAY, "time_of_day": "17:00"},
    )
    assert ok.status_code == 201, ok.text


def test_editing_cannot_strand_an_appointment(owner):
    card = make_item(
        owner, kind="appointment", title="Dentist", date_for=TODAY, time_of_day="09:00"
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
    assert not any(i["id"] == card["id"] for i in feed["anytime"])
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
    assert any(i["id"] == card["id"] for i in feed["anytime"])


def test_family_board_card_is_read_only_for_non_assignees(owner, child):
    # The "Alex Run" case: a routine the owner does alone, shown to the whole
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
    assert any(i["id"] == task["id"] for i in feed["anytime"])
    assert child.post(f"/items/{task['id']}/complete?date={TODAY}").status_code == 403


def test_either_parent_can_check_a_family_board_card(owner, parent):
    # A co-parent can complete a family-board appointment the other parent added,
    # even though they're neither its owner nor an assignee.
    appt = make_item(
        owner, kind="appointment", title="School pickup", visibility="family",
        date_for=TODAY, time_of_day="15:00",
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


def test_routine_completion_is_per_person(owner, child):
    dad_id, kid_id = user_id(owner), user_id(child)
    today_wd = dt.date.today().weekday()
    routine = make_item(
        owner,
        kind="routine",
        title="Make bed",
        assignee_ids=[dad_id, kid_id],
        repeat={"type": "weekly", "days": [today_wd]},
    )

    # The child checks their own occurrence.
    assert child.post(f"/items/{routine['id']}/complete?date={TODAY}").status_code == 200

    # On the owner's board the child is done but the owner is not.
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
    card = next(i for i in feed["anytime"] if i["id"] == task["id"])
    assert card["completed"] is True
    assert card["assignee_completions"] is None
