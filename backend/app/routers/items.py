import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import crumbs, inbox, push, recurrence, village_events
from app.clock import family_now, shift_schedule
from app.db import get_db
from app.deps import require_family, require_parent
from app.models import (
    Completion,
    Family,
    Item,
    ItemKind,
    ReminderLog,
    RepeatType,
    Role,
    User,
    VillageEvent,
    Visibility,
)
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


def _require_unmanaged(item: Item) -> None:
    """A materialized village-event copy is the ORGANIZER's to edit, cancel,
    remove, AND check off; the attendee family's way out is changing their
    RSVP. The host's own done/cancel marks mirror down onto the copies."""
    if item.village_event_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Managed by the organizer")


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
    if item.workout_auto_complete and item.kind != ItemKind.routine:
        _bad("Only routines can complete themselves from a workout")
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
    cancelled: bool = False,
    village_shared: bool = False,
) -> FeedItemOut:
    return FeedItemOut(
        id=item.id,
        village_shared=village_shared or item.village_event_id is not None,
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
        location=item.location,
        village_event_id=item.village_event_id,
        repeat=_repeat_out(item),
        workout_auto_complete=item.workout_auto_complete,
        completed=completed,
        streak=streak,
        pending=pending,
        pending_by=pending_by,
        cancelled=cancelled,
        assignee_completions=assignee_completions,
    )


# One item's completion rows, prefetched:
# (user_id, date_for, pending, cancelled) quadruples.
# A pending row is a minor's tap awaiting a parent — it must never read as done.
CompletionRows = list[tuple[int | None, dt.date, bool, bool]]


def _completions_by_item(db: Session, items: list[Item]) -> dict[int, CompletionRows]:
    """Every completion for these items in ONE query, keyed by item id.

    The feed and calendar assemble many cards at once — and the calendar
    assembles each card once per day it appears. Querying completions inside
    that loop turned one month-view request into hundreds of little selects;
    a single IN(...) fetch scales with the data instead of with the view.
    """
    rows: dict[int, CompletionRows] = {item.id: [] for item in items}
    if rows:
        for item_id, uid, day, pending, cancelled in db.execute(
            select(
                Completion.item_id,
                Completion.user_id,
                Completion.date_for,
                Completion.pending,
                Completion.cancelled,
            ).where(Completion.item_id.in_(rows))
        ):
            rows[item_id].append((uid, day, pending, cancelled))
    return rows


def _village_shared_ids(db: Session, items: list[Item]) -> set[int]:
    """Which of these items are offered to a village, in ONE query — the
    source of the board's gold SHARED flag (copies flag themselves via
    village_event_id)."""
    ids = [i.id for i in items if i.kind in (ItemKind.activity, ItemKind.appointment)]
    if not ids:
        return set()
    return set(db.scalars(select(VillageEvent.item_id).where(VillageEvent.item_id.in_(ids))))


def _build_feed_item(
    db: Session,
    item: Item,
    user: User,
    date: dt.date,
    completions: CompletionRows,
    village_shared: bool | None = None,
) -> FeedItemOut:
    """Assemble one card's completion state for the requesting member, from
    the item's prefetched completion rows (see _completions_by_item).

    Routines are per-person: each participant gets their own completed/streak,
    and the requesting member's own state (or, if they're not a participant,
    whether every participant is done) becomes the card's headline state.
    Other kinds carry a single shared check.

    village_shared marks the card for the gold SHARED flag: copies carry it
    on the row itself; an organizer's source needs a VillageEvent lookup —
    the feed/calendar pass a batched answer, single-card responses let the
    None default pay one small query.
    """
    if village_shared is None:
        village_shared = item.village_event_id is not None or (
            item.kind in (ItemKind.activity, ItemKind.appointment)
            and db.scalar(select(VillageEvent.id).where(VillageEvent.item_id == item.id))
            is not None
        )
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
            done = any(not pend and not canc for _, _, pend, canc in completions)
            called_off = any(canc for _, _, _, canc in completions)
            waiting = next((uid for uid, _, pend, canc in completions if pend and not canc), None)
        else:
            done = any(
                day == date and not pend and not canc for _, day, pend, canc in completions
            )
            called_off = any(day == date and canc for _, day, _, canc in completions)
            waiting = next(
                (
                    uid
                    for uid, day, pend, canc in completions
                    if pend and not canc and day == date
                ),
                None,
            )
        return _feed_item(
            item,
            completed=done,
            streak=None,
            assignee_completions=None,
            pending=not done and not called_off and waiting is not None,
            pending_by=waiting if not done and not called_off else None,
            cancelled=called_off,
            village_shared=village_shared,
        )

    participants = _routine_participants(db, item)
    dates_by_user: dict[int, set[dt.date]] = {}
    pending_by_user: dict[int, set[dt.date]] = {}
    for uid, day, pend, _canc in completions:  # routines are never cancelled
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
        village_shared=village_shared,
    )


