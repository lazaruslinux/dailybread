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


def test_completed_undated_todo_leaves_the_board(owner):
    item = make_item(owner)  # undated todo -> "anytime" bucket
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert any(i["id"] == item["id"] for i in feed["anytime"])

    owner.post(f"/items/{item['id']}/complete?date={TODAY}")
    feed = owner.get(f"/items/feed?date={TODAY}").json()
    assert not any(i["id"] == item["id"] for i in feed["anytime"])
