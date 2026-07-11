"""Daily verse check-offs and the reading streak. Strictly opt-in.

The day's three verses are deterministic from the date (the client bundles the
text; see frontend lib/verses.ts) — the server only records which of the three
a member has checked, per day. A day with all three checked counts toward the
member's streak, with the same grace the routine streaks give: an unfinished
today doesn't break yesterday's chain, a genuinely missed day does.

Privacy: which verses, on which days, is the member's own business, like the
journal. Only the streak NUMBER is surfaced — to the family always (it sits
beside their name on the strip), to villages only when the member opts in.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_family
from app.models import User, VerseCheck
from app.schemas import VerseCheckIn, VerseSettingsIn, VersesOut

router = APIRouter(tags=["verses"])

VERSES_PER_DAY = 3
# The furthest a streak walk looks back; a year-plus chain still terminates.
_SCAN_LIMIT_DAYS = 400
_MAX_DATE_DRIFT = dt.timedelta(days=1)


def _check_date(date_for: dt.date) -> dt.date:
    if abs(date_for - dt.date.today()) > _MAX_DATE_DRIFT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Date is too far from the server clock")
    return date_for


def _streak_from(complete_days: set[dt.date], today: dt.date) -> int:
    count = 0
    day = today
    first = True
    while (today - day).days <= _SCAN_LIMIT_DAYS:
        if day in complete_days:
            count += 1
        elif not first:
            break  # a genuinely missed day ends the chain
        # else: today's reading may simply not have happened yet — grace.
        first = False
        day -= dt.timedelta(days=1)
    return count


def streaks_for(db: Session, user_ids: list[int], today: dt.date) -> dict[int, int]:
    """Each member's current streak, in one query for the whole family."""
    if not user_ids:
        return {}
    rows = db.execute(
        select(VerseCheck.user_id, VerseCheck.date_for)
        .where(
            VerseCheck.user_id.in_(user_ids),
            VerseCheck.date_for >= today - dt.timedelta(days=_SCAN_LIMIT_DAYS),
        )
        .group_by(VerseCheck.user_id, VerseCheck.date_for)
        .having(func.count() >= VERSES_PER_DAY)
    ).all()
    complete: dict[int, set[dt.date]] = {}
    for user_id, day in rows:
        complete.setdefault(user_id, set()).add(day)
    return {uid: _streak_from(days, today) for uid, days in complete.items()}


def _verses_out(db: Session, user: User, date_for: dt.date) -> VersesOut:
    checked = set(
        db.scalars(
            select(VerseCheck.verse_idx).where(
                VerseCheck.user_id == user.id, VerseCheck.date_for == date_for
            )
        )
    )
    return VersesOut(
        enabled=user.verse_streak_enabled,
        share=user.share_verse_streak,
        checks=[i in checked for i in range(VERSES_PER_DAY)],
        streak=streaks_for(db, [user.id], dt.date.today()).get(user.id, 0),
    )


@router.get("/me/verses", response_model=VersesOut)
def my_verses(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    _check_date(date_for)
    return _verses_out(db, user, date_for)


@router.post("/me/verses/check", response_model=VersesOut)
def check_verse(
    data: VerseCheckIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    _check_date(data.date_for)
    if not user.verse_streak_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turn on verse check-offs first")
    exists = db.scalar(
        select(VerseCheck).where(
            VerseCheck.user_id == user.id,
            VerseCheck.date_for == data.date_for,
            VerseCheck.verse_idx == data.verse_idx,
        )
    )
    if exists is None:
        db.add(
            VerseCheck(user_id=user.id, date_for=data.date_for, verse_idx=data.verse_idx)
        )
        db.commit()
    return _verses_out(db, user, data.date_for)


@router.delete("/me/verses/check", response_model=VersesOut)
def uncheck_verse(
    date_for: dt.date = Query(alias="date"),
    verse_idx: int = Query(alias="idx", ge=0, le=VERSES_PER_DAY - 1),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    _check_date(date_for)
    row = db.scalar(
        select(VerseCheck).where(
            VerseCheck.user_id == user.id,
            VerseCheck.date_for == date_for,
            VerseCheck.verse_idx == verse_idx,
        )
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return _verses_out(db, user, date_for)


@router.put("/me/verses/settings", response_model=VersesOut)
def verse_settings(
    data: VerseSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Turn the check-offs (and the village streak sharing) on or off. Fields
    not sent stay as they are; turning check-offs off keeps the history, so
    coming back later resumes rather than restarts (the gap still breaks the
    streak, honestly)."""
    sent = data.model_dump(exclude_unset=True)
    if "enabled" in sent and sent["enabled"] is not None:
        user.verse_streak_enabled = sent["enabled"]
    if "share" in sent and sent["share"] is not None:
        user.share_verse_streak = sent["share"]
    db.commit()
    return _verses_out(db, user, dt.date.today())
