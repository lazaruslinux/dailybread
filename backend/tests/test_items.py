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


def test_child_checks_own_and_family_cards(owner, child):
    kid_id = user_id(child)
    own = make_item(owner, assignee_ids=[kid_id])
    family = make_item(owner)  # no assignees = whole family

    assert child.post(f"/items/{own['id']}/complete?date={TODAY}").status_code == 200
    assert child.post(f"/items/{family['id']}/complete?date={TODAY}").status_code == 200


def test_child_cannot_check_someone_elses_card(owner, child):
    owners_card = make_item(owner, assignee_ids=[user_id(owner)])
    res = child.post(f"/items/{owners_card['id']}/complete?date={TODAY}")
    assert res.status_code == 403


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

    # Clearing to [] makes it a whole-family card again.
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
