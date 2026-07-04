"""Board items: who can create, edit, delete, and check off what."""

import datetime as dt

from tests.conftest import user_id

TODAY = dt.date.today().isoformat()


def make_item(client, **overrides):
    payload = {"kind": "todo", "title": "Test card", **overrides}
    res = client.post("/items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_child_cannot_create_edit_or_delete(owner, child):
    item = make_item(owner)
    assert child.post("/items", json={"kind": "todo", "title": "Nope"}).status_code == 403
    assert child.patch(f"/items/{item['id']}", json={"title": "Nope"}).status_code == 403
    assert child.delete(f"/items/{item['id']}").status_code == 403


def test_anon_gets_401_everywhere(anon):
    assert anon.get(f"/items/feed?date={TODAY}").status_code == 401
    assert anon.post("/items", json={"kind": "todo", "title": "X"}).status_code == 401


def test_routines_cannot_carry_a_date(owner):
    res = owner.post(
        "/items", json={"kind": "routine", "title": "Daily thing", "date_for": TODAY}
    )
    assert res.status_code == 400


def test_child_checks_own_and_family_cards(owner, child):
    kid_id = user_id(child)
    own = make_item(owner, assignee_id=kid_id)
    family = make_item(owner)  # no assignee = whole family

    assert child.post(f"/items/{own['id']}/complete?date={TODAY}").status_code == 200
    assert child.post(f"/items/{family['id']}/complete?date={TODAY}").status_code == 200


def test_child_cannot_check_someone_elses_card(owner, child):
    owners_card = make_item(owner, assignee_id=user_id(owner))
    res = child.post(f"/items/{owners_card['id']}/complete?date={TODAY}")
    assert res.status_code == 403


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
    item = make_item(owner, kind="event", title="Vacation", date_for=far)

    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == item["id"] for i in feed["upcoming"])
