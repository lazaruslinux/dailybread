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

from app import crumbs
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
    # Anchor each walk at the member's newest complete day when it's ahead of
    # the server's clock: a phone past midnight legitimately checks off
    # "tomorrow" (the write guard allows one day of drift), and that reading
    # must count NOW, not after the server's own midnight.
    return {
        uid: _streak_from(days, max(today, max(days))) for uid, days in complete.items()
    }


def _verses_out(db: Session, user: User, date_for: dt.date) -> VersesOut:
    checked = set(
        db.scalars(
            select(VerseCheck.verse_idx).where(
                VerseCheck.user_id == user.id, VerseCheck.date_for == date_for
            )
        )
    )
    return VersesOut(
        enabled=user.verses_enabled,
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
    if not user.verses_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turn on daily verses first")
    exists = db.scalar(
        select(VerseCheck).where(
            VerseCheck.user_id == user.id,
            VerseCheck.date_for == data.date_for,
            VerseCheck.verse_idx == data.verse_idx,
        )
    )
    awarded = 0
    if exists is None:
        db.add(
            VerseCheck(user_id=user.id, date_for=data.date_for, verse_idx=data.verse_idx)
        )
        db.commit()
        # Checks are one-way (unchecking a read verse was pointless — the fold
        # arrow is how the card gets out of the way), so the day's third check
        # is THE moment: +3, plus any streak milestone just reached.
        done_today = db.scalar(
            select(func.count()).where(
                VerseCheck.user_id == user.id, VerseCheck.date_for == data.date_for
            )
        )
        if done_today >= VERSES_PER_DAY:
            awarded = crumbs.award(
                db,
                user,
                "verses",
                crumbs.VERSES_CRUMBS,
                f"verses:{data.date_for.isoformat()}",
                data.date_for,
            )
            streak = streaks_for(db, [user.id], dt.date.today()).get(user.id, 0)
            awarded += crumbs.award_streak_milestones(db, user, streak, data.date_for)
    out = _verses_out(db, user, data.date_for)
    out.crumbs_awarded = awarded
    return out


@router.put("/me/verses/settings", response_model=VersesOut)
def verse_settings(
    data: VerseSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Turn the check-offs on or off (village sharing now lives with the
    level toggle under Villages). Turning check-offs off keeps the history,
    so coming back later resumes rather than restarts (the gap still breaks
    the streak, honestly)."""
    sent = data.model_dump(exclude_unset=True)
    if "enabled" in sent and sent["enabled"] is not None:
        user.verses_enabled = sent["enabled"]
    db.commit()
    return _verses_out(db, user, dt.date.today())
