"""Server-admin powers that reach across the family wall — deliberately the
only ones that exist: rescuing a locked-out account's password, removing a
whole household, removing a single account, and renaming or dissolving any
village. All are owner-only; family admins stay walled in.
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


# ---- removing an individual account across the wall ------------------------------
# The server admin may remove ONE account of any family (not just a whole
# household). Family admins stay scoped to their own members, exactly as before.


def test_owner_removes_a_cross_family_member_with_data(app, owner, other):
    """The server admin deletes a single member of family B who carries a push
    subscription and a diary entry — the users.id FKs cascade them away, and
    the rest of family B is untouched."""
    from tests.conftest import login

    creds = {"username": "bmember", "display_name": "Bea Member", "password": "bea-pass-999"}
    assert other.post("/auth/users", json={**creds, "role": "parent"}).status_code == 201
    member = login(app, creds)
    member_id = user_id(member)

    member.put(
        "/push/subscription",
        json={"endpoint": "https://push.example/bmember", "keys": {"p256dh": "k", "auth": "a"}},
    )
    today = dt.date.today().isoformat()
    assert member.post(
        "/diary",
        json={
            "date_for": today, "slot": "breakfast", "amount": 100, "unit": "g",
            "source": "usda", "source_id": "111222", "name": "Rolled Oats", "brand": "",
            "calories": 100.0, "protein_g": 10.0, "carbs_g": 20.0, "fat_g": 2.0,
        },
    ).status_code == 201

    assert owner.delete(f"/auth/users/{member_id}").status_code == 204
    assert member.get("/auth/me").status_code == 401  # the account is gone

    # Family B itself survives, minus the one member.
    b_family = other.get("/families/me").json()["id"]
    tree = owner.get("/auth/overview").json()
    b = next(
        f for v in tree["villages"] for f in v["families"] if f["id"] == b_family
    ) if any(f["id"] == b_family for v in tree["villages"] for f in v["families"]) else next(
        f for f in tree["solo_families"] if f["id"] == b_family
    )
    assert "bmember" not in [u["username"] for u in b["users"]]
    assert "josh" in [u["username"] for u in b["users"]]  # B's head remains


def test_owner_cannot_delete_their_own_account(owner):
    me = user_id(owner)
    assert owner.delete(f"/auth/users/{me}").status_code == 400


def test_non_owner_cross_family_delete_still_404s(owner, other):
    """Regression: a family admin still can't reach another family's member —
    the same 404 as for an id that doesn't exist."""
    owner_id = user_id(owner)
    assert other.delete(f"/auth/users/{owner_id}").status_code == 404


def test_owner_cannot_strand_a_household_by_deleting_its_only_admin(app, owner, other):
    """Family B has an admin (josh) plus a plain member. Removing josh would
    leave the member with no admin — and nothing can promote a replacement
    across the wall — so the server admin is refused and pointed at removing
    the whole household instead."""
    creds = {"username": "cmember", "display_name": "Cee Member", "password": "cee-pass-999"}
    assert other.post(
        "/auth/users", json={**creds, "role": "parent", "is_admin": False}
    ).status_code == 201

    josh_id = user_id(other)
    res = owner.delete(f"/auth/users/{josh_id}")
    assert res.status_code == 400
    assert "household" in res.json()["detail"].lower()

    # josh is untouched.
    assert other.get("/auth/me").status_code == 200


def test_owner_removes_one_of_two_admins(app, owner, other):
    """With a co-admin present the family still has an admin afterwards, so the
    deletion goes through."""
    creds = {"username": "dmember", "display_name": "Dee Admin", "password": "dee-pass-999"}
    assert other.post(
        "/auth/users", json={**creds, "role": "parent", "is_admin": True}
    ).status_code == 201

    josh_id = user_id(other)
    assert owner.delete(f"/auth/users/{josh_id}").status_code == 204
    assert other.get("/auth/me").status_code == 401


def test_owner_removes_a_sole_member_even_if_admin(app, owner, other):
    """The last-admin guard only fires when OTHER members remain — an admin who
    is the household's only member can still be removed (leaving an empty
    family), preserving the emptied-family behavior."""
    josh_id = user_id(other)
    assert owner.delete(f"/auth/users/{josh_id}").status_code == 204
    assert other.get("/auth/me").status_code == 401


def test_overview_lists_a_family_emptied_of_members(app, owner, other):
    """After the server admin removes every member of family B, the overview
    still lists the family with an empty users array (no crash)."""
    b_family = other.get("/families/me").json()["id"]
    other_id = user_id(other)
    assert owner.delete(f"/auth/users/{other_id}").status_code == 204

    tree = owner.get("/auth/overview").json()
    b = next(f for f in tree["solo_families"] if f["id"] == b_family)
    assert b["users"] == []
