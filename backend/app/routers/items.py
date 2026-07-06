import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import recurrence
from app.db import get_db
from app.deps import require_family, require_parent
from app.models import Completion, Item, ItemKind, RepeatType, Role, User, Visibility
from app.schemas import (
    AssigneeCompletion,
    CalendarDayOut,
    CalendarOut,
    FeedItemOut,
    FeedOut,
    ItemIn,
    ItemUpdate,
    RepeatIn,
    RepeatOut,
)

router = APIRouter(prefix="/items", tags=["items"])

# The phone knows the family's local date; the server might be in UTC. So
# "today" endpoints take the date from the client, but only within a day of
# the server clock, which blocks backdating while tolerating timezones.
_MAX_DATE_DRIFT = dt.timedelta(days=1)


def _check_date(date_for: dt.date) -> dt.date:
    if abs(date_for - dt.date.today()) > _MAX_DATE_DRIFT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Date is too far from the server clock")
    return date_for


def _get_item(db: Session, item_id: int, family_id: int) -> Item:
    """Fetch an item only if it belongs to the caller's family. Cross-family
    ids 404 like they don't exist, so nothing leaks across households."""
    item = db.get(Item, item_id)
    if item is None or item.family_id != family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item")
    return item


def _visible_to(item: Item, user: User) -> bool:
    """Can this member see the card? family = the whole household; private =
    the owner plus anyone assigned (they must see it to do it). A card whose
    owner was deleted (owner_id NULL) is treated as family so it doesn't vanish."""
    if item.visibility == Visibility.family or item.owner_id is None:
        return True
    if item.owner_id == user.id:
        return True
    return any(a.id == user.id for a in item.assignees)


def _require_visible(item: Item, user: User) -> None:
    # 404, not 403: a card the member can't see should look like it doesn't
    # exist, the same way cross-family ids do.
    if not _visible_to(item, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item")


def _routine_participants(db: Session, item: Item) -> list[User]:
    """Who checks off a routine, each on their own: the people assigned to it,
    or the owner alone when nobody is assigned. Independent of visibility, so a
    routine can be shown to the whole family while only its assignees do it."""
    if item.assignees:
        return list(item.assignees)
    owner = db.get(User, item.owner_id) if item.owner_id else None
    return [owner] if owner is not None else []


def _resolve_completion_target(
    db: Session, item: Item, user: User, for_user: int | None
) -> User:
    """Return the member a completion is for, enforcing who may set it.

    Routines are per-person: you check your own, and a parent may check one off
    on any assignee's behalf via ?for=<id>. Other kinds are a single shared
    check (?for is ignored) that anyone involved, or any parent, may tap.
    """
    if item.kind == ItemKind.routine:
        if for_user is not None and for_user != user.id:
            # Acting on someone else's behalf is a parent-only power.
            if user.role != Role.parent:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, "Only a parent can check this off for someone else"
                )
            target = db.get(User, for_user)
            if target is None or target.family_id != user.family_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member")
            if not any(p.id == target.id for p in _routine_participants(db, item)):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "That routine isn't theirs to do")
            return target
        # Checking your own occurrence.
        if not any(p.id == user.id for p in _routine_participants(db, item)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This routine isn't yours to check")
        return user

    # Non-routine: one shared check. Anyone involved, or any parent (co-parents
    # share the household's chores and appointments), may complete it.
    involved = (item.owner_id is not None and item.owner_id == user.id) or any(
        a.id == user.id for a in item.assignees
    )
    if not (involved or user.role == Role.parent):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This card isn't yours to check")
    return user


def _mask_from_days(days: list[int]) -> int:
    """Pack weekday numbers (0=Mon .. 6=Sun) into a 7-bit mask."""
    mask = 0
    for d in days:
        if d < 0 or d > 6:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Weekday must be 0 (Mon) to 6 (Sun)")
        mask |= 1 << d
    return mask


def _resolve_repeat(repeat: RepeatIn | None):
    """Turn the API's repeat object into the item's stored recurrence columns:
    (repeat_type, repeat_days, repeat_interval, repeat_anchor, repeat_month_day)."""
    if repeat is None:
        return None, None, 1, None, None
    if repeat.type == RepeatType.weekly:
        return RepeatType.weekly, _mask_from_days(repeat.days), repeat.interval, repeat.anchor, None
    return RepeatType.monthly, None, repeat.interval, repeat.anchor, repeat.month_day


def _resolve_visibility(explicit: Visibility | None) -> Visibility:
    """Cards are private by default (the owner plus anyone assigned); the
    client opts into family visibility to put it on the whole family's board."""
    return explicit if explicit is not None else Visibility.private


def _bad(msg: str) -> None:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)


