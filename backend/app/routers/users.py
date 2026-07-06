import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import avatars
from app.db import get_db
from app.deps import require_family
from app.models import JournalEntry, Mood, Role, User
from app.schemas import (
    FamilyMemberOut,
    JournalIn,
    JournalOut,
    MoodIn,
    MoodOut,
    ProfileOut,
    ProfileUpdateIn,
)

router = APIRouter(tags=["users"])

_MAX_DATE_DRIFT = dt.timedelta(days=1)


def _profile_out(user: User, mood: Mood | None, viewer: User) -> ProfileOut:
    return ProfileOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_admin=user.is_admin,
        is_owner=user.is_owner,
        family_id=user.family_id,
        avatar_updated_at=user.avatar_updated_at,
        bio=user.bio,
        created_at=user.created_at,
        mood=_visible_mood(mood, viewer, user.id),
    )


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
        is_owner=user.is_owner,
        family_id=user.family_id,
        avatar_updated_at=user.avatar_updated_at,
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
    return _profile_out(user, mood, viewer)


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
    return _profile_out(me, mood, me)


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


# ---- journal -------------------------------------------------------------------
# A member's daily written entry. Strictly private: there is no endpoint to read
# anyone else's, and nothing about a journal appears on the family strip.


@router.get("/me/journal", response_model=JournalOut | None)
def get_my_journal(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    me: User = Depends(require_family),
):
    """Your entry for a day, or null if you haven't written one."""
    _check_date(date_for)
    return db.scalar(
        select(JournalEntry).where(
            JournalEntry.user_id == me.id, JournalEntry.date_for == date_for
        )
    )


@router.get("/me/journal/history", response_model=list[JournalOut])
def my_journal_history(
    db: Session = Depends(get_db),
    me: User = Depends(require_family),
):
    """Your past entries, most recent day first, for browsing back through."""
    return db.scalars(
        select(JournalEntry)
        .where(JournalEntry.user_id == me.id)
        .order_by(JournalEntry.date_for.desc())
    ).all()


@router.put("/me/journal", response_model=JournalOut)
def set_my_journal(
    data: JournalIn,
    db: Session = Depends(get_db),
    me: User = Depends(require_family),
):
    """Write (or rewrite) your entry for a day. Upsert: one row per day. An
    empty body clears the day so a blanked-out entry doesn't linger in history."""
    _check_date(data.date_for)
    entry = db.scalar(
        select(JournalEntry).where(
            JournalEntry.user_id == me.id, JournalEntry.date_for == data.date_for
        )
    )
    body = data.body.strip()
    if not body:
        if entry is not None:
            db.delete(entry)
            db.commit()
        return JournalOut(date_for=data.date_for, body="", updated_at=dt.datetime.now(dt.timezone.utc))
    if entry is None:
        entry = JournalEntry(user_id=me.id, date_for=data.date_for)
        db.add(entry)
    entry.body = body
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/me/journal", status_code=status.HTTP_204_NO_CONTENT)
def clear_my_journal(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    me: User = Depends(require_family),
):
    _check_date(date_for)
    entry = db.scalar(
        select(JournalEntry).where(
            JournalEntry.user_id == me.id, JournalEntry.date_for == date_for
        )
    )
    if entry is not None:
        db.delete(entry)
        db.commit()


# ---- avatars -------------------------------------------------------------------


def _target_member(user_id: int, viewer: User, db: Session) -> User:
    """The addressed member, but only within the viewer's own family; a
    cross-family id 404s so ids never leak."""
    user = db.get(User, user_id)
    if user is None or user.family_id != viewer.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    return user


def _require_can_set_avatar(target: User, viewer: User) -> None:
    # Only a parent manages photos, and only their own or a child's — never
    # another parent's. Children don't set avatars at all, not even their own.
    if viewer.role != Role.parent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a parent can change photos.")
    if target.id != viewer.id and target.role == Role.parent:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can't change another parent's photo."
        )


@router.get("/users/{user_id}/avatar")
def get_avatar(
    user_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(require_family),
):
    """Serve a member's avatar image. 404 when they have none so the frontend
    falls back to generated initials. The URL is versioned by avatar_updated_at,
    so the response can be cached hard."""
    user = _target_member(user_id, viewer, db)
    path = avatars.avatar_path(user.id)
    if user.avatar_updated_at is None or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No avatar")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.post("/users/{user_id}/avatar", response_model=ProfileOut)
async def upload_avatar(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    viewer: User = Depends(require_family),
):
    """Upload/replace a member's photo. Whatever the phone sends is normalised
    to a 256x256 WebP on disk; the DB only records that a photo now exists."""
    user = _target_member(user_id, viewer, db)
    _require_can_set_avatar(user, viewer)
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "That file is not an image.")
    raw = await file.read()
    if len(raw) > avatars.MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That image is too large.")
    try:
        avatars.process_and_save(raw, user.id)
    except avatars.BadImage as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    user.avatar_updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(user)
    mood = db.scalar(
        select(Mood).where(Mood.user_id == user.id, Mood.date_for == dt.date.today())
    )
    return _profile_out(user, mood, viewer)


@router.delete("/users/{user_id}/avatar", status_code=status.HTTP_204_NO_CONTENT)
def remove_avatar(
    user_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(require_family),
):
    """Remove a member's photo and revert them to generated initials."""
    user = _target_member(user_id, viewer, db)
    _require_can_set_avatar(user, viewer)
    avatars.delete_avatar(user.id)
    user.avatar_updated_at = None
    db.commit()
