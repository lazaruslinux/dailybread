import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_family
from app.models import Mood, User
from app.schemas import FamilyMemberOut, MoodIn, MoodOut, ProfileOut, ProfileUpdateIn

router = APIRouter(tags=["users"])

_MAX_DATE_DRIFT = dt.timedelta(days=1)


def _check_date(date_for: dt.date) -> dt.date:
    if abs(date_for - dt.date.today()) > _MAX_DATE_DRIFT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Date is too far from the server clock")
    return date_for


def _visible_mood(mood: Mood | None, viewer: User, owner_id: int) -> MoodOut | None:
    """The privacy rule, in one place: you always see your own mood; others
    see it only if it isn't hidden. A hidden mood and no mood look identical
    from the outside, so hiding doesn't leak that something is being hidden."""
    if mood is None:
        return None
    if mood.hidden and viewer.id != owner_id:
        return None
    return MoodOut.model_validate(mood)


def _member_out(user: User, mood: Mood | None, viewer: User) -> FamilyMemberOut:
    return FamilyMemberOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_admin=user.is_admin,
        mood=_visible_mood(mood, viewer, user.id),
    )


@router.get("/users", response_model=list[FamilyMemberOut])
def family(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    viewer: User = Depends(require_family),
):
    """The family strip: every member plus their visible mood for the day.
    Any signed-in member can see this; it's their household — and ONLY theirs."""
    _check_date(date_for)
    members = db.scalars(
        select(User).where(User.family_id == viewer.family_id).order_by(User.created_at)
    ).all()
    member_ids = [u.id for u in members]
    moods = {
        m.user_id: m
        for m in db.scalars(
            select(Mood).where(Mood.date_for == date_for, Mood.user_id.in_(member_ids))
        )
    }
    return [_member_out(u, moods.get(u.id), viewer) for u in members]


@router.get("/users/{user_id}/profile", response_model=ProfileOut)
def profile(
    user_id: int,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    viewer: User = Depends(require_family),
):
    _check_date(date_for)
    user = db.get(User, user_id)
    # Cross-family profiles 404 like they don't exist, so ids don't leak.
    if user is None or user.family_id != viewer.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    mood = db.scalar(
        select(Mood).where(Mood.user_id == user.id, Mood.date_for == date_for)
    )
    return ProfileOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_admin=user.is_admin,
        bio=user.bio,
        created_at=user.created_at,
        mood=_visible_mood(mood, viewer, user.id),
    )


@router.patch("/me/profile", response_model=ProfileOut)
def update_my_profile(
    data: ProfileUpdateIn,
    db: Session = Depends(get_db),
    me: User = Depends(require_family),
):
    """Your profile is yours: bio and display name, no one else's. Roles and
    admin flags stay in the admin-only endpoints."""
    if data.display_name is not None:
        me.display_name = data.display_name
    if data.bio is not None:
        me.bio = data.bio
    db.commit()
    db.refresh(me)
    mood = db.scalar(
        select(Mood).where(Mood.user_id == me.id, Mood.date_for == dt.date.today())
    )
    return ProfileOut(
        id=me.id,
        username=me.username,
        display_name=me.display_name,
        role=me.role,
        is_admin=me.is_admin,
        bio=me.bio,
        created_at=me.created_at,
        mood=_visible_mood(mood, me, me.id),
    )


@router.put("/me/mood", response_model=MoodOut)
def set_my_mood(
    data: MoodIn,
    db: Session = Depends(get_db),
    me: User = Depends(require_family),
):
    """Set (or change) your mood for a day. Upsert: one row per member per day."""
    _check_date(data.date_for)
    mood = db.scalar(
        select(Mood).where(Mood.user_id == me.id, Mood.date_for == data.date_for)
    )
    if mood is None:
        mood = Mood(user_id=me.id, date_for=data.date_for)
        db.add(mood)
    mood.level = data.level
    mood.hidden = data.hidden
    db.commit()
    db.refresh(mood)
    return mood


@router.delete("/me/mood", status_code=status.HTTP_204_NO_CONTENT)
def clear_my_mood(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    me: User = Depends(require_family),
):
    _check_date(date_for)
    mood = db.scalar(
        select(Mood).where(Mood.user_id == me.id, Mood.date_for == date_for)
    )
    if mood is not None:
        db.delete(mood)
        db.commit()