def _validate_item(item: Item) -> None:
    """Enforce each kind's final shape.

    Routines carry a repeat schedule, no date, and at most a single start time.
    Tasks are free-form. Activities are time blocks (start and end required).
    Appointments are calendar events: a start and end, or all-day (no times).
    """
    if item.kind == ItemKind.routine:
        if item.date_for is not None:
            _bad("Routines recur; they take no date")
        if item.repeat_type is None:
            _bad("Routines need a repeat schedule")
        if item.repeat_type == RepeatType.weekly and not item.repeat_days:
            _bad("Weekly routine needs at least one day")
        if item.repeat_type == RepeatType.monthly and not item.repeat_month_day:
            _bad("Monthly routine needs a day of the month")
        if (item.repeat_interval or 1) < 1:
            _bad("Repeat interval must be at least 1")
        if item.end_time is not None or item.all_day:
            _bad("Routines don't take an end time or all-day")
        return

    if item.repeat_type is not None:
        _bad("Only routines repeat")

    if item.kind == ItemKind.task:
        if item.end_time is not None or item.all_day:
            _bad("Tasks don't take an end time or all-day")
        return

    if item.kind == ItemKind.activity:
        if item.all_day:
            _bad("Activities can't be all-day")
        if item.date_for is None or item.time_of_day is None or item.end_time is None:
            _bad("Activities need a date and a start and end time")
        if item.end_time <= item.time_of_day:
            _bad("End time must be after the start time")
        return

    # appointment
    if item.date_for is None:
        _bad("Appointments need a date")
    if item.all_day:
        if item.time_of_day is not None or item.end_time is not None:
            _bad("An all-day appointment has no times")
    else:
        if item.time_of_day is None or item.end_time is None:
            _bad("Appointments need a start and end time, or mark them all-day")
        if item.end_time <= item.time_of_day:
            _bad("End time must be after the start time")


def _resolve_assignees(db: Session, ids: list[int], family_id: int) -> list[User]:
    """Validate that every id is a member of this family and return the User
    rows. Duplicates are collapsed."""
    users: list[User] = []
    seen: set[int] = set()
    for uid in ids:
        if uid in seen:
            continue
        seen.add(uid)
        member = db.get(User, uid)
        if member is None or member.family_id != family_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee does not exist")
        users.append(member)
    return users


def _occurs(item: Item, date: dt.date) -> bool:
    return recurrence.occurs_on(
        item.repeat_type,
        item.repeat_days,
        item.repeat_interval,
        item.repeat_anchor,
        item.repeat_month_day,
        date,
    )


def _streak(item: Item, completed_dates: set[dt.date], upto: dt.date) -> int:
    return recurrence.streak(
        item.repeat_type,
        item.repeat_days,
        item.repeat_interval,
        item.repeat_anchor,
        item.repeat_month_day,
        completed_dates,
        upto,
    )


def _repeat_out(item: Item) -> RepeatOut | None:
    if item.repeat_type is None:
        return None
    mask = item.repeat_days or 0
    days = [d for d in range(7) if mask & (1 << d)]
    return RepeatOut(
        type=item.repeat_type,
        days=days,
        interval=item.repeat_interval,
        month_day=item.repeat_month_day,
    )


def _feed_item(
    item: Item,
    completed: bool,
    streak: int | None,
    assignee_completions: list[AssigneeCompletion] | None,
) -> FeedItemOut:
    return FeedItemOut(
        id=item.id,
        owner_id=item.owner_id,
        kind=item.kind,
        title=item.title,
        notes=item.notes,
        visibility=item.visibility,
        assignees=item.assignees,
        shared_to_feed=item.shared_to_feed,
        time_of_day=item.time_of_day,
        end_time=item.end_time,
        all_day=item.all_day,
        date_for=item.date_for,
        repeat=_repeat_out(item),
        completed=completed,
        streak=streak,
        assignee_completions=assignee_completions,
    )


