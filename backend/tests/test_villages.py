"""Villages slice 1: membership and invite codes.

The invariants under test: nothing about villages is discoverable (uniform
404s, code never readable back), codes are single-use and throttled, and
membership changes only ever touch the acting family.
"""
import datetime as dt
import re

import pytest

from app import throttle
from app.routers import villages as villages_router


@pytest.fixture(autouse=True)
def _clean_throttle():
    throttle.clear()
    yield
    throttle.clear()


def _create(client, name="Bread Circle"):
    res = client.post("/villages", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture()
def village(owner, other):
    """Owner's family founds a village; family B joins with the code."""
    created = _create(owner)
    res = other.post("/villages/join", json={"code": created["invite_code"]})
    assert res.status_code == 200, res.text
    return created["id"]


# ---- creating ------------------------------------------------------------------


def test_create_returns_code_exactly_once(owner):
    created = _create(owner)
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", created["invite_code"])
    assert created["invite_active"] is True
    assert created["families"][0]["name"] == "Home"

    # The list endpoint reports status only — the code never appears again.
    listed = owner.get("/villages").json()
    assert len(listed) == 1
    assert listed[0]["invite_active"] is True
    assert listed[0]["invite_expires_at"] is not None
    assert "invite_code" not in listed[0]


def test_only_admins_create(parent, child, homeless):
    for client in (parent, child, homeless):
        assert client.post("/villages", json={"name": "Nope"}).status_code == 403


def test_any_member_may_list(child, owner):
    _create(owner)
    res = child.get("/villages")
    assert res.status_code == 200
    assert len(res.json()) == 1


# ---- joining -------------------------------------------------------------------


def test_join_links_both_families(village, owner, other):
    for client in (owner, other):
        listed = client.get("/villages").json()
        assert [f["name"] for f in listed[0]["families"]] == ["Home", "The Bs"]
    # The consumed code reads as no active invite.
    assert owner.get("/villages").json()[0]["invite_active"] is False


def test_code_is_single_use(owner, other):
    created = _create(owner)
    assert other.post("/villages/join", json={"code": created["invite_code"]}).status_code == 200
    # The same code again finds nothing — it died with the join.
    res = other.post("/villages/join", json={"code": created["invite_code"]})
    assert res.status_code == 404


def test_code_normalization(owner, other):
    created = _create(owner)
    sloppy = created["invite_code"].replace("-", " ").lower()
    assert other.post("/villages/join", json={"code": sloppy}).status_code == 200


def test_expired_code_is_uniformly_invalid(owner, other, monkeypatch):
    monkeypatch.setattr(villages_router, "INVITE_TTL", dt.timedelta(hours=-1))
    created = _create(owner)
    res = other.post("/villages/join", json={"code": created["invite_code"]})
    assert res.status_code == 404
    assert res.json()["detail"] == "That code isn't valid"
    # And the founder's list shows no active invite to hand out.
    assert owner.get("/villages").json()[0]["invite_active"] is False


def test_wrong_code_404_then_throttled(owner, other):
    _create(owner)
    for _ in range(throttle.MAX_FAILURES):
        res = other.post("/villages/join", json={"code": "WRONGCOD"})
        assert res.status_code == 404
        assert res.json()["detail"] == "That code isn't valid"
    assert other.post("/villages/join", json={"code": "WRONGCOD"}).status_code == 429


def test_join_requires_admin(village, owner, parent, child):
    fresh = owner.post(f"/villages/{village}/invite").json()
    for client in (parent, child):
        assert client.post("/villages/join", json={"code": fresh["invite_code"]}).status_code == 403


def test_double_join_is_a_plain_400(village, owner, other):
    fresh = owner.post(f"/villages/{village}/invite").json()
    res = other.post("/villages/join", json={"code": fresh["invite_code"]})
    assert res.status_code == 400
    # The code wasn't consumed by the failed attempt — it's still someone's door key.
    assert owner.get("/villages").json()[0]["invite_active"] is True


# ---- the join confirmation ------------------------------------------------------


def test_check_names_the_village_without_consuming(owner, other):
    created = _create(owner)
    for _ in range(2):
        res = other.post("/villages/join/check", json={"code": created["invite_code"]})
        assert res.status_code == 200
        assert res.json() == {"name": "Bread Circle", "families": ["Home"]}
    # Still joinable after being checked.
    assert other.post("/villages/join", json={"code": created["invite_code"]}).status_code == 200


def test_check_is_uniformly_invalid_and_shares_the_throttle(owner, other):
    from app import throttle as throttle_mod

    _create(owner)
    for _ in range(throttle_mod.MAX_FAILURES):
        res = other.post("/villages/join/check", json={"code": "WRONGCOD"})
        assert res.status_code == 404
        assert res.json()["detail"] == "That code isn't valid"
    # Check failures count against the same bucket the join uses.
    assert other.post("/villages/join", json={"code": "WRONGCOD"}).status_code == 429


# ---- parents on the village card -------------------------------------------------


def test_village_shows_parents_and_never_children(app, village, owner, other, child, grown_child):
    listed = owner.get("/villages").json()[0]
    by_family = {f["name"]: f for f in listed["families"]}
    home_names = [p["display_name"] for p in by_family["Home"]["parents"]]
    assert "Owner Parent" in home_names
    # Children stay behind the family wall — even with an adult birthdate.
    assert "The Kid" not in home_names
    assert "Grown Kid" not in home_names
    # The photo handle rides along (the one cross-family opening); no photo
    # yet reads as None and the client falls back to initials.
    assert by_family["Home"]["parents"][0]["avatar_updated_at"] is None
    # Family B's head shows for family A too.
    assert [p["display_name"] for p in by_family["The Bs"]["parents"]] == ["Josh"]


def test_one_village_per_family(village, owner, other):
    # For now a family belongs to at most one village: founding a second is
    # refused, and so is joining one.
    assert owner.post("/villages", json={"name": "Second Circle"}).status_code == 400
    assert other.post("/villages", json={"name": "Second Circle"}).status_code == 400


def test_join_refused_when_already_in_a_village(app, village, owner, other):
    # A third family founds its own village and invites family B — who is
    # already in one, so the valid code earns a plain 400.
    from tests.conftest import login

    third_head = {"username": "cathy", "display_name": "Cathy", "password": "cathy-pass-123"}
    res = owner.post("/auth/users", json={**third_head, "role": "parent", "new_household": True})
    assert res.status_code == 201
    cathy = login(app, third_head)
    assert cathy.post("/families", json={"name": "The Cs"}).status_code == 201
    created = _create(cathy, name="Other Circle")
    res = other.post("/villages/join", json={"code": created["invite_code"]})
    assert res.status_code == 400
    # The code wasn't consumed by the refusal.
    assert cathy.get("/villages").json()[0]["invite_active"] is True


# ---- regenerating --------------------------------------------------------------


def test_regenerate_kills_the_old_code(owner, other):
    created = _create(owner)
    fresh = owner.post(f"/villages/{created['id']}/invite")
    assert fresh.status_code == 200
    assert other.post("/villages/join", json={"code": created["invite_code"]}).status_code == 404
    assert other.post("/villages/join", json={"code": fresh.json()["invite_code"]}).status_code == 200


def test_member_family_admin_may_regenerate(village, other):
    res = other.post(f"/villages/{village}/invite")
    assert res.status_code == 200


# ---- leaving -------------------------------------------------------------------


def test_leave_removes_only_the_leaver(village, owner, other):
    assert other.delete(f"/villages/{village}/membership").status_code == 204
    assert other.get("/villages").json() == []
    remaining = owner.get("/villages").json()
    assert [f["name"] for f in remaining[0]["families"]] == ["Home"]


def test_last_family_out_deletes_the_village(owner):
    created = _create(owner)
    assert owner.delete(f"/villages/{created['id']}/membership").status_code == 204
    assert owner.get("/villages").json() == []
    # The village is gone, so a member action against its id 404s.
    assert owner.post(f"/villages/{created['id']}/invite").status_code == 404


def test_leave_requires_admin(village, parent):
    assert parent.delete(f"/villages/{village}/membership").status_code == 403


# ---- nothing leaks -------------------------------------------------------------


def test_village_ids_404_for_non_members(owner, other):
    """The tenancy invariant, extended to villages: an id outside your
    memberships answers exactly like an id that doesn't exist."""
    created = _create(owner)  # family B never joins
    for res in (
        other.post(f"/villages/{created['id']}/invite"),
        other.delete(f"/villages/{created['id']}/membership"),
        other.post("/villages/9999/invite"),
        other.delete("/villages/9999/membership"),
    ):
        assert res.status_code == 404
        assert res.json()["detail"] in ("No such village",)


def test_village_mates_cannot_open_each_others_profiles(village, owner, other):
    """Being linked in a village opens NOTHING personal: profiles, moods,
    status, and boards stay family-only, so a village-mate's id answers like
    it doesn't exist."""
    from tests.conftest import user_id

    today = dt.date.today().isoformat()
    owner_id = user_id(owner)
    assert other.get(f"/users/{owner_id}/profile?date={today}").status_code == 404
    # And the family strip never mixes families, village or not.
    strip = other.get(f"/users?date={today}").json()
    assert all(m["family_id"] == strip[0]["family_id"] for m in strip)


def test_village_parent_avatar_is_reachable_but_nothing_else(village, owner, other):
    """The avatar IMAGE crosses the wall for village parents; the profile
    never does, and a family outside the village still sees nothing."""
    from tests.conftest import user_id
    import datetime as _dt

    owner_id = user_id(owner)
    today = _dt.date.today().isoformat()
    # No photo uploaded: a village-mate gets the "No avatar" 404 (permission
    # passed), while the profile stays a "No such user" wall.
    res = other.get(f"/users/{owner_id}/avatar")
    assert res.status_code == 404
    assert res.json()["detail"] == "No avatar"
    res = other.get(f"/users/{owner_id}/profile?date={today}")
    assert res.status_code == 404
    assert res.json()["detail"] == "No such user"


def test_child_avatars_never_cross_the_wall(village, owner, other, child):
    from tests.conftest import user_id

    res = other.get(f"/users/{user_id(child)}/avatar")
    assert res.status_code == 404
    assert res.json()["detail"] == "No such user"


# ---- the recipe shelf -------------------------------------------------------------


def make_recipe(client, name="Pancakes", custom=False):
    """A two-line recipe: one shared-cache food, optionally one custom food."""
    lines = [
        {
            "source": "usda", "source_id": "1111", "name": "Flour", "brand": "",
            "amount": 200, "unit": "g", "calories": 364.0, "protein_g": 10.0,
        }
    ]
    if custom:
        res = client.post(
            "/foods",
            json={
                "name": "Grandma's mix", "brand": "", "base_unit": "g",
                "calories": 400.0, "protein_g": 8.0,
                "servings": [{"name": "1 scoop", "grams": 30.0}],
            },
        )
        assert res.status_code == 201, res.text
        lines.append({
            "food_id": res.json()["id"], "source": "custom", "name": "Grandma's mix",
            "amount": 60, "unit": "g",
        })
    res = client.post(
        "/recipes", json={"name": name, "servings": 4, "steps": "Mix. Cook.", "ingredients": lines}
    )
    assert res.status_code == 201, res.text
    return res.json()


def share(client, village_id, recipe_id):
    res = client.post(f"/villages/{village_id}/recipes", json={"recipe_id": recipe_id})
    assert res.status_code == 201, res.text
    return res.json()


def test_shelf_lists_shares_with_attribution(village, owner, other, child):
    recipe = make_recipe(owner)
    entry = share(owner, village, recipe["id"])
    assert entry["family_name"] == "Home"
    assert entry["is_own"] is True

    # Everyone in both families can browse; the sharer's entry reads is_own
    # only at home.
    for client, own in ((owner, True), (child, True), (other, False)):
        shelf = client.get("/villages/shelf").json()
        assert len(shelf) == 1
        assert shelf[0]["name"] == "Pancakes"
        assert shelf[0]["is_own"] is own
        assert "recipe_id" not in shelf[0] and "id" not in shelf[0]


def test_shared_detail_carries_no_handles(village, owner, other):
    recipe = make_recipe(owner, custom=True)
    entry = share(owner, village, recipe["id"])
    detail = other.get(f"/villages/shelf/{entry['share_id']}").json()
    assert detail["steps"] == "Mix. Cook."
    assert len(detail["ingredients"]) == 2
    for line in detail["ingredients"]:
        assert "food_id" not in line and "source_id" not in line and "id" not in line


def test_share_needs_your_own_recipe_and_membership(village, owner, other, child):
    theirs = make_recipe(other, name="Their stew")
    # Sharing someone else's recipe id 404s like it doesn't exist.
    assert owner.post(f"/villages/{village}/recipes", json={"recipe_id": theirs["id"]}).status_code == 404
    mine = make_recipe(owner)
    assert child.post(f"/villages/{village}/recipes", json={"recipe_id": mine["id"]}).status_code == 403
    entry = share(owner, village, mine["id"])
    assert owner.post(f"/villages/{village}/recipes", json={"recipe_id": mine["id"]}).status_code == 400
    # Only the sharing family may unshare.
    assert other.delete(f"/villages/shelf/{entry['share_id']}").status_code == 404
    assert owner.delete(f"/villages/shelf/{entry['share_id']}").status_code == 204


def test_save_a_copy_is_an_independent_snapshot(village, owner, other):
    recipe = make_recipe(owner, custom=True)
    entry = share(owner, village, recipe["id"])
    copy = other.post(f"/villages/shelf/{entry['share_id']}/copy").json()
    assert copy["name"] == "Pancakes"
    assert {l["name"] for l in copy["ingredients"]} == {"Flour", "Grandma's mix"}

    # The sharer's later edits and unshares never reach the copy.
    owner.patch(f"/recipes/{recipe['id']}", json={"name": "Renamed"})
    owner.delete(f"/villages/shelf/{entry['share_id']}")
    mine = other.get("/recipes").json()
    assert any(r["name"] == "Pancakes" for r in mine)

    # A second copy of a re-shared identical recipe dedupes the custom food
    # and suffixes the recipe name instead of failing.
    entry2 = share(owner, village, recipe["id"])
    copy2 = other.post(f"/villages/shelf/{entry2['share_id']}/copy").json()
    assert copy2["name"] == "Renamed"
    foods = other.get("/foods").json()
    assert sum(1 for f in foods if f["name"] == "Grandma's mix") == 1


def test_copy_name_collision_suffixes(village, owner, other):
    recipe = make_recipe(owner, name="Stew")
    make_recipe(other, name="Stew")  # the destination already has one
    entry = share(owner, village, recipe["id"])
    copy = other.post(f"/villages/shelf/{entry['share_id']}/copy").json()
    assert copy["name"] == "Stew (2)"


def test_shelf_is_village_scoped(owner, other):
    # No shared village: the shelf is empty and a foreign share id 404s.
    recipe = make_recipe(owner)
    created = _create(owner)
    entry = share(owner, created["id"], recipe["id"])
    assert other.get("/villages/shelf").json() == []
    assert other.get(f"/villages/shelf/{entry['share_id']}").status_code == 404
    assert other.post(f"/villages/shelf/{entry['share_id']}/copy").status_code == 404


# ---- presence: opt-in mood/status on the village card -----------------------------


def test_presence_is_opt_in_and_hidden_stays_hidden(village, owner, other):
    from tests.conftest import user_id

    today = dt.date.today().isoformat()
    owner.put("/me/mood", json={"date_for": today, "level": "sunny", "hidden": False})
    owner.patch("/me/profile", json={"bio": "Baking day"})

    def owner_row(client):
        listed = client.get("/villages").json()[0]
        home = next(f for f in listed["families"] if f["name"] == "Home")
        return next(p for p in home["parents"] if p["id"] == user_id(owner))

    # Not opted in: nothing crosses, even with a visible mood set.
    row = owner_row(other)
    assert row["mood"] is None and row["status"] == ""

    assert owner.patch("/me/profile", json={"village_presence": True}).status_code == 200
    row = owner_row(other)
    assert row["mood"] == {"level": "sunny", "hidden": True} or row["mood"] == {
        "level": "sunny",
        "hidden": False,
    }
    assert row["status"] == "Baking day"

    # A hidden mood reads exactly like no mood, opt-in or not.
    owner.put("/me/mood", json={"date_for": today, "level": "stormy", "hidden": True})
    row = owner_row(other)
    assert row["mood"] is None
    assert row["status"] == "Baking day"


def test_presence_flag_round_trips(owner):
    assert owner.get("/auth/me").json()["village_presence"] is False
    owner.patch("/me/profile", json={"village_presence": True})
    assert owner.get("/auth/me").json()["village_presence"] is True
    owner.patch("/me/profile", json={"village_presence": False})
    assert owner.get("/auth/me").json()["village_presence"] is False