def _completed_on(completions: CompletionRows, date: dt.date) -> bool:
    """Whether a valid completion landed on this exact day. Same validity rule
    _build_feed_item uses for a dated card's `done` (non-pending, non-cancelled),
    but day-specific: a mirrored village copy's user_id=None row counts like any
    other, and a kid's pending tap never does."""
    return any(day == date and not pend and not canc for _, day, pend, canc in completions)


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
    shared = _village_shared_ids(db, visible)

    overdue: list[FeedItemOut] = []
    today: list[FeedItemOut] = []
    next7: list[FeedItemOut] = []

    for item in visible:
        if item.repeat_type is not None:
            # Recurring cards (routines, repeating appointments) land only on
            # their scheduled days and are never "overdue" — a missed one isn't
            # carried forward, the next occurrence simply comes around.
            if _occurs(item, date_for):
                today.append(_build_feed_item(db, item, user, date_for, comps[item.id], item.id in shared))
            continue

        if item.date_for == date_for:
            fi = _build_feed_item(db, item, user, date_for, comps[item.id], item.id in shared)
            # Its due day has arrived. A card checked off ahead of time already
            # had its day in Done on the day it was ticked, so it doesn't come
            # back now; one done on its own day stays put, crossed out, today.
            if fi.completed and not _completed_on(comps[item.id], date_for):
                continue
            today.append(fi)
        elif item.date_for is None:
            fi = _build_feed_item(db, item, user, date_for, comps[item.id], item.id in shared)
            # An undated task finished on an earlier day is archived off the
            # board; finished today it stays put, crossed out, until midnight.
            # A pending mark from an earlier day archives too — the card is
            # out of the kid's hands and lives in the parents' approval queue.
            if (
                not fi.completed
                and not fi.pending
                and any(day != date_for for _, day, _, _ in comps[item.id])
            ):
                continue
            today.append(fi)
        elif item.date_for < date_for:
            # A one-off whose day has passed carries forward until checked off.
            # Once completed it leaves the board immediately: it wasn't done
            # today, so it doesn't belong in today's Done list — its record
            # lives on its own day in the calendar.
            fi = _build_feed_item(db, item, user, date_for, comps[item.id], item.id in shared)
            if fi.completed:
                continue
            overdue.append(fi)
        else:  # date_for in (today, today + 7]
            fi = _build_feed_item(db, item, user, date_for, comps[item.id], item.id in shared)
            # A future one-off ticked off ahead of schedule belongs in Done only
            # on the day it was ticked (today's Done pulls from next7). Any other
            # day it reads completed, it has left the board and stays gone.
            if fi.completed and not _completed_on(comps[item.id], date_for):
                continue
            next7.append(fi)

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
    shared = _village_shared_ids(db, visible)

    late = dt.time(23, 59)
    days: list[CalendarDayOut] = []
    day = start
    while day <= end:
        on_day = [
            _build_feed_item(db, item, user, day, comps[item.id], item.id in shared)
            for item in visible
            if (_occurs(item, day) if item.repeat_type is not None else item.date_for == day)
        ]
        on_day.sort(key=lambda i: (not i.all_day, i.time_of_day or late, i.title.lower()))
        days.append(CalendarDayOut(date=day, items=on_day))
        day += dt.timedelta(days=1)

    return CalendarOut(start=start, end=end, days=days)


def _server_now() -> dt.datetime:
    """The server's wall clock — an indirection so tests can pin it."""
    return dt.datetime.now()


