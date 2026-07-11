"""The breadcrumb economy: every earn pays once, caps hold, the math is
honest. Totals are asserted as deltas — logging in itself earns the daily +1,
so absolute numbers would couple every test to fixture setup order."""

import datetime as dt

import pytest

from app.crumbs import TIERS, level_of, tier_of
from app.models import VerseCheck
from tests.conftest import user_id

TODAY = dt.date.today()


def crumbs_total(client) -> int:
    res = client.get("/me/crumbs")
    assert res.status_code == 200, res.text
    return res.json()["total"]


# ---- the math -------------------------------------------------------------------


def test_level_math_boundaries():
    assert level_of(0) == (1, 0, 10)
    assert level_of(9) == (1, 9, 10)
    assert level_of(10) == (2, 0, 15)
    assert level_of(24) == (2, 14, 15)
    assert level_of(25) == (3, 0, 20)


def test_tiers_change_every_ten_levels():
    assert tier_of(1) == "slice"
    assert tier_of(9) == "slice"
    assert tier_of(10) == "roll"
    assert tier_of(20) == "loaf"
    assert tier_of(30) == "baker"
    assert tier_of(40) == "breadmaster"
    assert tier_of(99) == "breadmaster"  # the ladder tops out, honestly
    assert TIERS == ["slice", "roll", "loaf", "baker", "breadmaster"]


# ---- showing up -----------------------------------------------------------------


def test_showing_up_pays_once_a_day(owner):
    owner.get("/auth/me")
    owner.get("/auth/me")  # the second open of the day is not a second coin
    body = owner.get("/me/crumbs").json()
    assert body["total"] == 1
    assert body["today"] == 1
    assert body["login_award_today"] is True
    assert body["level"] == 1
    assert body["tier"] == "slice"


# ---- verses ---------------------------------------------------------------------


def _enable_verses(client):
    assert client.put("/me/verses/settings", json={"enabled": True}).status_code == 200


def _check(client, idx, date=TODAY.isoformat()):
    res = client.post("/me/verses/check", json={"date_for": date, "verse_idx": idx})
    assert res.status_code == 200, res.text
    return res.json()


def test_the_third_verse_pays_three_once(owner):
    _enable_verses(owner)
    before = crumbs_total(owner)
    assert _check(owner, 0)["crumbs_awarded"] == 0
    assert _check(owner, 1)["crumbs_awarded"] == 0
    assert _check(owner, 2)["crumbs_awarded"] == 3
    assert _check(owner, 2)["crumbs_awarded"] == 0  # re-tap: nothing
    assert crumbs_total(owner) == before + 3


def test_streak_milestones_pay_a_bonus_once(owner, engine_db):
    _enable_verses(owner)
    with engine_db() as db:
        for back in range(1, 7):  # six complete days behind today
            for idx in range(3):
                db.add(
                    VerseCheck(
                        user_id=user_id(owner),
                        date_for=TODAY - dt.timedelta(days=back),
                        verse_idx=idx,
                    )
                )
        db.commit()
    _check(owner, 0)
    _check(owner, 1)
    body = _check(owner, 2)  # day 7: the +3 and the 7-day +5 land together
    assert body["streak"] == 7
    assert body["crumbs_awarded"] == 8


# ---- workouts -------------------------------------------------------------------


def _payload(duration_s: int, day: dt.date = TODAY) -> dict:
    stamp = lambda hhmmss: f"{day.isoformat()} {hhmmss} -0700"
    return {
        "data": {
            "workouts": [
                {
                    "id": f"wk-{day.isoformat()}-{duration_s}",
                    "name": "Outdoor Run",
                    "start": stamp("06:30:00"),
                    "end": stamp("07:05:00"),
                    "duration": duration_s,
                }
            ]
        }
    }


def _mint(client) -> str:
    return client.post("/me/fitness/token").json()["token"]


def _send(client, token, payload):
    res = client.post(
        "/ingest/health", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text


def test_a_real_workout_pays_three_once_a_day(owner):
    token = _mint(owner)
    before = crumbs_total(owner)
    _send(owner, token, _payload(2100))  # 35 minutes
    assert crumbs_total(owner) == before + 3
    _send(owner, token, _payload(2100))  # the re-sync pays nothing
    assert crumbs_total(owner) == before + 3
    _send(owner, token, _payload(2400))  # a SECOND long workout today: still nothing
    assert crumbs_total(owner) == before + 3


def test_short_workouts_do_not_pay(owner):
    token = _mint(owner)
    before = crumbs_total(owner)
    _send(owner, token, _payload(600))  # ten minutes is a warm-up, not a coin
    assert crumbs_total(owner) == before


# ---- completions ----------------------------------------------------------------


def _make(client, **overrides):
    payload = {"kind": "task", "title": "Card", **overrides}
    res = client.post("/items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_completing_a_card_pays_one_and_only_once(owner):
    item = _make(owner, date_for=TODAY.isoformat())
    before = crumbs_total(owner)
    res = owner.post(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    assert res.json()["crumbs_awarded"] == 1
    # Uncheck and recheck: the ledger key remembers.
    owner.delete(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    res = owner.post(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    assert res.json()["crumbs_awarded"] == 0
    assert crumbs_total(owner) == before + 1


def test_completions_cap_at_ten_a_day(owner):
    items = [_make(owner, title=f"Chore {i}") for i in range(12)]
    awarded = sum(
        owner.post(f"/items/{item['id']}/complete?date={TODAY.isoformat()}").json()[
            "crumbs_awarded"
        ]
        for item in items
    )
    assert awarded == 10  # junk-card farming hits the wall


def test_a_kids_crumb_lands_on_approval(owner, child):
    kid_id = user_id(child)
    item = _make(
        owner,
        kind="routine",
        title="Brush teeth",
        assignee_ids=[kid_id],
        repeat={"type": "weekly", "days": [0, 1, 2, 3, 4, 5, 6]},
    )
    kid_before = crumbs_total(child)
    # The kid's own tap goes pending: no coin yet.
    res = child.post(f"/items/{item['id']}/complete?date={TODAY.isoformat()}")
    assert res.json()["crumbs_awarded"] == 0
    assert crumbs_total(child) == kid_before
    # A parent makes it official: the KID earns, not the parent.
    parent_before = crumbs_total(owner)
    res = owner.post(
        f"/items/{item['id']}/complete?date={TODAY.isoformat()}&for={kid_id}"
    )
    assert res.json()["crumbs_awarded"] == 1
    assert crumbs_total(child) == kid_before + 1
    assert crumbs_total(owner) == parent_before


# ---- what others see ------------------------------------------------------------


def test_the_profile_carries_the_economy_panel(owner):
    owner.get("/auth/me")  # ensure at least the day's +1 exists
    me = owner.get("/auth/me").json()
    profile = owner.get(f"/users/{me['id']}/profile?date={TODAY.isoformat()}").json()
    assert profile["level"] == 1
    assert profile["tier"] == "slice"
    assert profile["crumbs"] >= 1
    assert profile["next_level_cost"] == 10
    assert profile["level_progress"] == profile["crumbs"]
