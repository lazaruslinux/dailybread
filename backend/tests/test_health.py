"""Health profiles, the weight log, and auto calorie targets.

The profile (birthdate, sex, height, activity) plus the latest weigh-in feed
a computed daily calorie target: BMR (Katch-McArdle when body fat is known,
Mifflin-St Jeor otherwise) times an activity factor, shifted 500 kcal/day per
lb/week of goal rate, floored at a safe minimum. Health data is as private as
the diary, with one deliberate exception: parents manage a child's goal (and
can see that child's health section); children cannot set their own goals.
"""

import datetime as dt

from tests.conftest import user_id

TODAY = dt.date.today().isoformat()

# A 40-year-old male, 180 cm, moderately active. Mifflin-St Jeor at 90 kg:
# 10*90 + 6.25*180 - 5*40 + 5 = 1830; TDEE = 1830 * 1.5 = 2745 (moderate
# baseline is x1.5, matching Cronometer).
PROFILE = {
    "birthdate": (dt.date.today() - dt.timedelta(days=365 * 40 + 10)).isoformat(),
    "sex": "male",
    "height_cm": 180.0,
    "activity_level": "moderate",
}


def setup_profile(client, weight_kg=90.0, **overrides):
    res = client.put("/me/health/profile", json={**PROFILE, **overrides})
    assert res.status_code == 200, res.text
    res = client.put("/me/health/weight", json={"date_for": TODAY, "weight_kg": weight_kg})
    assert res.status_code == 200, res.text


# ---- profile and weigh-ins -------------------------------------------------------


def test_profile_and_weight_round_trip(owner):
    setup_profile(owner, weight_kg=90.0)
    h = owner.get("/me/health").json()
    assert h["profile"]["sex"] == "male"
    assert h["latest_weight"]["weight_kg"] == 90.0
    assert h["computed"]["bmr"] == 1830.0
    assert h["computed"]["tdee"] == 2745.0


def test_weigh_in_upserts_by_day(owner):
    setup_profile(owner, weight_kg=90.0)
    owner.put("/me/health/weight", json={"date_for": TODAY, "weight_kg": 89.5})
    h = owner.get("/me/health").json()
    assert h["latest_weight"]["weight_kg"] == 89.5
    assert len(h["weights"]) == 1


def test_body_fat_switches_bmr_to_katch_mcardle(owner):
    setup_profile(owner, weight_kg=90.0)
    # 20% body fat -> 72 kg lean mass -> 370 + 21.6*72 = 1925.2.
    owner.put(
        "/me/health/weight",
        json={"date_for": TODAY, "weight_kg": 90.0, "body_fat_pct": 20.0},
    )
    h = owner.get("/me/health").json()
    assert h["computed"]["bmr"] == 1925.2


def test_incomplete_profile_computes_nothing(owner):
    res = owner.put("/me/health/profile", json={"sex": "male", "height_cm": 180.0})
    assert res.status_code == 200
    h = owner.get("/me/health").json()
    assert h["computed"] is None  # no birthdate, no weigh-in yet


# ---- goals and the auto calorie target ---------------------------------------------


def test_lose_goal_shifts_the_target(owner):
    setup_profile(owner, weight_kg=90.0)
    res = owner.put(
        "/me/health/goal",
        json={"goal": "lose", "rate_lbs_per_week": 1.0, "goal_weight_kg": 80.0},
    )
    assert res.status_code == 200, res.text
    h = owner.get("/me/health").json()
    # 2745 - 500 = 2245, rounded to the nearest 10 (banker's: 2240).
    assert h["computed"]["auto_calories"] == 2240


def test_maintain_goal_targets_tdee(owner):
    setup_profile(owner, weight_kg=90.0)
    owner.put("/me/health/goal", json={"goal": "maintain"})
    assert owner.get("/me/health").json()["computed"]["auto_calories"] == 2740


def test_target_never_drops_below_the_floor(owner):
    # Small, light, sedentary person asking for an aggressive cut.
    setup_profile(
        owner,
        weight_kg=50.0,
        sex="female",
        height_cm=155.0,
        activity_level="sedentary",
    )
    owner.put("/me/health/goal", json={"goal": "lose", "rate_lbs_per_week": 2.0})
    h = owner.get("/me/health").json()
    assert h["computed"]["auto_calories"] == 1200  # female floor


