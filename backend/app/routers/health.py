import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_family, require_parent
from app.health import compute
from app.models import HealthProfile, Role, User, WeightEntry
from app.schemas import GoalIn, HealthOut, HealthProfileIn, WeightIn, WeightOut

# No prefix: self endpoints live under /me/health (the app's convention for
# personal data), and the parent-managed view under /members/{id}/health.
router = APIRouter(tags=["health"])

# Health data is as private as the diary, with ONE deliberate exception:
# a parent can see a CHILD's health section and set the child's goal.
# Children never set their own goals - a calorie plan for a kid is a
# parent-and-pediatrician decision, not a settings toggle. Between adults
# there is no exception: another parent's section 404s even for an admin.


def _profile(db: Session, user_id: int, create: bool = False) -> HealthProfile | None:
    profile = db.get(HealthProfile, user_id)
    if profile is None and create:
        profile = HealthProfile(user_id=user_id)
        db.add(profile)
    return profile


def _weights(db: Session, user_id: int, limit: int = 90) -> list[WeightEntry]:
    return list(
        db.scalars(
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(WeightEntry.date_for.desc())
            .limit(limit)
        )
    )


def _health_out(db: Session, user_id: int) -> HealthOut:
    profile = _profile(db, user_id)
    weights = _weights(db, user_id)
    latest = weights[0] if weights else None
    computed = compute(profile, latest)
    return HealthOut(
        profile=profile,
        latest_weight=latest,
        weights=[WeightOut.model_validate(w) for w in weights],
        computed=computed,
    )


def _managed_child(db: Session, user_id: int, parent: User) -> User:
    """A child of the parent's own family. Anyone else - other adults, other
    families - 404s identically, leaking nothing."""
    target = db.get(User, user_id)
    if (
        target is None
        or target.family_id != parent.family_id
        or target.role != Role.child
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member")
    return target


# ---- self -------------------------------------------------------------------------


@router.get("/me/health", response_model=HealthOut)
def my_health(db: Session = Depends(get_db), user: User = Depends(require_family)):
    return _health_out(db, user.id)


@router.put("/me/health/profile", response_model=HealthOut)
def update_profile(
    data: HealthProfileIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    profile = _profile(db, user.id, create=True)
    for field in data.model_fields_set:
        setattr(profile, field, getattr(data, field))
    db.commit()
    return _health_out(db, user.id)


@router.put("/me/health/weight", response_model=HealthOut)
def log_weight(
    data: WeightIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """One weigh-in per day; weighing again the same day updates it. The
    latest weigh-in is what the calorie math reads, so this is also how the
    auto target adjusts itself over time."""
    if data.date_for > dt.date.today() + dt.timedelta(days=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That date hasn't happened yet")
    entry = db.scalar(
        select(WeightEntry).where(
            WeightEntry.user_id == user.id, WeightEntry.date_for == data.date_for
        )
    )
    if entry is None:
        entry = WeightEntry(user_id=user.id, date_for=data.date_for)
        db.add(entry)
    entry.weight_kg = data.weight_kg
    entry.body_fat_pct = data.body_fat_pct
    db.commit()
    return _health_out(db, user.id)


def _apply_goal(db: Session, target_user_id: int, data: GoalIn) -> None:
    profile = _profile(db, target_user_id, create=True)
    profile.goal = data.goal
    profile.rate_lbs_per_week = data.rate_lbs_per_week
    profile.goal_weight_kg = data.goal_weight_kg
    db.commit()


@router.put("/me/health/goal", response_model=HealthOut)
def set_my_goal(
    data: GoalIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    if user.role == Role.child:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A parent sets goals for child accounts"
        )
    _apply_goal(db, user.id, data)
    return _health_out(db, user.id)


# ---- parent-managed: a child's health section ---------------------------------------


@router.get("/members/{user_id}/health", response_model=HealthOut)
def child_health(
    user_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    child = _managed_child(db, user_id, parent)
    return _health_out(db, child.id)


@router.put("/members/{user_id}/health/goal", response_model=HealthOut)
def set_child_goal(
    user_id: int,
    data: GoalIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    child = _managed_child(db, user_id, parent)
    _apply_goal(db, child.id, data)
    return _health_out(db, child.id)