def _claim_past_start(db: Session, item: Item) -> None:
    """The member just set this time themselves; catch-up is for reminders
    lost to downtime, not edits into the past. A dated one-shot created (or
    rescheduled) onto a start already behind its family's clock pre-claims its
    ReminderLog slot, so the tick's catch-up window finds nothing to fire.
    Repeating cards are out of scope: their claims are per-occurrence day.
    Runs after the endpoint's own commit; a racing tick that claimed first is
    the same outcome, so the collision is swallowed like _already_reminded."""
    if item.repeat_type is not None or item.date_for is None or item.time_of_day is None:
        return
    tz = db.scalar(select(Family.timezone).where(Family.id == item.family_id))
    local = family_now(_server_now(), tz)
    if item.date_for != local.date() or item.time_of_day > local.time():
        return
    db.add(ReminderLog(item_id=item.id, date_for=item.date_for))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


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
        workout_auto_complete=data.workout_auto_complete,
        location=data.location,
    )
    _validate_item(item)
    db.add(item)
    db.commit()
    db.refresh(item)
    _claim_past_start(db, item)
    _push_board_change(
        db,
        _board_change_recipients(db, item, parent),
        parent.display_name.split()[0],
        "scheduled" if item.kind == ItemKind.appointment else "added",
        item.kind,
        item.title,
        _schedule_text(item),
    )
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
    _require_unmanaged(item)
    fields = data.model_fields_set  # only touch keys the client actually sent
    before_schedule = tuple(getattr(item, f) for f in _SCHEDULE_FIELDS)
    before_location = item.location
    before_title = item.title
    before_notes = item.notes

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
    if "workout_auto_complete" in fields and data.workout_auto_complete is not None:
        item.workout_auto_complete = data.workout_auto_complete
    if "location" in fields:
        item.location = data.location
    if "shared_to_feed" in fields and data.shared_to_feed is not None:
        item.shared_to_feed = data.shared_to_feed

    _validate_item(item)
    # A card offered to a village must stay a shareable shape (dated,
    # non-repeating): every member family's list and board copies depend on
    # that date. Reshaping it is a 400 until it's unshared.
    if (item.repeat_type is not None or item.date_for is None) and village_events.events_on(
        db, item
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Unshare it from the village first"
        )
    rescheduled = tuple(getattr(item, f) for f in _SCHEDULE_FIELDS) != before_schedule
    if rescheduled:
        # A rescheduled card reminds afresh on its new schedule. Its old
        # ReminderLog claims must go: yesterday's heads-up row, or a past-due
        # nudge holding (item, day+1), would silently swallow the new day's
        # reminder — an overdue card moved to tomorrow is exactly that case.
        db.execute(delete(ReminderLog).where(ReminderLog.item_id == item.id))
    db.commit()
    db.refresh(item)
    first = parent.display_name.split()[0]
    if rescheduled:
        # The old ReminderLog rows were cleared above so the NEW schedule
        # reminds afresh — unless that schedule is already in the past, in
        # which case the slot is re-claimed on the spot.
        _claim_past_start(db, item)
        _push_board_change(
            db,
            _board_change_recipients(db, item, parent),
            first,
            "rescheduled",
            item.kind,
            item.title,
            f"Now {_schedule_text(item)}",
        )
    # A content-only edit writes ONE Inbox line and never rings (title, notes,
    # and location tweaks are quiet on the phone by design). The elif chain is
    # deliberate: a reschedule already spoke, so never a second line. Cut on
    # purpose: assignee, visibility, and shared_to_feed changes stay silent.
    elif "title" in fields and item.title != before_title:
        inbox.record_all(
            db, _board_change_recipients(db, item, parent), "board",
            f"{first} edited {_KIND_PHRASE[item.kind]}: {item.title}",
            f'Was "{before_title}"',
        )
    elif "notes" in fields and item.notes != before_notes:
        inbox.record_all(
            db, _board_change_recipients(db, item, parent), "board",
            f"{first} edited {_KIND_PHRASE[item.kind]}: {item.title}",
            "Notes updated",
        )
    elif "location" in fields and item.location != before_location:
        inbox.record_all(
            db, _board_change_recipients(db, item, parent), "board",
            f"{first} edited {_KIND_PHRASE[item.kind]}: {item.title}",
            f"Location: {item.location}" if item.location else "Location removed",
        )
    # A shared source card drags its village copies along: every copy is
    # rewritten from the source (schedules reconverted onto each family's
    # clock), and the going families hear about it only when the WHEN or
    # WHERE moved — a typo fix in the title syncs silently.
    try:
        recipients = village_events.sync_copies(db, item, rescheduled)
        if recipients:
            db.commit()
            if rescheduled or ("location" in fields and item.location != before_location):
                _notify_event_change(
                    db, recipients, item,
                    f"Updated: {item.title}",
                    _event_notify_bodies(db, item, recipients),
                )
    except Exception:
        db.rollback()
        log.exception("village copy sync failed (the edit itself is saved)")
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
    _require_unmanaged(item)
    title, kind = item.title, item.kind
    recipients = _board_change_recipients(db, item, parent)
    # A shared source takes its village events and every family's copy with
    # it. Collect the going families first — the rows are gone after commit.
    events = village_events.events_on(db, item)
    going = village_events.going_adults(db, [e.id for e in events]) if events else []
    if events:
        village_events.delete_copies(db, [e.id for e in events])
    db.delete(item)  # completions cascade away with it; village_events rows too
    db.commit()
    _push_board_change(db, recipients, parent.display_name.split()[0], "removed", kind, title)
    if going:
        _notify_event_change(db, going, item, f"Called off: {title}", "The organizer removed it")


