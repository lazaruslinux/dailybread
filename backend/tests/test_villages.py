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
    # No avatar handle rides along: bubbles are initials-only across families.
    assert "avatar_updated_at" not in by_family["Home"]["parents"][0]
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
