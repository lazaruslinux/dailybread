"""One-time breadcrumb backfill: pay for the life the family already lived.

Run with:  python -m app.crumbs_backfill

The window opens at each family's FIRST completion — the day they really
started using the board — so imported health history from before the app
existed doesn't hand anyone a head start. Every award goes through the same
source keys the live hooks use, so re-running is safe and running it after
launch never double-pays a day the live path already covered.

Per member, inside the window:
  - each fully-read verse day        +3   (verses:<date>)
  - streak milestones crossed        +5/+15/+50 (vstreak:<n>)
  - each day with a 15+ min workout  +3   (workout:<date>)
  - completions, capped 10 a day     +1   (item:<id>:<date>)
  - a login proxy: any day they left a trace (completion, diary entry, mood,
    verse check)                     +1   (login:<date>)
"""

import datetime as dt
from collections import defaultdict

from sqlalchemy import func, select

from app import crumbs
from app.db import SessionLocal
from app.models import (
    Completion,
    DiaryEntry,
    Family,
    Item,
    Mood,
    User,
    VerseCheck,
    Workout,
)
from app.routers.verses import VERSES_PER_DAY


def _family_window(db, family_id: int) -> dt.date | None:
    """The family's first check-off; None means they never used the board."""
    first = db.scalar(
        select(func.min(Completion.date_for))
        .join(Item, Item.id == Completion.item_id)
        .where(Item.family_id == family_id, Completion.pending.is_(False))
    )
    return first


def _verse_days(db, user_id: int, start: dt.date) -> list[dt.date]:
    rows = db.execute(
        select(VerseCheck.date_for)
        .where(VerseCheck.user_id == user_id, VerseCheck.date_for >= start)
        .group_by(VerseCheck.date_for)
        .having(func.count() >= VERSES_PER_DAY)
        .order_by(VerseCheck.date_for)
    ).all()
    return [day for (day,) in rows]


def backfill_user(db, user: User, start: dt.date) -> int:
    total = 0

    # Verse days, and the milestones the chain crossed along the way.
    verse_days = _verse_days(db, user.id, start)
    streak = 0
    previous: dt.date | None = None
    for day in verse_days:
        total += crumbs.award(
            db, user, "verses", crumbs.VERSES_CRUMBS, f"verses:{day.isoformat()}", day
        )
        streak = streak + 1 if previous == day - dt.timedelta(days=1) else 1
        previous = day
        total += crumbs.award_streak_milestones(db, user, streak, day)

    # Days with a real workout.
    workout_days = sorted(
        {
            started.date()
            for (started,) in db.execute(
                select(Workout.started_at).where(
                    Workout.user_id == user.id,
                    Workout.started_at >= dt.datetime.combine(start, dt.time.min),
                    Workout.duration_s >= crumbs.WORKOUT_MIN_SECONDS,
                )
            )
        }
    )
    for day in workout_days:
        total += crumbs.award(
            db, user, "workout", crumbs.WORKOUT_CRUMBS, f"workout:{day.isoformat()}", day
        )

    # Completions, oldest first, deterministic, 10 a day like the live cap.
    by_day: dict[dt.date, list[int]] = defaultdict(list)
    for item_id, day in db.execute(
        select(Completion.item_id, Completion.date_for)
        .where(
            Completion.user_id == user.id,
            Completion.date_for >= start,
            Completion.pending.is_(False),
            Completion.cancelled.is_(False),
        )
        .order_by(Completion.date_for, Completion.item_id)
    ):
        by_day[day].append(item_id)
    for day, item_ids in by_day.items():
        for item_id in item_ids[: crumbs.COMPLETE_DAILY_CAP]:
            total += crumbs.award(
                db, user, "complete", crumbs.COMPLETE_CRUMBS,
                f"item:{item_id}:{day.isoformat()}", day,
            )

    # The login proxy: any day with a trace of them.
    active: set[dt.date] = set(by_day)
    for model, col in ((DiaryEntry, DiaryEntry.date_for), (Mood, Mood.date_for), (VerseCheck, VerseCheck.date_for)):
        for (day,) in db.execute(
            select(col).where(model.user_id == user.id, col >= start).distinct()
        ):
            active.add(day)
    for day in sorted(active):
        total += crumbs.award(
            db, user, "login", crumbs.LOGIN_CRUMBS, f"login:{day.isoformat()}", day
        )

    return total


def main() -> None:
    with SessionLocal() as db:
        for family in db.scalars(select(Family)):
            start = _family_window(db, family.id)
            if start is None:
                print(f"{family.name}: never used the board, nothing to backfill")
                continue
            print(f"{family.name}: window opens {start.isoformat()}")
            for user in db.scalars(select(User).where(User.family_id == family.id)):
                earned = backfill_user(db, user, start)
                total = crumbs.total_for(db, user.id)
                level, _, _ = crumbs.level_of(total)
                print(
                    f"  {user.display_name}: +{earned} backfilled, "
                    f"total {total}, level {level} ({crumbs.tier_of(level)})"
                )


if __name__ == "__main__":
    main()