# ---- cancelling (appointments and activities) -----------------------------------

_CANCELLABLE = {ItemKind.appointment, ItemKind.activity}


def _cancel_slot(item: Item, date_for: dt.date):
    """The completion slot a cancellation occupies: the single one-shot row
    for a dated card, the day's row for a repeating one."""
    stmt = select(Completion).where(Completion.item_id == item.id)
    if item.date_for is None:
        stmt = stmt.where(Completion.date_for == date_for)
    return stmt


@router.post("/{item_id}/cancel", response_model=FeedItemOut)
def cancel_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Call an appointment or activity off: resolved (no reminders, no
    digest), but shown as cancelled rather than done. Parents only — calling
    off the dentist is a parent's move. Repeating cards cancel one occurrence."""
    _check_complete_date(date_for)
    item = _get_item(db, item_id, parent.family_id)
    _require_visible(item, parent)
    _require_unmanaged(item)
    if item.kind not in _CANCELLABLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only appointments and activities can be cancelled"
        )
    for row in db.scalars(_cancel_slot(item, date_for)):
        db.delete(row)  # a cancellation replaces any done/pending mark
    db.flush()  # the deletes must land before the new row reuses the slot
    db.add(
        Completion(
            item_id=item.id, user_id=parent.id, date_for=date_for, cancelled=True
        )
    )
    db.commit()
    _mirror_called_off(db, item, cancelled=True)
    _push_board_change(
        db,
        _board_change_recipients(db, item, parent),
        parent.display_name.split()[0],
        "cancelled",
        item.kind,
        item.title,
    )
    return _build_feed_item(
        db, item, parent, date_for, _completions_by_item(db, [item])[item.id]
    )


@router.delete("/{item_id}/cancel", response_model=FeedItemOut)
def uncancel_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """It's back on: remove the cancellation mark."""
    _check_complete_date(date_for)
    item = _get_item(db, item_id, parent.family_id)
    _require_visible(item, parent)
    _require_unmanaged(item)
    rows = [r for r in db.scalars(_cancel_slot(item, date_for)) if r.cancelled]
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
        _mirror_called_off(db, item, cancelled=False)
        inbox.record_all(
            db, _board_change_recipients(db, item, parent), "board",
            f"{parent.display_name.split()[0]} put back on: {item.title}",
        )
    return _build_feed_item(
        db, item, parent, date_for, _completions_by_item(db, [item])[item.id]
    )


# ---- board-change notifications ---------------------------------------------------

# When a member adds, reschedules, or removes a card, the family members who
# can see it hear about it once — ONE push per action, never one per
# occurrence of a repeating card.

