import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import push, recurrence
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
    PendingApprovalOut,
    RepeatIn,
    RepeatOut,
)

log = logging.getLogger("dailybread.items")

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
    owner was deleted (owner_id NULL) is treated as family so it doesn't vanish.

    Kid mode narrows "the whole household": a minor sees their own cards plus
    UNASSIGNED family cards (notices like "Grandma arrives 6 PM"), but a family
    card assigned to other people is none of their business. This is the single
    choke point — feed, calendar, and _require_visible all inherit the rule."""
    if item.owner_id == user.id:
        return True
    if any(a.id == user.id for a in item.assignees):
        return True
    if item.visibility == Visibility.family or item.owner_id is None:
        return not user.is_minor or not item.assignees
    return False


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
        _validate_repeat(item)
        if item.end_time is not None or item.all_day:
            _bad("Routines don't take an end time or all-day")
        return

    if item.kind == ItemKind.task:
        if item.repeat_type is not None:
            _bad("Tasks don't repeat")
        if item.end_time is not None or item.all_day:
            _bad("Tasks don't take an end time or all-day")
        return

    if item.kind == ItemKind.activity:
        if item.repeat_type is not None:
            _bad("Activities don't repeat")
        if item.all_day:
            _bad("Activities can't be all-day")
        if item.date_for is None or item.time_of_day is None or item.end_time is None:
            _bad("Activities need a date and a start and end time")
        if item.end_time <= item.time_of_day:
            _bad("End time must be after the start time")
        return

    # appointment — a one-off on its date, or (the weekly work meeting) a
    # repeating one that recurs like a routine but keeps its shared check
    # and its start–end times.
    if item.repeat_type is not None:
        if item.date_for is not None:
            _bad("A repeating appointment recurs; it takes no date")
        if item.all_day:
            _bad("A repeating appointment needs times, not all-day")
        _validate_repeat(item)
    elif item.date_for is None:
        _bad("Appointments need a date")
    if item.all_day:
        if item.time_of_day is not None or item.end_time is not None:
            _bad("An all-day appointment has no times")
    else:
        if item.time_of_day is None or item.end_time is None:
            _bad("Appointments need a start and end time, or mark them all-day")
        if item.end_time <= item.time_of_day:
            _bad("End time must be after the start time")


def _validate_repeat(item: Item) -> None:
    if item.repeat_type == RepeatType.weekly and not item.repeat_days:
        _bad("Weekly repeat needs at least one day")
    if item.repeat_type == RepeatType.monthly and not item.repeat_month_day:
        _bad("Monthly repeat needs a day of the month")
    if (item.repeat_interval or 1) < 1:
        _bad("Repeat interval must be at least 1")


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
    pending: bool = False,
    pending_by: int | None = None,
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
        pending=pending,
        pending_by=pending_by,
        assignee_completions=assignee_completions,
    )


# One item's completion rows, prefetched: (user_id, date_for, pending) triples.
# A pending row is a minor's tap awaiting a parent — it must never read as done.
CompletionRows = list[tuple[int | None, dt.date, bool]]


def _completions_by_item(db: Session, items: list[Item]) -> dict[int, CompletionRows]:
    """Every completion for these items in ONE query, keyed by item id.

    The feed and calendar assemble many cards at once — and the calendar
    assembles each card once per day it appears. Querying completions inside
    that loop turned one month-view request into hundreds of little selects;
    a single IN(...) fetch scales with the data instead of with the view.
    """
    rows: dict[int, CompletionRows] = {item.id: [] for item in items}
    if rows:
        for item_id, uid, day, pending in db.execute(
            select(
                Completion.item_id, Completion.user_id, Completion.date_for, Completion.pending
            ).where(Completion.item_id.in_(rows))
        ):
            rows[item_id].append((uid, day, pending))
    return rows


def _build_feed_item(
    db: Session, item: Item, user: User, date: dt.date, completions: CompletionRows
) -> FeedItemOut:
    """Assemble one card's completion state for the requesting member, from
    the item's prefetched completion rows (see _completions_by_item).

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
        # A pending row (a minor's tap awaiting a parent) never counts as done;
        # it surfaces separately so the card can show its waiting state.
        if item.date_for is not None:
            done = any(not pend for _, _, pend in completions)
            waiting = next((uid for uid, _, pend in completions if pend), None)
        else:
            done = any(day == date and not pend for _, day, pend in completions)
            waiting = next(
                (uid for uid, day, pend in completions if pend and day == date), None
            )
        return _feed_item(
            item,
            completed=done,
            streak=None,
            assignee_completions=None,
            pending=not done and waiting is not None,
            pending_by=waiting if not done else None,
        )

    participants = _routine_participants(db, item)
    dates_by_user: dict[int, set[dt.date]] = {}
    pending_by_user: dict[int, set[dt.date]] = {}
    for uid, day, pend in completions:
        if uid is not None:
            (pending_by_user if pend else dates_by_user).setdefault(uid, set()).add(day)

    completions = [
        AssigneeCompletion(
            user_id=p.id,
            completed=date in dates_by_user.get(p.id, set()),
            streak=_streak(item, dates_by_user.get(p.id, set()), date),
            pending=date in pending_by_user.get(p.id, set())
            and date not in dates_by_user.get(p.id, set()),
        )
        for p in participants
    ]
    mine = next((c for c in completions if c.user_id == user.id), None)
    if mine is not None:
        completed, streak, pending = mine.completed, mine.streak, mine.pending
    else:
        completed = bool(completions) and all(c.completed for c in completions)
        streak, pending = None, False
    return _feed_item(
        item,
        completed=completed,
        streak=streak,
        assignee_completions=completions,
        pending=pending,
        pending_by=user.id if pending else None,
    )


