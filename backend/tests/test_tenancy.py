"""Multi-family tenancy: zero cross-family visibility on every endpoint.

Two households share one install: Family A (the bootstrap owner's) and
Family B (created through the new-household flow). B must never see, touch,
or even confirm the existence of A's users, items, moods, or grocery data.
Cross-family lookups return 404 — not 403 — so B can't tell a real id from
a nonexistent one.
"""

import datetime as dt

import pytest

from tests.conftest import login, user_id

TODAY = str(dt.date.today())
JOSH = {"username": "josh", "display_name": "Josh", "password": "josh-pass-1234"}
BKID = {"username": "bkid", "display_name": "B Kid", "password": "bkid-pass-1234"}


@pytest.fixture()
def homeless(app, owner):
    """A new-household account that hasn't created its family yet."""
    res = owner.post("/auth/users", json={**JOSH, "role": "parent", "new_household": True})
    assert res.status_code == 201, res.text
    return login(app, JOSH)


@pytest.fixture()
def other(homeless):
    """Family B's head of household, family created."""
    res = homeless.post("/families", json={"name": "The Bs"})
    assert res.status_code == 201, res.text
    return homeless


def test_bootstrap_owner_lands_in_a_family(owner):
    assert owner.get("/auth/me").json()["family_id"] is not None


def test_new_household_must_be_a_parent(owner):
    res = owner.post("/auth/users", json={**BKID, "role": "child", "new_household": True})
    assert res.status_code == 400


def test_no_family_yet_means_locked_out_of_data(homeless):
    assert homeless.get("/auth/me").status_code == 200  # can see who they are
    assert homeless.get(f"/items/feed?date={TODAY}").status_code == 403
    assert homeless.get("/grocery").status_code == 403
    assert homeless.get(f"/users?date={TODAY}").status_code == 403
    assert homeless.post("/items", json={"kind": "todo", "title": "X"}).status_code == 403


def test_create_family_unlocks_and_promotes_to_head(other):
    me = other.get("/auth/me").json()
    assert me["family_id"] is not None
    assert me["role"] == "parent"
    assert me["is_admin"] is True
    feed = other.get(f"/items/feed?date={TODAY}")
    assert feed.status_code == 200
    body = feed.json()
    assert body["today"] == [] and body["anytime"] == [] and body["upcoming"] == []


def test_cannot_create_a_second_family(owner, other):
    assert other.post("/families", json={"name": "Again"}).status_code == 400
    assert owner.post("/families", json={"name": "Mine too"}).status_code == 400


def test_admin_lists_only_own_family(owner, other, child):
    a_names = {u["username"] for u in owner.get("/auth/users").json()}
    assert JOSH["username"] not in a_names

    other.post("/auth/users", json={**BKID, "role": "child"})
    b_names = {u["username"] for u in other.get("/auth/users").json()}
    assert b_names == {JOSH["username"], BKID["username"]}


def test_cross_family_user_management_is_404(owner, other, child):
    kid_id = user_id(child)
    assert other.patch(f"/auth/users/{kid_id}", json={"display_name": "X"}).status_code == 404
    assert other.delete(f"/auth/users/{kid_id}").status_code == 404


def test_items_are_invisible_across_families(owner, other):
    created = owner.post("/items", json={"kind": "todo", "title": "A-only secret"})
    item_id = created.json()["id"]

    feed = other.get(f"/items/feed?date={TODAY}").json()
    titles = [i["title"] for sec in ("today", "anytime", "upcoming") for i in feed[sec]]
    assert "A-only secret" not in titles

    assert other.patch(f"/items/{item_id}", json={"title": "hijack"}).status_code == 404
    assert other.delete(f"/items/{item_id}").status_code == 404
    assert other.post(f"/items/{item_id}/complete?date={TODAY}").status_code == 404
    assert other.delete(f"/items/{item_id}/complete?date={TODAY}").status_code == 404


def test_cannot_assign_across_families(owner, other, child):
    kid_id = user_id(child)
    res = other.post("/items", json={"kind": "todo", "title": "X", "assignee_id": kid_id})
    assert res.status_code == 400


def test_family_strip_and_profiles_are_scoped(owner, other, child):
    owner.put("/me/mood", json={"date_for": TODAY, "level": "sunny", "hidden": False})

    strip = other.get(f"/users?date={TODAY}").json()
    assert {m["username"] for m in strip} == {JOSH["username"]}

    owner_id = user_id(owner)
    assert other.get(f"/users/{owner_id}/profile?date={TODAY}").status_code == 404


def test_grocery_is_scoped_including_stores_and_clear(owner, other):
    store = owner.post("/grocery/lists", json={"name": "Costco"}).json()
    owner.post("/grocery", json={"title": "A milk", "list_id": store["id"]})
    checked = owner.post("/grocery", json={"title": "A eggs"}).json()
    owner.patch(f"/grocery/{checked['id']}", json={"checked": True})

    state = other.get("/grocery").json()
    assert state["lists"] == [] and state["items"] == []

    # A's store id is a bad reference from B's side, and both families can
    # have a store with the same name.
    assert other.post("/grocery", json={"title": "X", "list_id": store["id"]}).status_code == 400
    assert other.delete(f"/grocery/lists/{store['id']}").status_code == 404
    assert other.post("/grocery/lists", json={"name": "Costco"}).status_code == 201
    assert other.patch(f"/grocery/{checked['id']}", json={"checked": False}).status_code == 404

    # B clearing checked items must not sweep A's checked General item.
    other.post("/grocery/clear-checked")
    a_titles = {i["title"] for i in owner.get("/grocery").json()["items"]}
    assert "A eggs" in a_titles