_SCHEDULE_FIELDS = (
    "date_for",
    "time_of_day",
    "end_time",
    "all_day",
    "repeat_type",
    "repeat_days",
    "repeat_interval",
    "repeat_month_day",
)


def _schedule_text(item: Item) -> str:
    if item.repeat_type is not None:
        base = "Repeats " + ("weekly" if item.repeat_type == RepeatType.weekly else "monthly")
    elif item.date_for is not None:
        base = item.date_for.strftime("%a %b %-d")
    else:
        base = "Anytime"
    if item.all_day:
        return f"{base} · all day"
    if item.time_of_day is not None:
        clock = item.time_of_day.strftime("%-I:%M %p")
        if item.end_time is not None:
            clock += " – " + item.end_time.strftime("%-I:%M %p")
        return f"{base} · {clock}"
    return base


def _schedule_text_on(item: Item, from_tz: str | None, to_tz: str | None) -> str:
    """_schedule_text rendered on a recipient family's wall clock. A shared
    village event fans out to families that may keep different timezones, so the
    WHEN each family reads must be its own; the organizer's is only one of them.
    Same-tz recipients (equal names, both NULL included) shift to a byte-
    identical string. Repeats and dateless cards carry no instant to convert and
    format unchanged."""
    date_for, start, end = item.date_for, item.time_of_day, item.end_time
    if item.repeat_type is None and date_for is not None:
        date_for, start, end = shift_schedule(
            date_for, start, end, item.all_day, from_tz, to_tz
        )
    if item.repeat_type is not None:
        base = "Repeats " + ("weekly" if item.repeat_type == RepeatType.weekly else "monthly")
    elif date_for is not None:
        base = date_for.strftime("%a %b %-d")
    else:
        base = "Anytime"
    if item.all_day:
        return f"{base} · all day"
    if start is not None:
        clock = start.strftime("%-I:%M %p")
        if end is not None:
            clock += " – " + end.strftime("%-I:%M %p")
        return f"{base} · {clock}"
    return base


def _event_notify_bodies(
    db: Session, item: Item, recipients: list[User], *, with_location: bool = True
) -> dict[int, str]:
    """Per-family notification bodies for a shared event: the schedule on each
    recipient family's own clock plus the (unshifting) location when present,
    keyed by family_id. One query covers the organizer and recipient families,
    no per-user lookup. Same-tz families read text byte-identical to a single
    _schedule_text body."""
    fam_ids = {r.family_id for r in recipients} | {item.family_id}
    tz_by_family = dict(
        db.execute(select(Family.id, Family.timezone).where(Family.id.in_(fam_ids))).all()
    )
    organizer_tz = tz_by_family.get(item.family_id)
    suffix = f" · {item.location}" if (with_location and item.location) else ""
    return {
        r.family_id: _schedule_text_on(item, organizer_tz, tz_by_family.get(r.family_id))
        + suffix
        for r in recipients
    }


def _board_change_recipients(db: Session, item: Item, actor: User) -> list[User]:
    """Adults who can see the card, minus whoever made the change. Push
    config and prefs deliberately don't filter here — the same audience gets
    the Inbox line whether or not anything rings their phone."""
    from app.push import _recipients

    return [p for p in _recipients(db, item) if not p.is_minor and p.id != actor.id]


# How each kind reads in a sentence: "Alex added a task: Take out the trash".
_KIND_PHRASE = {
    ItemKind.task: "a task",
    ItemKind.activity: "an activity",
    ItemKind.appointment: "an appointment",
    ItemKind.routine: "a routine",
}


def _push_board_change(
    db: Session,
    recipients: list[User],
    actor_first: str,
    verb: str,
    kind: ItemKind,
    title: str,
    body: str = "",
) -> None:
    """One family push per board action, phrased like a person: the verb, the
    kind, and the card's name right in the title. Each recipient gets an Inbox
    line first, recorded and committed before the push leg so a push failure
    never loses the history — routines included. Routines never PUSH here,
    though: they're the board's daily heartbeat, not news (kid routines still
    reach parents through Kid Tasks)."""
    if not recipients:
        return
    payload = {
        "title": f"{actor_first} {verb} {_KIND_PHRASE[kind]}: {title}",
        "body": body,
        "tag": f"board-change-{title[:40]}",
        "url": "/",
    }
    try:
        for r in recipients:
            inbox.record(db, r.id, r.family_id, "board", payload["title"], payload["body"])
        db.commit()
    except Exception:
        db.rollback()
        log.exception("board-change inbox write failed (the change itself is saved)")
    if kind == ItemKind.routine or not push.enabled():
        return
    try:
        for r in recipients:
            if push.wants(r, "family"):
                push.send_to_user(db, r.id, payload)
    except Exception:
        log.exception("board-change push failed (the change itself is saved)")


