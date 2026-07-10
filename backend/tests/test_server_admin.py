"""Server-admin powers that reach across the family wall — deliberately the
only two that exist: rescuing a locked-out account's password, and removing
a whole household. Both are owner-only; family admins stay walled in.
"""

import datetime as dt

import pytest

from tests.conftest import user_id
from tests.test_villages import _create, make_recipe, share


@pytest.fixture()
def village(owner, other):
    """Owner's family founds a village; family B joins with the code."""
    created = _create(owner)
    res = other.post("/villages/join", json={"code": created["invite_code"]})
    assert res.status_code == 200, res.text
    return created["id"]


# ---- the rescue reset ------------------------------------------------------------


def test_owner_rescues_a_locked_out_family(app, owner, other):
    """Family B's only admin forgot their password. The server admin resets
    it; the new password works, and B's old session is ended everywhere."""
    from fastapi.testclient import TestClient

    other_id = user_id(other)
    res = owner.post(f"/auth/users/{other_id}/rescue", json={"password": "a-fresh-start"})
    assert res.status_code == 200, res.text

    assert other.get("/auth/me").status_code == 401  # old session is stale
    fresh = TestClient(app)
    assert fresh.post(
        "/auth/login", json={"username": "josh", "password": "a-fresh-start"}
    ).status_code == 200


def test_rescue_is_owner_only(owner, other, parent):
    target = user_id(owner)
    # A family admin (other) and a plain parent both get walled off.
    assert other.post(f"/auth/users/{target}/rescue", json={"password": "long-enough"}).status_code == 403
    assert parent.post(f"/auth/users/{target}/rescue", json={"password": "long-enough"}).status_code == 403


def test_rescue_validates_like_any_reset(owner, other):
    other_id = user_id(other)
    assert owner.post(f"/auth/users/{other_id}/rescue", json={"password": "short"}).status_code == 422
    assert owner.post("/auth/users/99999/rescue", json={"password": "long-enough"}).status_code == 404


def test_owner_rescuing_themselves_stays_signed_in(owner):
    me = user_id(owner)
    assert owner.post(f"/auth/users/{me}/rescue", json={"password": "a-fresh-start"}).status_code == 200
    assert owner.get("/auth/me").status_code == 200  # cookie re-issued in the response


# ---- removing a household --------------------------------------------------------


def _fill_household(client):
    """Give a family one of everything deletion has to reach: a checked-off
    card, a store with an item, a shared recipe with a custom-food line."""
    res = client.post("/items", json={"kind": "task", "title": "Pack boxes"})
    assert res.status_code == 201, res.text
    today = dt.date.today().isoformat()
    assert client.post(f"/items/{res.json()['id']}/complete?date={today}").status_code == 200
    res = client.post("/grocery/lists", json={"name": "Costco"})
    assert res.status_code == 201, res.text
    res = client.post("/grocery", json={"title": "Milk", "list_id": res.json()["id"]})
    assert res.status_code == 201, res.text
    return make_recipe(client, name="Farewell pie", custom=True)


def test_owner_removes_a_family_and_everything_it_owned(owner, other, village):
    """Family B lived a full life — board, kitchen, a village share the owner
    saved a copy of — then moves out. The copy survives (it's the owner's,
    same as when a family leaves a village); the village stays up because the
    owner's family is still in it; B's session and data are gone."""
    recipe = _fill_household(other)
    entry = share(other, village, recipe["id"])
    copy = owner.post(f"/villages/shelf/{entry['share_id']}/copy").json()

    b_family = other.get("/families/me").json()["id"]
    res = owner.delete(f"/families/{b_family}")
    assert res.status_code == 204, res.text

    assert other.get("/auth/me").status_code == 401  # the whole household is gone
    assert owner.get("/villages/shelf").json() == []  # their share left with them
    mine = [r["name"] for r in owner.get("/recipes").json()]
    assert "Farewell pie" in mine  # the saved copy is the owner's, and stays

    tree = owner.get("/auth/overview").json()
    all_families = [f["name"] for v in tree["villages"] for f in v["families"]] + [
        f["name"] for f in tree["solo_families"]
    ]
    assert "The Bs" not in all_families
    # The village survives with the owner's family still inside.
    assert [v["name"] for v in tree["villages"]] == ["Bread Circle"]


def test_removing_the_last_family_turns_off_a_villages_lights(owner, other):
    created = _create(other, name="B Lane")  # B founds a village, alone
    b_family = other.get("/families/me").json()["id"]
    assert owner.delete(f"/families/{b_family}").status_code == 204

    tree = owner.get("/auth/overview").json()
    assert tree["villages"] == []


def test_the_owners_own_family_is_not_deletable(owner):
    my_family = owner.get("/families/me").json()["id"]
    assert owner.delete(f"/families/{my_family}").status_code == 400


def test_removing_a_family_is_owner_only(owner, other):
    a_family = owner.get("/families/me").json()["id"]
    assert other.delete(f"/families/{a_family}").status_code == 403
    assert owner.delete("/families/99999").status_code == 404
