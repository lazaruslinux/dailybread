"""The health math: BMR, daily burn, and the auto calorie target.

Estimation formulas, not medical advice (the UI says as much). Everything
here is a pure function of a profile and the latest weigh-in, so the diary
and the health endpoints can never disagree about the numbers.
"""

import datetime as dt

from app.models import ActivityLevel, GoalType, HealthProfile, Sex, WeightEntry

# Standard multipliers over resting burn for overall daily activity.
ACTIVITY_FACTORS: dict[ActivityLevel, float] = {
    ActivityLevel.sedentary: 1.2,
    ActivityLevel.light: 1.375,
    ActivityLevel.moderate: 1.55,
    ActivityLevel.active: 1.725,
    ActivityLevel.very_active: 1.9,
}

# One pound of body fat is roughly 3500 kcal, so each lb/week of goal rate
# shifts the daily budget by 500.
KCAL_PER_LB_PER_WEEK = 500.0

# Safe daily minimums: an aggressive rate never pushes the target below these
# (the widely used clinical floor for unsupervised dieting).
FLOOR = {Sex.female: 1200, Sex.male: 1500}


def _age_years(birthdate: dt.date) -> int:
    today = dt.date.today()
    return today.year - birthdate.year - (
        (today.month, today.day) < (birthdate.month, birthdate.day)
    )


def _round10(v: float) -> int:
    return int(round(v / 10.0) * 10)


def compute(profile: HealthProfile | None, latest: WeightEntry | None) -> dict | None:
    """The computed panel: BMR, daily burn, and the goal-adjusted calorie
    target. None until the profile is complete enough to be honest about it
    (birthdate, sex, height, activity, and at least one weigh-in)."""
    if (
        profile is None
        or latest is None
        or profile.birthdate is None
        or profile.sex is None
        or profile.height_cm is None
        or profile.activity_level is None
    ):
        return None

    kg = latest.weight_kg
    if latest.body_fat_pct is not None:
        # Katch-McArdle: resting burn from lean mass. More accurate when body
        # fat is known - the reason the profile asks for it at all.
        lean = kg * (1 - latest.body_fat_pct / 100.0)
        bmr = 370 + 21.6 * lean
    else:
        # Mifflin-St Jeor from weight, height, age, and sex.
        age = _age_years(profile.birthdate)
        bmr = 10 * kg + 6.25 * profile.height_cm - 5 * age
        bmr += 5 if profile.sex == Sex.male else -161

    tdee = bmr * ACTIVITY_FACTORS[profile.activity_level]
    maintenance = _round10(tdee)

    # Reaching the goal weight flips the plan to maintenance automatically;
    # nobody should keep a deficit running past their own finish line.
    goal = profile.goal or GoalType.maintain
    at_goal = False
    if profile.goal_weight_kg is not None:
        if goal == GoalType.lose and kg <= profile.goal_weight_kg:
            at_goal = True
        elif goal == GoalType.gain and kg >= profile.goal_weight_kg:
            at_goal = True
    effective = GoalType.maintain if at_goal else goal

    rate = profile.rate_lbs_per_week or 0.0
    shift = rate * KCAL_PER_LB_PER_WEEK
    if effective == GoalType.lose:
        target = tdee - shift
    elif effective == GoalType.gain:
        target = tdee + shift
    else:
        target = tdee

    auto = max(_round10(target), FLOOR[profile.sex])

    return {
        "bmr": round(bmr, 1),
        "tdee": round(tdee, 1),
        "maintenance_calories": maintenance,
        "auto_calories": auto,
        "at_goal": at_goal,
    }


def computed_for(db, user_id: int) -> dict | None:
    """compute() over a member's stored profile and latest weigh-in. The
    diary's auto target mode reads this, so targets and the health panel
    always agree."""
    from sqlalchemy import select

    profile = db.get(HealthProfile, user_id)
    latest = db.scalar(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id)
        .order_by(WeightEntry.date_for.desc())
        .limit(1)
    )
    return compute(profile, latest)