def _notify_parents_of_pending(db: Session, item: Item, kid: User, date_for: dt.date) -> None:
    """Tell every parent a kid's check-off is waiting on them. Sent inline
    after the commit — at family scale that's a couple hundred milliseconds,
    and the client's toggle is optimistic so nobody is watching the clock.
    (Not a BackgroundTask: get_db's session would close before it ran.) A
    push failure must never fail the check-off itself."""
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
    try:
        for parent in parents:
            inbox.record(
                db, parent.id, parent.family_id, "pending",
                payload["title"], "Waiting on your approval",
            )
        db.commit()
    except Exception:
        db.rollback()
        log.exception("approval inbox write failed (check-off already saved)")
    if not push.enabled():
        return
    try:
        for parent in parents:
            if push.wants(parent, "approvals"):
                push.send_to_user(db, parent.id, payload)
    except Exception:
        log.exception("approval push failed (check-off already saved)")


def _mirror_called_off(db: Session, src: Item, cancelled: bool) -> None:
    """A shared source's cancel/uncancel echoes onto every going family's
    copy: the strikethrough is the app's own language for "called off", and a
    silently vanishing card would read like the invite never happened. The
    mirrored mark carries user_id=None — the organizer's id must never cross
    the family wall. Runs after the source's own commit; never 500s it."""
    try:
        events = village_events.events_on(db, src)
        if not events:
            return
        copies = village_events.copies_of(db, [e.id for e in events])
        for copy in copies:
            # Cancel replaces any done mark (the source-side semantics);
            # uncancel removes only the mirrored strikethrough.
            existing = [
                r
                for r in db.scalars(
                    select(Completion).where(Completion.item_id == copy.id)
                )
                if cancelled or r.cancelled
            ]
            for row in existing:
                db.delete(row)
            if cancelled:
                db.flush()
                db.add(
                    Completion(
                        item_id=copy.id,
                        user_id=None,
                        date_for=copy.date_for or src.date_for,
                        cancelled=True,
                    )
                )
        db.commit()
        recipients = village_events.going_adults(db, [e.id for e in events])
        _notify_event_change(
            db, recipients, src,
            (f"Called off: {src.title}" if cancelled else f"Back on: {src.title}"),
            _event_notify_bodies(db, src, recipients, with_location=False),
        )
    except Exception:
        db.rollback()
        log.exception("village cancel mirror failed (the change itself is saved)")


def _notify_event_change(
    db: Session, recipients: list, item: Item, title: str, body: str | dict[int, str] = ""
) -> None:
    """The going families hear a shared event moved, was called off, or is
    back on. Inbox always; push behind the "village" pref. A dict body carries
    per-family text (each family's own wall clock); a str is the same for all."""

    def _body(r) -> str:
        return body if isinstance(body, str) else body.get(r.family_id, "")

    try:
        for r in recipients:
            inbox.record(db, r.id, r.family_id, "village", title, _body(r))
        db.commit()
    except Exception:
        db.rollback()
        log.exception("village-change inbox write failed (the change is saved)")
    if not push.enabled():
        return
    try:
        for r in recipients:
            if push.wants(r, "village"):
                payload = {
                    "title": title, "body": _body(r),
                    "tag": f"village-item-{item.id}", "url": "/",
                }
                push.send_to_user(db, r.id, payload)
    except Exception:
        log.exception("village-change push failed (the change is saved)")


def _mirror_done_to_copies(db: Session, src: Item, done: bool) -> None:
    """After the organizer marks a shared source done (or undoes it), echo the
    mark onto every going family's copy. Runs after the completion's own commit;
    a failure here never fails the member's own action. A no-op for unshared
    cards and for copies (which 403 before they get here)."""
    try:
        village_events.mirror_done(db, src, done)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("village done-mirror failed (the completion itself is saved)")


