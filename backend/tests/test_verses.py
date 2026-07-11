"""Verse check-offs and reading streaks: strictly opt-in, only the streak
number ever leaves the member — family always, villages by a second opt-in."""

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


def _enable(client, share=False):
    res = client.put("/me/verses/settings", json={"enabled": True, "share": share})
    assert res.status_code == 200, res.text
    return res.json()


def _check(client, idx, date=TODAY):
    return client.post("/me/verses/check", json={"date_for": date, "verse_idx": idx})


def _me(client, date=TODAY):
    return client.get(f"/me/verses?date={date}").json()


def test_checks_require_the_opt_in(owner):
    assert _check(owner, 0).status_code == 400
    assert _me(owner) == {"enabled": False, "share": False, "checks": [False, False, False], "streak": 0}


def test_checking_all_three_completes_the_day(owner):
    _enable(owner)
    for i in range(3):
        res = _check(owner, i)
        assert res.status_code == 200, res.text
    body = _me(owner)
    assert body["checks"] == [True, True, True]
    assert body["streak"] == 1


def test_unchecking_reopens_the_day(owner):
    _enable(owner)
    for i in range(3):
        _check(owner, i)
    res = owner.delete(f"/me/verses/check?date={TODAY}&idx=1")
    assert res.status_code == 200
    body = _me(owner)
    assert body["checks"] == [True, False, True]
    assert body["streak"] == 0


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


def test_the_streak_number_rides_the_family_strip(owner, parent):
    _enable(owner)
    for i in range(3):
        _check(owner, i)
    members = parent.get(f"/users?date={TODAY}").json()
    by_name = {m["username"]: m for m in members}
    assert by_name["owner"]["verse_streak"] == 1
    # A member who never opted in shows nothing at all.
    assert by_name["parent2"]["verse_streak"] is None


def test_two_checks_are_not_a_complete_day(owner):
    _enable(owner)
    _check(owner, 0)
    _check(owner, 1)
    assert _me(owner)["streak"] == 0


def test_village_streak_needs_its_own_opt_in(owner, other):
    created = owner.post("/villages", json={"name": "Bread Circle"}).json()
    assert other.post("/villages/join", json={"code": created["invite_code"]}).status_code == 200
    vid = created["id"]

    _enable(owner, share=False)
    for i in range(3):
        _check(owner, i)

    def my_row():
        v = next(x for x in other.get("/villages").json() if x["id"] == vid)
        parents = [p for fam in v["families"] for p in fam["parents"]]
        return next(p for p in parents if p["display_name"] == "Owner Parent")

    assert my_row()["verse_streak"] is None
    owner.put("/me/verses/settings", json={"share": True})
    assert my_row()["verse_streak"] == 1
