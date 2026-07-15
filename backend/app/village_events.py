"""The copy machinery behind shared village events.

An event is a pointer at the organizer's own Item; a family that RSVPs
"going" gets an independent Item COPY on its board (the recipe save-a-copy
model), so the feed, calendar, reminders, and pushes need zero special
cases. Everything that writes a copy goes through _SYNCED_FIELDS +
shift_schedule here, so materialize and sync can never drift apart. This
module lives outside routers/ because both items.py and villages.py need it.

Nothing here commits: callers own the transaction, same as inbox.record.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import shift_schedule
from app.models import (
    Completion,
    Family,
    Item,
    ReminderLog,
    Role,
    RsvpStatus,
    User,
    VillageEvent,
    VillageEventRsvp,
    Visibility,
)

# Every field a copy takes verbatim from the source. Schedule fields travel
# separately through shift_schedule. A future Item column must consciously
# join or skip this tuple.
_SYNCED_FIELDS = ("kind", "title", "notes", "location", "all_day")


def _copy_schedule(src: Item, from_tz: str | None, to_tz: str | None):
    return shift_schedule(
        src.date_for, src.time_of_day, src.end_time, src.all_day, from_tz, to_tz
    )


def _apply(copy: Item, src: Item, from_tz: str | None, to_tz: str | None) -> None:
    for f in _SYNCED_FIELDS:
        setattr(copy, f, getattr(src, f))
    copy.date_for, copy.time_of_day, copy.end_time = _copy_schedule(src, from_tz, to_tz)


def materialize(
    db: Session,
    event: VillageEvent,
    src: Item,
    organizer_tz: str | None,
    family: Family,
    parent: User,
) -> Item:
    """A going family's own copy of the event: family-visible, no assignees,
    owned by the parent who RSVPed, schedule on the family's clock. If the
    organizer has the source called off right now, the copy is born with the
    same strikethrough."""
    copy = Item(
        family_id=family.id,
        owner_id=parent.id,
        visibility=Visibility.family,
        village_event_id=event.id,
    )
    _apply(copy, src, organizer_tz, family.timezone)
    db.add(copy)
    cancelled = db.scalar(
        select(Completion).where(
            Completion.item_id == src.id, Completion.cancelled.is_(True)
        )
    )
    if cancelled is not None:
        db.flush()  # the copy needs its id for the mirrored mark
        db.add(
            Completion(
                item_id=copy.id,
                user_id=None,  # never leak the organizer's cross-family id
                date_for=copy.date_for or cancelled.date_for,
                cancelled=True,
            )
        )
    return copy


def copies_of(db: Session, event_ids: list[int]) -> list[Item]:
    if not event_ids:
        return []
    return list(db.scalars(select(Item).where(Item.village_event_id.in_(event_ids))))


def events_on(db: Session, item: Item) -> list[VillageEvent]:
    """The share rows pointing at this source item (empty for copies and
    unshared cards — the cheap no-op path for every board edit)."""
    if item.village_event_id is not None:
        return []
    return list(db.scalars(select(VillageEvent).where(VillageEvent.item_id == item.id)))


def sync_copies(db: Session, src: Item, rescheduled: bool) -> list[User]:
    """After an organizer edit: rewrite every copy from the source (schedule
    reconverted onto each family's clock), clear rescheduled copies' reminder
    claims so they remind afresh, and hand back the going families' adults
    for the caller's notifications. Caller commits."""
    events = events_on(db, src)
    if not events:
        return []
    organizer_tz = db.scalar(select(Family.timezone).where(Family.id == src.family_id))
    copies = copies_of(db, [e.id for e in events])
    tz_by_family = {
        f.id: f.timezone
        for f in db.scalars(select(Family).where(Family.id.in_({c.family_id for c in copies})))
    }
    for copy in copies:
        _apply(copy, src, organizer_tz, tz_by_family.get(copy.family_id))
        if rescheduled:
            db.execute(
                ReminderLog.__table__.delete().where(ReminderLog.item_id == copy.id)
            )
    return going_adults(db, [e.id for e in events])


def going_adults(db: Session, event_ids: list[int]) -> list[User]:
    """Every adult of every family currently RSVPed going, deduped — the
    audience for reschedules, call-offs, and deletions."""
    if not event_ids:
        return []
    family_ids = set(
        db.scalars(
            select(VillageEventRsvp.family_id).where(
                VillageEventRsvp.event_id.in_(event_ids),
                VillageEventRsvp.status == RsvpStatus.going,
            )
        )
    )
    if not family_ids:
        return []
    # is_minor is a role-derived property, not a column: adults == parents.
    return list(
        db.scalars(
            select(User).where(User.family_id.in_(family_ids), User.role == Role.parent)
        )
    )


def delete_copies(db: Session, event_ids: list[int]) -> None:
    """Remove every materialized copy of these events. Explicit rather than
    FK-only: the notify lists are collected before rows disappear, and the
    deletes hold in both dialects without leaning on cascade order. (The
    CASCADE FK is live in SQLite too — use_alter still renders inline in its
    DDL — so on a source-item delete it races these ORM deletes and SQLAlchemy
    logs a benign rowcount warning.)"""
    for copy in copies_of(db, event_ids):
        db.delete(copy)  # ORM delete so completions cascade in both dialects


def delete_copies_for_family(db: Session, event_id: int, family_id: int) -> None:
    """One family's copy of one event leaves their board (RSVP moved away
    from going, or the answer was withdrawn)."""
    for copy in db.scalars(
        select(Item).where(
            Item.village_event_id == event_id, Item.family_id == family_id
        )
    ):
        db.delete(copy)