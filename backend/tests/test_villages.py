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


def test_adults_list_but_minors_never_see_the_roster(child, owner, parent):
    """The roster carries other households' names, moods, and levels, so a
    kid never gets it. Their cross-family window is the recipe shelf only
    (test_shelf_shows_other_families_only covers the kid read there)."""
    _create(owner)
    assert parent.get("/villages").status_code == 200
    assert len(owner.get("/villages").json()) == 1
    assert child.get("/villages").status_code == 403


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


def test_a_family_founds_once_but_joins_many(app, village, owner, other):
    # The founder can't create a second village...
    assert owner.post("/villages", json={"name": "Second Circle"}).status_code == 400
    # ...but a family that only JOINED may found its own, and belonging to
    # several villages is fine.
    created = other.post("/villages", json={"name": "Bs Own Circle"}).json()
    assert created["is_creator"] is True

    from tests.conftest import login

    third_head = {"username": "cathy", "display_name": "Cathy", "password": "cathy-pass-123"}
    res = owner.post("/auth/users", json={**third_head, "role": "parent", "new_household": True})
    assert res.status_code == 201
    cathy = login(app, third_head)
    assert cathy.post("/families", json={"name": "The Cs"}).status_code == 201
    fresh = other.post(f"/villages/{created['id']}/invite").json()
    assert cathy.post("/villages/join", json={"code": fresh["invite_code"]}).status_code == 200
    # cathy founded no village of her own; she may later
    assert len(other.get("/villages").json()) == 2  # Bread Circle + her own


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