def _build_feed_item(db: Session, item: Item, user: User, date: dt.date) -> FeedItemOut:
    """Assemble one card's completion state for the requesting member.

    Routines are per-person: each participant gets their own completed/streak,
    and the requesting member's own state (or, if they're not a participant,
    whether every participant is done) becomes the card's headline state.
    Other kinds carry a single shared check.
    """
    if item.kind != ItemKind.routine:
        # A dated card is a one-shot: done once, regardless of which day the
        # check landed on. Tasks are reminders that can be ticked off ahead of
        # their due date, so the completion may sit on an earlier day than
        # date_for — checking by date would make it reappear as undone when the
        # due day arrives. An undated "anytime" task stays date-scoped so it
        # shows crossed out today and archives tomorrow.
        if item.date_for is not None:
            done = (
                db.scalar(select(Completion.id).where(Completion.item_id == item.id))
                is not None
            )
        else:
            done = (
                db.scalar(
                    select(Completion.id).where(
                        Completion.item_id == item.id, Completion.date_for == date
                    )
                )
                is not None
            )
        return _feed_item(item, completed=done, streak=None, assignee_completions=None)

    participants = _routine_participants(db, item)
    dates_by_user: dict[int, set[dt.date]] = {}
    for uid, day in db.execute(
        select(Completion.user_id, Completion.date_for).where(Completion.item_id == item.id)
    ):
        if uid is not None:
            dates_by_user.setdefault(uid, set()).add(day)

    completions = [
        AssigneeCompletion(
            user_id=p.id,
            completed=date in dates_by_user.get(p.id, set()),
            streak=_streak(item, dates_by_user.get(p.id, set()), date),
        )
        for p in participants
    ]
    mine = next((c for c in completions if c.user_id == user.id), None)
    if mine is not None:
        completed, streak = mine.completed, mine.streak
    else:
        completed = bool(completions) and all(c.completed for c in completions)
        streak = None
    return _feed_item(item, completed=completed, streak=streak, assignee_completions=completions)


