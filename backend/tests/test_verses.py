"""Verse check-offs and reading streaks: strictly opt-in. The streak lives
inside the verse card (and feeds crumbs + the at-risk push); what rides the
strip and the village wall now is the LEVEL, by its own opt-in."""

import datetime as dt

import pytest

from app import throttle

TODAY = dt.date.today().isoformat()
YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


@pytest.fixture(autouse=True)
def _clean_throttle():
    throttle.clear()
    yield
    throttle.clear()


def _enable(client):
    res = client.put("/me/verses/settings", json={"enabled": True})
    assert res.status_code == 200, res.text
    return res.json()


def _check(client, idx, date=TODAY):
    return client.post("/me/verses/check", json={"date_for": date, "verse_idx": idx})


def _me(client, date=TODAY):
    return client.get(f"/me/verses?date={date}").json()


def test_checks_require_the_opt_in(owner):
    assert _check(owner, 0).status_code == 400
    assert _me(owner) == {
        "enabled": False,
        "checks": [False, False, False],
        "streak": 0,
        "crumbs_awarded": 0,
    }


def test_checking_all_three_completes_the_day(owner):
    _enable(owner)
    for i in range(3):
        res = _check(owner, i)
        assert res.status_code == 200, res.text
    body = _me(owner)
    assert body["checks"] == [True, True, True]
    assert body["streak"] == 1


def test_checks_are_one_way(owner):
    # Unchecking a read verse was pointless (his words); the endpoint is gone
    # and the fold arrow is how the card gets out of the way.
    _enable(owner)
    for i in range(3):
        _check(owner, i)
    assert owner.delete(f"/me/verses/check?date={TODAY}&idx=1").status_code == 405
    assert _me(owner)["checks"] == [True, True, True]


def test_double_checking_is_idempotent(owner):
    _enable(owner)
    _check(owner, 0)
    assert _check(owner, 0).status_code == 200
    assert _me(owner)["checks"][0] is True


def test_an_unfinished_today_keeps_yesterdays_streak(owner):
    _enable(owner)
    for i in range(3):
        _check(owner, i, date=YESTERDAY)
    assert _me(owner)["streak"] == 1  # grace: today just hasn't happened yet
    for i in range(3):
        _check(owner, i)
    assert _me(owner)["streak"] == 2


def test_the_level_rides_the_family_strip(owner, parent):
    # The streak number stays inside the verse card; the strip carries the
    # LEVEL for everyone (a fresh account reads level 1, honestly).
    _enable(owner)
    for i in range(3):
        _check(owner, i)
    members = parent.get(f"/users?date={TODAY}").json()
    by_name = {m["username"]: m for m in members}
    assert by_name["owner"]["level"] == 1
    assert by_name["parent2"]["level"] == 1
    assert "verse_streak" not in by_name["owner"]


def test_two_checks_are_not_a_complete_day(owner):
    _enable(owner)
    _check(owner, 0)
    _check(owner, 1)
    assert _me(owner)["streak"] == 0


def test_village_level_needs_its_own_opt_in(owner, other):
    created = owner.post("/villages", json={"name": "Bread Circle"}).json()
    assert other.post("/villages/join", json={"code": created["invite_code"]}).status_code == 200
    vid = created["id"]

    _enable(owner)
    for i in range(3):
        _check(owner, i)  # +3 crumbs, still level 1

    def my_row():
        v = next(x for x in other.get("/villages").json() if x["id"] == vid)
        parents = [p for fam in v["families"] for p in fam["parents"]]
        return next(p for p in parents if p["display_name"] == "Owner Parent")

    assert my_row()["level"] is None  # not shared: invisible, not "1"
    assert my_row()["crumbs"] is None
    assert owner.patch("/me/profile", json={"share_level": True}).status_code == 200
    assert my_row()["level"] == 1
    assert my_row()["crumbs"] == 3


def test_a_phone_past_midnight_still_counts_today(owner):
    """The client's calendar can be a day ahead of the server's (the write
    guard allows the drift). Checks dated 'tomorrow' anchor the streak walk
    so the badge appears immediately, not after the server's midnight."""
    _enable(owner)
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    for i in range(3):
        assert _check(owner, i, date=tomorrow).status_code == 200
    assert _me(owner, date=tomorrow)["streak"] == 1