def make_food(client, name="Grandma's mix", brand="", folder=None):
    """A family's own custom food: one 100 g serving, so the stored per-100
    nutrition equals what's entered."""
    body = {
        "name": name, "brand": brand, "base_unit": "g",
        "calories": 400.0, "protein_g": 8.0,
        "servings": [{"name": "1 serving", "grams": 100.0}],
    }
    if folder is not None:
        body["folder"] = folder
    res = client.post("/foods", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def share_food(client, village_id, food_id):
    res = client.post(f"/villages/{village_id}/foods", json={"food_id": food_id})
    assert res.status_code == 201, res.text
    return res.json()


def test_shelf_shows_other_families_only(village, owner, other, child):
    recipe = make_recipe(owner)
    entry = share(owner, village, recipe["id"])
    assert entry["family_name"] == "Home"

    # The sharer's family sees their own entry flagged is_own (the client
    # renders it in a read-only "Shared by you" area); the other family sees
    # the live entry with the recipe's freshness stamp.
    for client, own in ((owner, True), (child, True), (other, False)):
        shelf = client.get("/villages/shelf").json()
        assert len(shelf) == 1
        assert shelf[0]["name"] == "Pancakes"
        assert shelf[0]["is_own"] is own
        assert shelf[0]["updated_at"] is not None
        assert "recipe_id" not in shelf[0] and "id" not in shelf[0]

    # The owner's recipe payload carries the share handle + village name.
    mine = next(r for r in owner.get("/recipes").json() if r["id"] == recipe["id"])
    assert mine["shared_to"] == [
        {"share_id": entry["share_id"], "village_id": village, "village_name": "Bread Circle"}
    ]
    # And copying your own share is nonsense, refused plainly.
    assert owner.post(f"/villages/shelf/{entry['share_id']}/copy").status_code == 400


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
    assert {ing["name"] for ing in copy["ingredients"]} == {"Flour", "Grandma's mix"}

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


# ---- the food shelf ---------------------------------------------------------------


def test_food_shelf_shows_both_families_with_is_own(village, owner, other, child):
    a = make_food(owner, name="Orange chicken", brand="Panda")
    share_food(owner, village, a["id"])
    b = make_food(other, name="Chow mein", brand="Panda")
    share_food(other, village, b["id"])

    shelf = owner.get("/villages/food-shelf").json()
    assert len(shelf) == 2
    by_name = {r["name"]: r for r in shelf}
    assert by_name["Orange chicken"]["is_own"] is True
    assert by_name["Chow mein"]["is_own"] is False
    row = by_name["Orange chicken"]
    assert row["brand"] == "Panda" and row["base_unit"] == "g"
    assert row["calories"] == 400.0 and row["protein_g"] == 8.0
    assert row["serving"] == "1 serving"
    # No handles into the owning family's rows, and folder never crosses.
    assert "food_id" not in row and "id" not in row and "folder" not in row

    # Minors browse the shelf directly (no listVillages needed for them).
    assert len(child.get("/villages/food-shelf").json()) == 2


def test_food_share_gating(village, owner, other, child):
    mine = make_food(owner, name="Mine")
    theirs = make_food(other, name="Theirs")
    # Another family's food is not the sharer's to share.
    assert owner.post(
        f"/villages/{village}/foods", json={"food_id": theirs["id"]}
    ).status_code == 404
    # A cache (USDA) food is not a custom food.
    recipe = make_recipe(owner)
    cache_food_id = recipe["ingredients"][0]["food_id"]
    assert owner.post(
        f"/villages/{village}/foods", json={"food_id": cache_food_id}
    ).status_code == 404
    # A village this family doesn't belong to.
    outsider = other.post("/villages", json={"name": "Bs Own Circle"}).json()["id"]
    assert owner.post(
        f"/villages/{outsider}/foods", json={"food_id": mine["id"]}
    ).status_code == 404
    # Kids can't share.
    assert child.post(
        f"/villages/{village}/foods", json={"food_id": mine["id"]}
    ).status_code == 403
    # Duplicate.
    share_food(owner, village, mine["id"])
    assert owner.post(
        f"/villages/{village}/foods", json={"food_id": mine["id"]}
    ).status_code == 400


def test_food_detail_is_id_free(village, owner, other):
    food = make_food(owner, name="Detailed", folder="Secret")
    entry = share_food(owner, village, food["id"])
    detail = other.get(f"/villages/food-shelf/{entry['share_id']}").json()
    assert detail["name"] == "Detailed"
    assert "folder" not in detail and "id" not in detail
    assert "food_id" not in detail and "source_id" not in detail and "barcode" not in detail
    assert len(detail["servings"]) == 1
    for s in detail["servings"]:
        assert set(s.keys()) == {"name", "grams"}


def test_food_copy_is_independent(village, owner, other):
    food = make_food(owner, name="Orange chicken", folder="Panda Express")
    entry = share_food(owner, village, food["id"])
    copy = other.post(f"/villages/food-shelf/{entry['share_id']}/copy").json()
    assert copy["name"] == "Orange chicken"
    assert copy["source_id"] is None  # the sharer's barcode never crosses
    assert copy["folder"] == "Panda Express"  # folder rides onto the clone
    assert [s["name"] for s in copy["servings"]] == ["1 serving"]
    assert [s["grams"] for s in copy["servings"]] == [100.0]

    # A second copy dedupes to the same food id (idempotent).
    copy2 = other.post(f"/villages/food-shelf/{entry['share_id']}/copy").json()
    assert copy2["id"] == copy["id"]
    assert sum(1 for f in other.get("/foods").json() if f["name"] == "Orange chicken") == 1

    # Editing the copy never reaches the original.
    other.put(
        f"/foods/{copy['id']}",
        json={
            "name": "Orange chicken", "base_unit": "g", "calories": 5.0,
            "servings": [{"name": "1 serving", "grams": 100.0}],
        },
    )
    original = next(f for f in owner.get("/foods").json() if f["name"] == "Orange chicken")
    assert original["calories"] == 400.0

    # Copying your own share is nonsense, refused plainly.
    assert owner.post(f"/villages/food-shelf/{entry['share_id']}/copy").status_code == 400


def test_food_share_and_copy_notifications(village, owner, other):
    food = make_food(owner, name="Kung pao")
    entry = share_food(owner, village, food["id"])
    # Sharing writes an inbox line to the OTHER family's parents ("village"),
    # never to the sharer.
    assert any(
        r["kind"] == "village" and "Kung pao" in r["title"]
        for r in other.get("/me/inbox").json()
    )
    assert not any(
        r["kind"] == "village" and "Kung pao" in r["title"]
        for r in owner.get("/me/inbox").json()
    )
    # Copying writes an inbox line to the SHARER's parents ("recipe"), never to
    # the copier.
    other.post(f"/villages/food-shelf/{entry['share_id']}/copy")
    assert any(
        r["kind"] == "recipe" and "saved your food" in r["title"]
        for r in owner.get("/me/inbox").json()
    )
    assert not any(
        r["kind"] == "recipe" and "saved your food" in r["title"]
        for r in other.get("/me/inbox").json()
    )


def test_food_shelf_is_village_scoped(village, owner, other, app):
    from tests.conftest import login

    food = make_food(owner, name="Scoped")
    entry = share_food(owner, village, food["id"])
    # A third family in no shared village sees an empty shelf and 404s the ids.
    creds = {"username": "cfam", "display_name": "C Fam", "password": "cfam-pass-1"}
    owner.post("/auth/users", json={**creds, "role": "parent", "new_household": True})
    third = login(app, creds)
    third.post("/families", json={"name": "The Cs"})
    assert third.get("/villages/food-shelf").json() == []
    assert third.get(f"/villages/food-shelf/{entry['share_id']}").status_code == 404
    # Non-owner can't unshare; owner can, and a saved copy survives.
    other.post(f"/villages/food-shelf/{entry['share_id']}/copy")
    assert other.delete(f"/villages/food-shelf/{entry['share_id']}").status_code == 404
    assert owner.delete(f"/villages/food-shelf/{entry['share_id']}").status_code == 204
    assert any(f["name"] == "Scoped" for f in other.get("/foods").json())


def test_recipe_copy_carries_ingredient_folder(village, owner, other):
    food = make_food(owner, name="Panda sauce", folder="Panda Express")
    res = owner.post(
        "/recipes",
        json={
            "name": "Sauce bowl", "servings": 2, "steps": "Mix.",
            "ingredients": [
                {"food_id": food["id"], "source": "custom", "name": "Panda sauce",
                 "amount": 50, "unit": "g"}
            ],
        },
    )
    assert res.status_code == 201, res.text
    entry = share(owner, village, res.json()["id"])
    other.post(f"/villages/shelf/{entry['share_id']}/copy")
    copied = next(f for f in other.get("/foods").json() if f["name"] == "Panda sauce")
    assert copied["folder"] == "Panda Express"


def test_food_list_carries_shared_to(village, owner):
    shared = make_food(owner, name="Shared dish")
    make_food(owner, name="Plain dish")
    entry = share_food(owner, village, shared["id"])

    foods = {f["name"]: f for f in owner.get("/foods").json()}
    assert foods["Shared dish"]["shared_to"] == [
        {"share_id": entry["share_id"], "village_id": village, "village_name": "Bread Circle"}
    ]
    assert foods["Plain dish"]["shared_to"] == []

    # Edits keep the share handle; unsharing empties it.
    edited = owner.put(
        f"/foods/{shared['id']}",
        json={
            "name": "Shared dish", "base_unit": "g", "calories": 410.0,
            "servings": [{"name": "1 serving", "grams": 100.0}],
        },
    )
    assert edited.json()["shared_to"][0]["share_id"] == entry["share_id"]
    assert owner.delete(f"/villages/food-shelf/{entry['share_id']}").status_code == 204
    foods = {f["name"]: f for f in owner.get("/foods").json()}
    assert foods["Shared dish"]["shared_to"] == []


def test_leaving_takes_food_shares_off_the_shelf(village, owner, other):
    food = make_food(owner, name="Departing dish")
    share_food(owner, village, food["id"])
    assert len(other.get("/villages/food-shelf").json()) == 1
    # Leaving takes the family's food shares with it, like recipe shares.
    assert owner.delete(f"/villages/{village}/membership").status_code == 204
    assert other.get("/villages/food-shelf").json() == []


def test_deleting_shared_food_unshares_it(village, owner, other):
    food = make_food(owner, name="Ephemeral")
    share_food(owner, village, food["id"])
    assert len(other.get("/villages/food-shelf").json()) == 1
    # delete-orphan on Food.village_shares takes the shelf entry with it.
    assert owner.delete(f"/foods/{food['id']}").status_code == 204
    assert other.get("/villages/food-shelf").json() == []


def test_join_and_shelf_shares_are_inbox_only(owner, other, parent, configured, outbox):
    created = _create(owner)
    owner.put("/push/subscription", json={
        "endpoint": "https://push.example/owner-device",
        "keys": {"p256dh": "k", "auth": "a"},
    })
    assert other.post("/villages/join", json={"code": created["invite_code"]}).status_code == 200
    # The join is recorded, but nobody's phone buzzes (his policy: only event
    # invitations and changes to going events push).
    assert any(
        r["kind"] == "village" and "joined" in r["title"]
        for r in owner.get("/me/inbox").json()
    )
    assert outbox == []

    other.put("/push/subscription", json={
        "endpoint": "https://push.example/other-device",
        "keys": {"p256dh": "k", "auth": "a"},
    })
    recipe = make_recipe(owner)
    share(owner, created["id"], recipe["id"])
    food = make_food(owner, name="Quiet dish")
    share_food(owner, created["id"], food["id"])
    assert outbox == []
    rows = other.get("/me/inbox").json()
    assert any("shared a recipe" in r["title"] for r in rows)
    assert any("shared a food: Quiet dish" in r["title"] for r in rows)
    # The sharer's co-parent gets the own-family lines, inbox-only.
    prows = parent.get("/me/inbox").json()
    assert any(r["title"] == "Owner shared to Bread Circle: Quiet dish" for r in prows)
    assert any(r["title"] == "Owner shared to Bread Circle: Pancakes" for r in prows)


def test_undo_lines_reach_the_co_parent_only(village, owner, other, parent):
    # Unshare a food: the co-parent hears, the village hears NOTHING.
    food = make_food(owner, name="Retracted dish")
    entry = share_food(owner, village, food["id"])
    assert owner.delete(f"/villages/food-shelf/{entry['share_id']}").status_code == 204
    assert any(
        r["title"] == "Owner took off the shelf: Retracted dish"
        for r in parent.get("/me/inbox").json()
    )
    assert not any(
        "took off the shelf" in r["title"] for r in other.get("/me/inbox").json()
    )


def test_join_writes_the_co_parent_line(owner, other, parent):
    # B founds a village; A's admin joins; A's co-parent sees it in history.
    created = _create(other, name="B Lane")
    assert owner.post("/villages/join", json={"code": created["invite_code"]}).status_code == 200
    assert any(
        r["title"] == "Owner joined B Lane" and r["kind"] == "village"
        for r in parent.get("/me/inbox").json()
    )


# ---- presence: opt-in mood/status on the village card -----------------------------


def test_presence_is_opt_in_hidden_stays_hidden_and_status_stays_home(village, owner, other):
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
    assert row["mood"] is None

    assert owner.patch("/me/profile", json={"village_presence": True}).status_code == 200
    row = owner_row(other)
    assert row["mood"] == {"level": "sunny", "hidden": False}
    # Presence carries today's status line too (2026-07-11: the mini
    # profile shows it); it was set before opting in, and it shows now.
    assert row["status"] == "Baking day"
    assert row["presence"] is True

    # A hidden mood reads exactly like no mood, opt-in or not.
    owner.put("/me/mood", json={"date_for": today, "level": "stormy", "hidden": True})
    row = owner_row(other)
    assert row["mood"] is None


def test_presence_flag_round_trips(owner):
    assert owner.get("/auth/me").json()["village_presence"] is False
    owner.patch("/me/profile", json={"village_presence": True})
    assert owner.get("/auth/me").json()["village_presence"] is True
    owner.patch("/me/profile", json={"village_presence": False})
    assert owner.get("/auth/me").json()["village_presence"] is False


def test_shelf_attribution_names_the_sharer(village, owner, other):
    recipe = make_recipe(owner, name="Attributed stew")
    entry = share(owner, village, recipe["id"])
    assert entry["shared_by"] == "Owner"  # first name of "Owner Parent"
    listed = other.get("/villages/shelf").json()
    assert listed[0]["shared_by"] == "Owner" and listed[0]["family_name"] == "Home"


def test_copies_carry_their_provenance(village, owner, other):
    recipe = make_recipe(owner, name="Provenance pie")
    entry = share(owner, village, recipe["id"])
    copy = other.post(f"/villages/shelf/{entry['share_id']}/copy").json()
    assert copy["provenance"].startswith("Copy of Provenance pie shared by Owner from Home on ")
    # The original never carries one.
    mine = next(r for r in owner.get("/recipes").json() if r["id"] == recipe["id"])
    assert mine["provenance"] is None


# ---- server-admin management: rename and delete ---------------------------------
# Renaming a village is an INSTALL-WIDE power, so it's the server admin's alone
# (is_owner). Family admins, even the founding family's, keep exactly what they
# had. Deleting gains an owner path that reaches villages the owner never joined.


def test_owner_renames_the_village(village, owner, other):
    """The server admin renames a village they founded; the new name persists
    across a re-read for every member family."""
    res = owner.patch(f"/villages/{village}", json={"name": "Sourdough Circle"})
    assert res.status_code == 204, res.text
    assert owner.get("/villages").json()[0]["name"] == "Sourdough Circle"
    assert other.get("/villages").json()[0]["name"] == "Sourdough Circle"


def test_owner_renames_a_village_they_did_not_found(owner, other):
    """Family B founds a village the owner never joins; the server admin still
    renames it install-wide."""
    created = _create(other, name="B Lane")
    res = owner.patch(f"/villages/{created['id']}", json={"name": "B Boulevard"})
    assert res.status_code == 204, res.text
    assert other.get("/villages").json()[0]["name"] == "B Boulevard"


def test_rename_is_server_admin_only(village, owner, other, parent, child, app):
    """Founding-family admin, other-family admin, a plain parent, and a kid all
    get 403 — rename is owner-only, and the name never moves."""
    from tests.conftest import login

    # A second admin in the FOUNDING family (Home) who is NOT the server owner.
    creds = {"username": "hadmin", "display_name": "Home Admin", "password": "home-admin-1"}
    assert owner.post(
        "/auth/users", json={**creds, "role": "parent", "is_admin": True}
    ).status_code == 201
    home_admin = login(app, creds)

    for client in (home_admin, other, parent, child):
        assert client.patch(f"/villages/{village}", json={"name": "Nope"}).status_code == 403
    assert owner.get("/villages").json()[0]["name"] == "Bread Circle"


def test_rename_rejects_empty_and_overlong(village, owner):
    # A single space slips past min_length=1 but is empty after strip -> 400.
    assert owner.patch(f"/villages/{village}", json={"name": "   "}).status_code == 400
    # 81 characters trips the 80-char cap -> 422.
    assert owner.patch(f"/villages/{village}", json={"name": "x" * 81}).status_code == 422
    # An empty string fails min_length outright -> 422.
    assert owner.patch(f"/villages/{village}", json={"name": ""}).status_code == 422
    # None of that changed the name.
    assert owner.get("/villages").json()[0]["name"] == "Bread Circle"


def test_rename_unknown_village_404(owner):
    assert owner.patch("/villages/99999", json={"name": "Ghost"}).status_code == 404


def test_rename_notifies_member_families_inbox_only(
    village, owner, other, configured, outbox
):
    """The member families hear the rename in their inbox; the acting family
    hears nothing, and the phone stays silent even with push configured."""
    other.put(
        "/push/subscription",
        json={"endpoint": "https://push.example/b", "keys": {"p256dh": "k", "auth": "a"}},
    )
    res = owner.patch(f"/villages/{village}", json={"name": "New Circle"})
    assert res.status_code == 204, res.text
    assert any(
        r["kind"] == "village" and "renamed" in r["title"].lower()
        for r in other.get("/me/inbox").json()
    )
    assert not any(
        "renamed" in r["title"].lower() for r in owner.get("/me/inbox").json()
    )
    assert outbox == []  # inbox-only: no push, whatever the pref


def test_rename_to_the_same_name_is_a_quiet_noop(village, owner, other):
    res = owner.patch(f"/villages/{village}", json={"name": "Bread Circle"})
    assert res.status_code == 204, res.text
    assert not any(
        "renamed" in r["title"].lower() for r in other.get("/me/inbox").json()
    )


def test_owner_deletes_a_village_they_did_not_found(owner, other, app):
    """Family B founds a village a third family joins; the server admin, never
    a member, dissolves it and its memberships and shelf rows go with it."""
    from tests.conftest import login

    created = _create(other, name="B Lane")
    creds = {"username": "cfam", "display_name": "C Fam", "password": "cfam-pass-1"}
    owner.post("/auth/users", json={**creds, "role": "parent", "new_household": True})
    third = login(app, creds)
    third.post("/families", json={"name": "The Cs"})
    assert third.post(
        "/villages/join", json={"code": created["invite_code"]}
    ).status_code == 200
    recipe = make_recipe(other, name="B pie")
    share(other, created["id"], recipe["id"])

    assert owner.delete(f"/villages/{created['id']}").status_code == 204
    assert other.get("/villages").json() == []
    assert third.get("/villages").json() == []
    assert other.get("/villages/shelf").json() == []  # shelf rows cascaded away
    assert owner.get("/auth/overview").json()["villages"] == []


def test_founding_family_admin_still_deletes_its_own_village(other):
    """Regression: the non-owner founding path is unchanged."""
    created = _create(other, name="B Lane")
    assert other.delete(f"/villages/{created['id']}").status_code == 204


def test_non_owner_member_who_did_not_found_still_403s(village, other):
    """Regression: a member family that didn't found still can't delete."""
    assert other.delete(f"/villages/{village}").status_code == 403


def test_non_owner_non_member_delete_still_404s(owner, other):
    """Regression: a non-member non-owner still gets the uniform 404."""
    created = _create(owner)  # family B never joins
    assert other.delete(f"/villages/{created['id']}").status_code == 404