@router.get("/feed", response_model=FeedOut)
def feed(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """The whole home screen in one request: today, anytime, upcoming.

    Only cards the member can see are returned; routines appear on a day only
    when their schedule lands on it.
    """
    _check_date(date_for)

    items = (
        db.scalars(
            select(Item)
            .options(selectinload(Item.assignees))
            .where(
                Item.family_id == user.family_id,
                (Item.date_for.is_(None)) | (Item.date_for >= date_for),
            )
        )
        .unique()
        .all()
    )
    visible = [item for item in items if _visible_to(item, user)]

    today: list[FeedItemOut] = []
    anytime: list[FeedItemOut] = []
    upcoming: list[FeedItemOut] = []

    for item in visible:
        if item.kind == ItemKind.routine:
            if _occurs(item, date_for):
                today.append(_build_feed_item(db, item, user, date_for))
        elif item.date_for == date_for:
            today.append(_build_feed_item(db, item, user, date_for))
        elif item.date_for is None:
            fi = _build_feed_item(db, item, user, date_for)
            # An undated task finished on an earlier day is archived off the
            # board; finished today it stays put, crossed out, until midnight.
            if not fi.completed:
                earlier = db.scalar(
                    select(Completion.id).where(
                        Completion.item_id == item.id, Completion.date_for != date_for
                    )
                )
                if earlier is not None:
                    continue
            anytime.append(fi)
        elif item.date_for > date_for:
            upcoming.append(_build_feed_item(db, item, user, date_for))

    # All-day events first, then timed cards in day order; untimed sink to the end.
    late = dt.time(23, 59)
    today.sort(key=lambda i: (not i.all_day, i.time_of_day or late, i.title.lower()))
    anytime.sort(key=lambda i: (i.completed, i.title.lower()))  # done sink to the bottom
    upcoming.sort(key=lambda i: (i.date_for, not i.all_day, i.time_of_day or late, i.title.lower()))

    return FeedOut(date=date_for, today=today, anytime=anytime, upcoming=upcoming)


# A calendar request can span weeks, so it can't use the ±1-day "today" clamp;
# it's bounded by span length instead to keep the day-by-day expansion cheap.
_MAX_CALENDAR_SPAN = dt.timedelta(days=45)


@router.get("/calendar", response_model=CalendarOut)
def calendar(
    start: dt.date = Query(),
    end: dt.date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Scheduled cards across a date range, grouped by day. Routines are
    expanded onto each day their schedule lands on; other kinds appear on their
    own date. Undated "anytime" tasks are not scheduled and are left out.

    Every day in the range is returned (empty ones included) so the client can
    draw the whole week or month, dots and all, from a single response.
    """
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end must be on or after start")
    if end - start > _MAX_CALENDAR_SPAN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Calendar range is too wide")

    # Routines (recur, so always in play) plus non-routine cards dated in range.
    items = (
        db.scalars(
            select(Item)
            .options(selectinload(Item.assignees))
            .where(
                Item.family_id == user.family_id,
                or_(Item.repeat_type.isnot(None), Item.date_for.between(start, end)),
            )
        )
        .unique()
        .all()
    )
    visible = [item for item in items if _visible_to(item, user)]

    late = dt.time(23, 59)
    days: list[CalendarDayOut] = []
    day = start
    while day <= end:
        on_day = [
            _build_feed_item(db, item, user, day)
            for item in visible
            if (_occurs(item, day) if item.repeat_type is not None else item.date_for == day)
        ]
        on_day.sort(key=lambda i: (not i.all_day, i.time_of_day or late, i.title.lower()))
        days.append(CalendarDayOut(date=day, items=on_day))
        day += dt.timedelta(days=1)

    return CalendarOut(start=start, end=end, days=days)


@router.post("", response_model=FeedItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    data: ItemIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Parents put cards on their family's board. A card is the creator's own
    (personal) until it names members or is shared with the whole family."""
    assignees = _resolve_assignees(db, data.assignee_ids, parent.family_id)
    rtype, rdays, rinterval, ranchor, rmonthday = _resolve_repeat(data.repeat)
    shared = data.shared_to_feed if data.shared_to_feed is not None else (
        data.kind == ItemKind.activity
    )

    item = Item(
        family_id=parent.family_id,
        owner_id=parent.id,
        kind=data.kind,
        title=data.title,
        notes=data.notes,
        visibility=_resolve_visibility(data.visibility),
        assignees=assignees,
        shared_to_feed=shared,
        time_of_day=data.time_of_day,
        end_time=data.end_time,
        all_day=data.all_day,
        date_for=data.date_for,
        repeat_type=rtype,
        repeat_days=rdays,
        repeat_interval=rinterval,
        repeat_anchor=ranchor,
        repeat_month_day=rmonthday,
    )
    _validate_item(item)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _build_feed_item(db, item, parent, dt.date.today())


@router.patch("/{item_id}", response_model=FeedItemOut)
def update_item(
    item_id: int,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id, parent.family_id)
    _require_visible(item, parent)
    fields = data.model_fields_set  # only touch keys the client actually sent

    if "assignee_ids" in fields:
        item.assignees = _resolve_assignees(db, data.assignee_ids or [], parent.family_id)
    if "visibility" in fields and data.visibility is not None:
        item.visibility = data.visibility
    if "title" in fields and data.title is not None:
        item.title = data.title
    if "notes" in fields and data.notes is not None:
        item.notes = data.notes
    if "time_of_day" in fields:
        item.time_of_day = data.time_of_day
    if "end_time" in fields:
        item.end_time = data.end_time
    if "all_day" in fields and data.all_day is not None:
        item.all_day = data.all_day
    if "date_for" in fields:
        item.date_for = data.date_for
    if "repeat" in fields:
        (
            item.repeat_type,
            item.repeat_days,
            item.repeat_interval,
            item.repeat_anchor,
            item.repeat_month_day,
        ) = _resolve_repeat(data.repeat)
    if "shared_to_feed" in fields and data.shared_to_feed is not None:
        item.shared_to_feed = data.shared_to_feed

    _validate_item(item)
    db.commit()
    db.refresh(item)
    return _build_feed_item(db, item, parent, dt.date.today())


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id, parent.family_id)
    _require_visible(item, parent)
    db.delete(item)  # completions cascade away with it
    db.commit()


@router.post("/{item_id}/complete", response_model=FeedItemOut)
def complete_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    for_user: int | None = Query(default=None, alias="for"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    _check_date(date_for)
    item = _get_item(db, item_id, user.family_id)
    _require_visible(item, user)
    target = _resolve_completion_target(db, item, user, for_user)

    if item.kind == ItemKind.routine:
        # Per-person: the target member's own occurrence.
        exists = db.scalar(
            select(Completion.id).where(
                Completion.item_id == item.id,
                Completion.user_id == target.id,
                Completion.date_for == date_for,
            )
        )
    else:
        # Shared: one check for the whole card, whoever taps it.
        exists = db.scalar(
            select(Completion.id).where(
                Completion.item_id == item.id, Completion.date_for == date_for
            )
        )

    if exists is None:
        db.add(Completion(item_id=item.id, user_id=target.id, date_for=date_for))
        db.commit()

    return _build_feed_item(db, item, user, date_for)


@router.delete("/{item_id}/complete", response_model=FeedItemOut)
def uncomplete_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    for_user: int | None = Query(default=None, alias="for"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Undo an accidental check-off for that day."""
    _check_date(date_for)
    item = _get_item(db, item_id, user.family_id)
    _require_visible(item, user)
    target = _resolve_completion_target(db, item, user, for_user)

    if item.kind == ItemKind.routine:
        completion = db.scalar(
            select(Completion).where(
                Completion.item_id == item.id,
                Completion.user_id == target.id,
                Completion.date_for == date_for,
            )
        )
    else:
        completion = db.scalar(
            select(Completion).where(
                Completion.item_id == item.id, Completion.date_for == date_for
            )
        )
    if completion is not None:
        db.delete(completion)
        db.commit()

    return _build_feed_item(db, item, user, date_for)