# One-off cards keep nagging for this long after their date before they fall
# off the board for good; past that they live only in the calendar's history.
_MAX_OVERDUE_LOOKBACK = dt.timedelta(days=90)
# How far ahead the board looks; dated cards beyond this show only on the calendar.
_NEXT_DAYS = dt.timedelta(days=7)


def _check_complete_date(date_for: dt.date) -> None:
    """Completing is allowed further back than the board's ±1-day "today" clamp:
    you can mark a missed item on the day it actually was (the calendar's whole
    point), within the same 90-day window the overdue list carries. Marking
    something done in the future is still refused (a day of timezone slack aside)."""
    today = dt.date.today()
    if date_for - today > _MAX_DATE_DRIFT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't complete something in the future")
    if today - date_for > _MAX_OVERDUE_LOOKBACK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That day is too far back to mark")


@router.get("/feed", response_model=FeedOut)
def feed(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """The whole home screen in one request: overdue, today, the next 7 days.

    Only cards the member can see are returned; routines appear on a day only
    when their schedule lands on it. The client buckets ``today`` by the clock.
    """
    _check_date(date_for)

    window_start = date_for - _MAX_OVERDUE_LOOKBACK
    window_end = date_for + _NEXT_DAYS
    items = (
        db.scalars(
            select(Item)
            .options(selectinload(Item.assignees))
            .where(
                Item.family_id == user.family_id,
                (Item.date_for.is_(None)) | (Item.date_for.between(window_start, window_end)),
            )
        )
        .unique()
        .all()
    )
    visible = [item for item in items if _visible_to(item, user)]
    comps = _completions_by_item(db, visible)

    overdue: list[FeedItemOut] = []
    today: list[FeedItemOut] = []
    next7: list[FeedItemOut] = []

    for item in visible:
        if item.repeat_type is not None:
            # Recurring cards (routines, repeating appointments) land only on
            # their scheduled days and are never "overdue" — a missed one isn't
            # carried forward, the next occurrence simply comes around.
            if _occurs(item, date_for):
                today.append(_build_feed_item(db, item, user, date_for, comps[item.id]))
            continue

        if item.date_for == date_for:
            today.append(_build_feed_item(db, item, user, date_for, comps[item.id]))
        elif item.date_for is None:
            fi = _build_feed_item(db, item, user, date_for, comps[item.id])
            # An undated task finished on an earlier day is archived off the
            # board; finished today it stays put, crossed out, until midnight.
            # A pending mark from an earlier day archives too — the card is
            # out of the kid's hands and lives in the parents' approval queue.
            if (
                not fi.completed
                and not fi.pending
                and any(day != date_for for _, day, _ in comps[item.id])
            ):
                continue
            today.append(fi)
        elif item.date_for < date_for:
            # A one-off whose day has passed carries forward until checked off.
            # Once completed it leaves the board immediately: it wasn't done
            # today, so it doesn't belong in today's Done list — its record
            # lives on its own day in the calendar.
            fi = _build_feed_item(db, item, user, date_for, comps[item.id])
            if fi.completed:
                continue
            overdue.append(fi)
        else:  # date_for in (today, today + 7]
            next7.append(_build_feed_item(db, item, user, date_for, comps[item.id]))

    # All-day events first, then timed cards in day order; untimed sink to the end.
    late = dt.time(23, 59)
    overdue.sort(key=lambda i: (i.date_for, not i.all_day, i.time_of_day or late, i.title.lower()))
    today.sort(key=lambda i: (not i.all_day, i.time_of_day or late, i.title.lower()))
    next7.sort(key=lambda i: (i.date_for, not i.all_day, i.time_of_day or late, i.title.lower()))

    return FeedOut(date=date_for, overdue=overdue, today=today, next7=next7)


@router.get("/pending", response_model=list[PendingApprovalOut])
def pending_approvals(
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Every check-off in the family still waiting on a parent, oldest first —
    the "Waiting on you" list. Deliberately not derived from the feed: a
    pending mark from an earlier day (yesterday's routine, an archived task)
    wouldn't materialize there, but it still needs an answer."""
    rows = db.execute(
        select(Completion, Item, User)
        .join(Item, Completion.item_id == Item.id)
        .join(User, Completion.user_id == User.id)
        .where(Item.family_id == parent.family_id, Completion.pending.is_(True))
        .order_by(Completion.completed_at)
    ).all()
    return [
        PendingApprovalOut(
            item_id=item.id,
            title=item.title,
            kind=item.kind,
            user=kid,
            date_for=completion.date_for,
            completed_at=completion.completed_at,
        )
        for completion, item, kid in rows
    ]


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
    # One completions fetch covers every card on every day of the range.
    comps = _completions_by_item(db, visible)

    late = dt.time(23, 59)
    days: list[CalendarDayOut] = []
    day = start
    while day <= end:
        on_day = [
            _build_feed_item(db, item, user, day, comps[item.id])
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
    return _build_feed_item(db, item, parent, dt.date.today(), [])


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
        # Drop pending marks from members no longer on the card: nobody could
        # ever approve them, and the approval queue must not show ghost rows.
        participant_ids = {a.id for a in item.assignees} or (
            {item.owner_id} if item.owner_id is not None else set()
        )
        pending_rows = db.scalars(
            select(Completion).where(
                Completion.item_id == item.id, Completion.pending.is_(True)
            )
        ).all()
        for row in pending_rows:
            if row.user_id not in participant_ids:
                db.delete(row)
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
    return _build_feed_item(
        db, item, parent, dt.date.today(), _completions_by_item(db, [item])[item.id]
    )


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


def _notify_parents_of_pending(db: Session, item: Item, kid: User, date_for: dt.date) -> None:
    """Tell every parent a kid's check-off is waiting on them. Sent inline
    after the commit — at family scale that's a couple hundred milliseconds,
    and the client's toggle is optimistic so nobody is watching the clock.
    (Not a BackgroundTask: get_db's session would close before it ran.) A
    push failure must never fail the check-off itself."""
    if not push.enabled():
        return
    try:
        first_name = kid.display_name.split()[0]
        payload = {
            "title": f"{first_name} finished: {item.title}",
            "body": "Tap to review and approve",
            "tag": f"approval-{item.id}-{kid.id}-{date_for.isoformat()}",
            "url": "/",
        }
        parents = db.scalars(
            select(User).where(User.family_id == kid.family_id, User.role == Role.parent)
        ).all()
        for parent in parents:
            push.send_to_user(db, parent.id, payload)
    except Exception:
        log.exception("approval push failed (check-off already saved)")


@router.post("/{item_id}/complete", response_model=FeedItemOut)
def complete_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    for_user: int | None = Query(default=None, alias="for"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    _check_complete_date(date_for)
    item = _get_item(db, item_id, user.family_id)
    _require_visible(item, user)
    target = _resolve_completion_target(db, item, user, for_user)

    if item.kind == ItemKind.routine:
        # Per-person: the target member's own occurrence on this day.
        exists = db.scalar(
            select(Completion).where(
                Completion.item_id == item.id,
                Completion.user_id == target.id,
                Completion.date_for == date_for,
            )
        )
    elif item.date_for is not None:
        # A dated card is a one-shot: any single completion means done, whatever
        # day it was marked. The calendar records the real day; the board's
        # overdue-clear records today. Either way, don't add a second row.
        exists = db.scalar(select(Completion).where(Completion.item_id == item.id))
    else:
        # Undated task: per-day, so it can archive the day after it's checked.
        exists = db.scalar(
            select(Completion).where(
                Completion.item_id == item.id, Completion.date_for == date_for
            )
        )

    if exists is None:
        # A minor's own tap starts pending until a parent makes it official; a
        # parent's tap (their own card or ?for=<kid>) is official on the spot.
        row = Completion(
            item_id=item.id, user_id=target.id, date_for=date_for, pending=user.is_minor
        )
        db.add(row)
        db.commit()
        if row.pending:
            _notify_parents_of_pending(db, item, user, date_for)
    elif exists.pending and user.role == Role.parent:
        # Approval: promote the kid's pending row in place (never a second row,
        # so the (item, member, day) uniqueness keeps holding) and remember who
        # made it official.
        exists.pending = False
        exists.approved_by_id = user.id
        db.commit()

    return _build_feed_item(
        db, item, user, date_for, _completions_by_item(db, [item])[item.id]
    )


@router.delete("/{item_id}/complete", response_model=FeedItemOut)
def uncomplete_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    for_user: int | None = Query(default=None, alias="for"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Undo a check-off. For a routine or an undated task this clears that one
    day; for a dated one-shot it clears the single completion whatever day it
    landed on, so undoing from the calendar's real day and from the board's
    overdue-clear (recorded today) both work."""
    _check_complete_date(date_for)
    item = _get_item(db, item_id, user.family_id)
    _require_visible(item, user)
    target = _resolve_completion_target(db, item, user, for_user)

    if item.kind == ItemKind.routine:
        stmt = select(Completion).where(
            Completion.item_id == item.id,
            Completion.user_id == target.id,
            Completion.date_for == date_for,
        )
    elif item.date_for is not None:
        stmt = select(Completion).where(Completion.item_id == item.id)
    else:
        stmt = select(Completion).where(
            Completion.item_id == item.id, Completion.date_for == date_for
        )
    completions = db.scalars(stmt).all()
    if user.is_minor:
        # A minor may only withdraw their own still-pending mark. Approved
        # rows are a parent's word now — un-ticking them is not theirs to do.
        completions = [c for c in completions if c.pending and c.user_id == user.id]
    for completion in completions:
        db.delete(completion)
    if completions:
        db.commit()

    return _build_feed_item(
        db, item, user, date_for, _completions_by_item(db, [item])[item.id]
    )