def _record_kid_payoff(
    db: Session, kid: User, parent: User, verb: str, title: str, awarded: int
) -> None:
    """The kid-facing Inbox line for an official completion: who made it
    official, which card, and the crumb if one was paid. Committed on its own
    so a failure here never fails the completion."""
    try:
        inbox.record(
            db,
            kid.id,
            kid.family_id,
            "approved",
            f"{parent.display_name.split()[0]} {verb}: {title}",
            f"+{awarded} crumb" if awarded else "",
        )
        db.commit()
    except Exception:
        db.rollback()
        log.exception("payoff inbox write failed (completion already saved)")


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
    # A materialized copy is the organizer's to complete; the attendee family
    # can't check it off. The host's mark mirrors down to them instead.
    _require_unmanaged(item)
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

    if exists is not None and exists.cancelled:
        # A called-off occurrence can't be done. Putting it back on
        # (DELETE /cancel) is the only move from here.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "It's been called off. Put it back on first"
        )

    awarded = 0
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
        else:
            # The crumb belongs to whoever DID the thing (the target), and
            # only once it's official — a pending kid tap earns on approval.
            awarded = crumbs.award_completion(db, target, item.id, date_for)
            if awarded > 0:
                # awarded > 0 only happens when a parent checked off FOR a
                # kid; the kid's Inbox should still show their earn.
                _record_kid_payoff(db, target, user, "checked off", item.title, awarded)
            # The family hears about it in the DOER's name; whoever tapped is
            # the one excluded from hearing their own news.
            _push_board_change(
                db,
                _board_change_recipients(db, item, user),
                target.display_name.split()[0],
                "completed",
                item.kind,
                item.title,
            )
    elif exists.pending and user.role == Role.parent:
        # Approval: promote the kid's pending row in place (never a second row,
        # so the (item, member, day) uniqueness keeps holding) and remember who
        # made it official.
        exists.pending = False
        exists.approved_by_id = user.id
        db.commit()
        doer = db.get(User, exists.user_id)
        if doer is not None:
            awarded = crumbs.award_completion(db, doer, item.id, exists.date_for)
            # The payoff moment: the kid hears the approval by name even when
            # the daily cap zeroes the crumb — being seen IS the reward.
            _record_kid_payoff(db, doer, user, "approved", item.title, awarded)
            # A routine approval writes no board line: the parents already got
            # the "pending" line, the kid gets "approved". Only non-routine
            # kid cards announce the completion to the other parent.
            if item.kind != ItemKind.routine:
                _push_board_change(
                    db,
                    _board_change_recipients(db, item, user),
                    doer.display_name.split()[0],
                    "completed",
                    item.kind,
                    item.title,
                )

    out = _build_feed_item(
        db, item, user, date_for, _completions_by_item(db, [item])[item.id]
    )
    out.crumbs_awarded = awarded
    # A shared source drags its copies to match its REAL done state: a parent's
    # tap (or an approval) marks them; a kid's still-pending tap is not done yet,
    # so nothing mirrors until a parent makes it official.
    _mirror_done_to_copies(db, item, done=out.completed)
    return out


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
    _require_unmanaged(item)  # copies clear only when the host uncompletes
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
        first = user.display_name.split()[0]
        if user.is_minor:
            # A kid withdrawing their own pending check-off: every parent hears,
            # the same audience the pending notice went to.
            parents = db.scalars(
                select(User).where(
                    User.family_id == user.family_id, User.role == Role.parent
                )
            ).all()
            inbox.record_all(
                db, list(parents), "board",
                f"{first} withdrew their check-off: {item.title}",
            )
        else:
            inbox.record_all(
                db, _board_change_recipients(db, item, user), "board",
                f"{first} unchecked {_KIND_PHRASE[item.kind]}: {item.title}",
            )

    out = _build_feed_item(
        db, item, user, date_for, _completions_by_item(db, [item])[item.id]
    )
    # Mirror the source's resulting state onto copies: a real uncheck clears
    # them, but a minor's no-op uncheck of an approved row leaves them done.
    _mirror_done_to_copies(db, item, done=out.completed)
    return out