def test_reaching_goal_weight_flips_to_maintenance(owner):
    setup_profile(owner, weight_kg=80.0)
    owner.put(
        "/me/health/goal",
        json={"goal": "lose", "rate_lbs_per_week": 1.0, "goal_weight_kg": 80.0},
    )
    h = owner.get("/me/health").json()
    assert h["computed"]["at_goal"] is True
    # No deficit once the goal weight is reached: maintain instead.
    assert h["computed"]["auto_calories"] == h["computed"]["maintenance_calories"]


def test_rate_is_capped_to_a_healthy_range(owner):
    setup_profile(owner)
    res = owner.put("/me/health/goal", json={"goal": "lose", "rate_lbs_per_week": 5.0})
    assert res.status_code == 422


def test_goal_body_fat_round_trips_without_touching_the_math(owner):
    setup_profile(owner, weight_kg=90.0)
    base = owner.get("/me/health").json()["computed"]["auto_calories"]
    res = owner.put(
        "/me/health/goal",
        json={
            "goal": "lose",
            "rate_lbs_per_week": 1.0,
            "goal_weight_kg": 80.0,
            "goal_body_fat_pct": 15.0,
        },
    )
    assert res.status_code == 200, res.text
    h = owner.get("/me/health").json()
    assert h["profile"]["goal_body_fat_pct"] == 15.0
    # Informational only: the calorie target is the same as without it.
    assert h["computed"]["auto_calories"] == base - 500

    # And it clears like the other goal fields do.
    owner.put("/me/health/goal", json={"goal": "maintain"})
    assert owner.get("/me/health").json()["profile"]["goal_body_fat_pct"] is None


# ---- diary targets integration ------------------------------------------------------


def test_auto_mode_feeds_the_diary_targets(owner):
    setup_profile(owner, weight_kg=90.0)
    owner.put("/me/health/goal", json={"goal": "lose", "rate_lbs_per_week": 1.0})
    res = owner.put("/diary/targets", json={
        "calories": 2000, "protein_pct": 40, "carbs_pct": 30, "fat_pct": 30,
        "mode": "auto",
    })
    assert res.status_code == 200, res.text
    t = owner.get(f"/diary?date={TODAY}").json()["targets"]
    assert t["mode"] == "auto"
    assert t["calories"] == 2240  # computed, not the manual 2000
    # The macro split stays the member's own, applied to the auto budget.
    assert t["protein_g"] == round(2240 * 0.4 / 4, 1)


def test_auto_mode_needs_a_complete_profile(owner):
    res = owner.put("/diary/targets", json={
        "calories": 2000, "protein_pct": 30, "carbs_pct": 40, "fat_pct": 30,
        "mode": "auto",
    })
    assert res.status_code == 400


def test_manual_mode_ignores_the_profile(owner):
    setup_profile(owner, weight_kg=90.0)
    owner.put("/me/health/goal", json={"goal": "lose", "rate_lbs_per_week": 1.0})
    owner.put("/diary/targets", json={
        "calories": 2500, "protein_pct": 30, "carbs_pct": 40, "fat_pct": 30,
    })
    t = owner.get(f"/diary?date={TODAY}").json()["targets"]
    assert t["mode"] == "manual"
    assert t["calories"] == 2500


# ---- privacy and the parent-managed exception --------------------------------------


def test_health_data_is_self_only_between_adults(owner, parent):
    setup_profile(parent, weight_kg=70.0)
    # Another parent's health section is nobody's business, admin or not.
    res = owner.get(f"/members/{user_id(parent)}/health")
    assert res.status_code == 404


def test_children_cannot_set_their_own_goal(child):
    setup_profile(child, weight_kg=45.0)
    res = child.put("/me/health/goal", json={"goal": "lose", "rate_lbs_per_week": 1.0})
    assert res.status_code == 403


def test_a_parent_manages_a_childs_goal(owner, child):
    setup_profile(child, weight_kg=45.0)
    kid = user_id(child)
    # The parent can see the child's health section and set the goal.
    assert owner.get(f"/members/{kid}/health").status_code == 200
    res = owner.put(f"/members/{kid}/health/goal", json={"goal": "maintain"})
    assert res.status_code == 200, res.text
    assert child.get("/me/health").json()["profile"]["goal"] == "maintain"


def test_cross_family_child_is_invisible(other, child):
    setup_profile(child, weight_kg=45.0)
    kid = user_id(child)
    assert other.get(f"/members/{kid}/health").status_code == 404
    assert other.put(f"/members/{kid}/health/goal", json={"goal": "maintain"}).status_code == 404
