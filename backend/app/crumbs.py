"""The breadcrumb economy: what earns, how much, and what a total means.

Everything routes through award(): one attempted INSERT whose unique
(user, source_key) makes every award idempotent — the same claim pattern the
push engine's DigestLog uses. Callers never check "did this already pay?";
they just ask, and the constraint answers.

The earn table (see docs and the plan): first activity of the day +1, all
three verses +3, one watch workout of 15+ minutes per day +3, each completed
card +1 (capped at COMPLETE_DAILY_CAP a day so junk-card farming is
pointless), and verse-streak milestones +5/+15/+50 at 7/30/100 days. Mood,
status, and journal deliberately earn nothing: honesty is never paid.
"""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CrumbLedger, User

LOGIN_CRUMBS = 1
VERSES_CRUMBS = 3
WORKOUT_CRUMBS = 3
COMPLETE_CRUMBS = 1
COMPLETE_DAILY_CAP = 10  # max crumbs/day from card completions
WORKOUT_MIN_SECONDS = 15 * 60

# Verse-streak milestones: hitting N days pays once, ever ("vstreak:<n>").
STREAK_MILESTONES = {7: 5, 30: 15, 100: 50}

# Crumbs to go from level L to L+1. Ramping: quick early levels, a long
# honest arc (level 10 ~ six weeks of real use, level 40 ~ a year and a half).
def level_cost(level: int) -> int:
    return 10 + 5 * (level - 1)


# The five tiers, by level band of 10. His names.
TIERS = ["slice", "roll", "loaf", "baker", "breadmaster"]


def tier_of(level: int) -> str:
    """Bands of ten: 1-9 slice, 10-19 roll, …, 40+ breadmaster."""
    return TIERS[min(max(level, 1) // 10, len(TIERS) - 1)]


def level_of(total: int) -> tuple[int, int, int]:
    """(level, crumbs into this level, cost of the next) for a crumb total."""
    level = 1
    remaining = max(total, 0)
    while remaining >= level_cost(level):
        remaining -= level_cost(level)
        level += 1
    return level, remaining, level_cost(level)


def award(
    db: Session,
    user: User,
    kind: str,
    amount: int,
    source_key: str,
    date_for: dt.date,
) -> int:
    """Pay a member once for a thing. Returns the amount actually awarded —
    0 when this source_key already paid (or the member has no family yet).
    Commits on success; the caller's own pending work should be committed
    first, since a lost race rolls the session back."""
    if user.family_id is None or amount == 0:
        return 0
    db.add(
        CrumbLedger(
            family_id=user.family_id,
            user_id=user.id,
            date_for=date_for,
            kind=kind,
            amount=amount,
            source_key=source_key,
        )
    )
    try:
        db.commit()
        return amount
    except IntegrityError:
        db.rollback()
        return 0


def award_completion(db: Session, user: User, item_id: int, date_for: dt.date) -> int:
    """A completed card, +1, respecting the daily cap for this source."""
    earned_today = db.scalar(
        select(func.coalesce(func.sum(CrumbLedger.amount), 0)).where(
            CrumbLedger.user_id == user.id,
            CrumbLedger.kind == "complete",
            CrumbLedger.date_for == date_for,
        )
    )
    if earned_today >= COMPLETE_DAILY_CAP:
        return 0
    return award(
        db, user, "complete", COMPLETE_CRUMBS, f"item:{item_id}:{date_for.isoformat()}", date_for
    )


def award_streak_milestones(db: Session, user: User, streak: int, date_for: dt.date) -> int:
    """Whatever milestones this streak value has reached and not yet paid."""
    total = 0
    for days, bonus in STREAK_MILESTONES.items():
        if streak >= days:
            total += award(db, user, "bonus", bonus, f"vstreak:{days}", date_for)
    return total


def total_for(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(CrumbLedger.amount), 0)).where(
            CrumbLedger.user_id == user_id
        )
    )


def totals_for(db: Session, user_ids: list[int]) -> dict[int, int]:
    """Every member's crumb total in one query, for strips and lists."""
    if not user_ids:
        return {}
    rows = db.execute(
        select(CrumbLedger.user_id, func.sum(CrumbLedger.amount))
        .where(CrumbLedger.user_id.in_(user_ids))
        .group_by(CrumbLedger.user_id)
    ).all()
    return {uid: int(total) for uid, total in rows}


def levels_for(db: Session, user_ids: list[int]) -> dict[int, int]:
    """Every member's level, defaulting to 1 for members with no earns yet."""
    totals = totals_for(db, user_ids)
    return {uid: level_of(totals.get(uid, 0))[0] for uid in user_ids}
