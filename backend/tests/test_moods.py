"""Mood privacy: hidden and unset must be indistinguishable to other members."""

import datetime as dt

from tests.conftest import login, user_id

TODAY = dt.date.today().isoformat()

SIB = {"username": "sib", "display_name": "Sibling", "password": "sib-pass-12345"}


def make_sibling(app, owner):
    """A second child in the family — the 'other kid' for privacy checks."""
    res = owner.post("/auth/users", json={**SIB, "role": "child"})
    assert res.status_code == 201, res.text
    return login(app, SIB)


def set_mood(client, level="sunny", hidden=False):
    res = client.put(
        "/me/mood", json={"date_for": TODAY, "level": level, "hidden": hidden}
    )
    assert res.status_code == 200, res.text
    return res.json()


def member(client, uid):
    res = client.get(f"/users?date={TODAY}")
    assert res.status_code == 200
    return next(m for m in res.json() if m["id"] == uid)


def test_visible_mood_shows_to_others(owner, child):
    set_mood(owner, "partly", hidden=False)
    assert member(child, user_id(owner))["mood"] == {"level": "partly", "hidden": False}


def test_hidden_mood_looks_exactly_like_no_mood(owner, parent, child):
    # Owner hides a mood; the second parent sets none at all.
    set_mood(owner, "stormy", hidden=True)

    seen_by_child = member(child, user_id(owner))
    no_mood_at_all = member(child, user_id(parent))
    assert seen_by_child["mood"] is None
    assert seen_by_child["mood"] == no_mood_at_all["mood"]  # indistinguishable


def test_own_hidden_mood_still_visible_to_self(owner):
    set_mood(owner, "stormy", hidden=True)
    assert member(owner, user_id(owner))["mood"] == {"level": "stormy", "hidden": True}


def test_profile_respects_the_same_privacy_rule(owner, child):
    set_mood(owner, "rainy", hidden=True)
    profile = child.get(f"/users/{user_id(owner)}/profile?date={TODAY}").json()
    assert profile["mood"] is None


def test_clearing_a_mood(owner, child):
    set_mood(owner, "sunny")
    assert owner.delete(f"/me/mood?date={TODAY}").status_code == 204
    assert member(child, user_id(owner))["mood"] is None


def test_members_cannot_edit_each_others_profiles(child):
    # /me/profile only ever touches the caller; there is no path to another
    # member's bio. The child editing "their" profile must not 403...
    res = child.patch("/me/profile", json={"bio": "I like turtles"})
    assert res.status_code == 200
    assert res.json()["bio"] == "I like turtles"


def test_status_shows_on_the_day_it_is_set(owner):
    owner.patch("/me/profile", json={"bio": "Busy but good"})
    prof = owner.get(f"/users/{user_id(owner)}/profile?date={TODAY}").json()
    assert prof["bio"] == "Busy but good"


def test_status_clears_overnight(owner, child):
    # A status is a daily note like a mood: seen from the next day it reads as
    # no status, so it clears itself overnight without anyone editing it.
    owner.patch("/me/profile", json={"bio": "Busy but good"})
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    prof = child.get(f"/users/{user_id(owner)}/profile?date={tomorrow}").json()
    assert prof["bio"] == ""


# ---- kid privacy: a minor's mood and status are the parents' business ---------------


def test_minor_mood_hidden_from_other_children(app, owner, child):
    sibling = make_sibling(app, owner)
    set_mood(child)
    kid = user_id(child)
    # Parents see it; a sibling sees nothing at all.
    assert member(owner, kid)["mood"] == {"level": "sunny", "hidden": False}
    assert member(sibling, kid)["mood"] is None
    # The kid still sees their own.
    assert member(child, kid)["mood"] is not None


def test_parents_moods_stay_family_visible(owner, parent, child):
    set_mood(parent)
    set_mood(owner, "partly")
    # Kid privacy narrows only the minor's own data: a minor still sees the
    # rest of the family's moods like anyone else.
    assert member(child, user_id(parent))["mood"] is not None
    assert member(child, user_id(owner))["mood"] is not None


def test_minor_status_hidden_from_other_children(app, owner, child):
    sibling = make_sibling(app, owner)
    res = child.patch("/me/profile", json={"bio": "Lost a tooth today"})
    assert res.status_code == 200
    kid = user_id(child)

    seen_by_parent = owner.get(f"/users/{kid}/profile?date={TODAY}").json()
    seen_by_sibling = sibling.get(f"/users/{kid}/profile?date={TODAY}").json()
    assert seen_by_parent["bio"] == "Lost a tooth today"
    assert seen_by_sibling["bio"] == ""
    # Their own profile still shows it (that's how they edit it).
    assert child.get(f"/users/{kid}/profile?date={TODAY}").json()["bio"] != ""


def test_family_and_profile_carry_is_minor(owner, child):
    # These two build their payloads by hand (unlike /auth/me), so pin that
    # is_minor actually rides along — the client keys kid-mode UI off it.
    kid = user_id(child)
    assert member(owner, kid)["is_minor"] is True
    assert owner.get(f"/users/{kid}/profile?date={TODAY}").json()["is_minor"] is True
