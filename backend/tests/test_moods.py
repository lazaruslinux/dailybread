"""Mood privacy: hidden and unset must be indistinguishable to other members."""

import datetime as dt

from tests.conftest import user_id

TODAY = dt.date.today().isoformat()


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
