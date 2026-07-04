import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import require_family, require_parent
from app.models import Completion, Item, ItemKind, Role, User
from app.schemas import FeedItemOut, FeedOut, ItemIn, ItemUpdate

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


def _resolve_assignees(db: Session, ids: list[int], family_id: int) -> list[User]:
    """Validate that every id is a member of this family and return the User
    rows. Duplicates are collapsed; an empty list means the whole family."""
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


def _streak(db: Session, item: Item, date_for: dt.date) -> int:
    """Consecutive days a routine was completed, counting back from date_for.

    An unfinished today doesn't break the chain: if the routine was done
    yesterday but not yet today, the streak from yesterday still shows.
    """
    dates = set(
        db.scalars(
            select(Completion.date_for)
            .where(Completion.item_id == item.id)
            .order_by(Completion.date_for.desc())
            .limit(400)
        )
    )
    day = date_for if date_for in dates else date_for - dt.timedelta(days=1)
    streak = 0
    while day in dates:
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


def _feed_item(item: Item, completed: bool, streak: int | None) -> FeedItemOut:
    return FeedItemOut(
        id=item.id,
        kind=item.kind,
        title=item.title,
        notes=item.notes,
        assignees=item.assignees,
        time_of_day=item.time_of_day,
        date_for=item.date_for,
        completed=completed,
        streak=streak,
    )


@router.get("/feed", response_model=FeedOut)
def feed(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """The whole home screen in one request: today, anytime, upcoming.

    Upcoming has no horizon: a card scheduled weeks out stays visible on the
    board rather than silently waiting inside a seven-day window.
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

    # One query for every completion that could matter today, keyed by item.
    done_today = set(
        db.scalars(select(Completion.item_id).where(Completion.date_for == date_for))
    )
    # An undated todo finished on some EARLIER day is archived off the board;
    # finished today it stays put, crossed out, until the day rolls over.
    done_before = set(
        db.scalars(
            select(Completion.item_id).where(
                Completion.item_id.in_([i.id for i in items if i.date_for is None]),
                Completion.date_for != date_for,
            )
        )
    )

    today: list[FeedItemOut] = []
    anytime: list[FeedItemOut] = []
    upcoming: list[FeedItemOut] = []

    for item in items:
        if item.kind == ItemKind.routine:
            streak = _streak(db, item, date_for)
            today.append(_feed_item(item, item.id in done_today, streak))
        elif item.date_for == date_for:
            today.append(_feed_item(item, item.id in done_today, None))
        elif item.date_for is None:
            if item.id not in done_before:
                anytime.append(_feed_item(item, item.id in done_today, None))
        elif item.date_for > date_for:
            upcoming.append(_feed_item(item, False, None))

    # Timed cards in day order; untimed ones sink to the end of the day.
    late = dt.time(23, 59)
    today.sort(key=lambda i: (i.time_of_day or late, i.title.lower()))
    anytime.sort(key=lambda i: (i.completed, i.title.lower()))  # done sink to the bottom
    upcoming.sort(key=lambda i: (i.date_for, i.time_of_day or late, i.title.lower()))

    return FeedOut(date=date_for, today=today, anytime=anytime, upcoming=upcoming)


@router.post("", response_model=FeedItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    data: ItemIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Parents put cards on their family's board."""
    assignees = _resolve_assignees(db, data.assignee_ids, parent.family_id)
    if data.kind == ItemKind.routine and data.date_for is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Routines repeat daily; no date")

    item = Item(
        family_id=parent.family_id,
        kind=data.kind,
        title=data.title,
        notes=data.notes,
        assignees=assignees,
        time_of_day=data.time_of_day,
        date_for=data.date_for,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _feed_item(item, completed=False, streak=0 if item.kind == ItemKind.routine else None)


@router.patch("/{item_id}", response_model=FeedItemOut)
def update_item(
    item_id: int,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id, parent.family_id)
    fields = data.model_fields_set  # only touch keys the client actually sent

    if "assignee_ids" in fields:
        item.assignees = _resolve_assignees(db, data.assignee_ids or [], parent.family_id)
    if "title" in fields and data.title is not None:
        item.title = data.title
    if "notes" in fields and data.notes is not None:
        item.notes = data.notes
    if "time_of_day" in fields:
        item.time_of_day = data.time_of_day
    if "date_for" in fields:
        if item.kind == ItemKind.routine and data.date_for is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Routines repeat daily; no date")
        item.date_for = data.date_for

    db.commit()
    db.refresh(item)
    done_today = db.scalar(
        select(Completion.id).where(
            Completion.item_id == item.id, Completion.date_for == dt.date.today()
        )
    )
    streak = _streak(db, item, dt.date.today()) if item.kind == ItemKind.routine else None
    return _feed_item(item, completed=done_today is not None, streak=streak)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id, parent.family_id)
    db.delete(item)  # completions cascade away with it
    db.commit()


def _can_check(item: Item, user: User) -> bool:
    """Parents can check anything. Children only their own or family cards."""
    if user.role == Role.parent:
        return True
    return not item.assignees or any(a.id == user.id for a in item.assignees)


@router.post("/{item_id}/complete", response_model=FeedItemOut)
def complete_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    _check_date(date_for)
    item = _get_item(db, item_id, user.family_id)
    if not _can_check(item, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This card is someone else's")

    exists = db.scalar(
        select(Completion.id).where(
            Completion.item_id == item.id, Completion.date_for == date_for
        )
    )
    if exists is None:
        db.add(Completion(item_id=item.id, user_id=user.id, date_for=date_for))
        db.commit()

    streak = _streak(db, item, date_for) if item.kind == ItemKind.routine else None
    return _feed_item(item, completed=True, streak=streak)


@router.delete("/{item_id}/complete", response_model=FeedItemOut)
def uncomplete_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Undo an accidental check-off for that day."""
    _check_date(date_for)
    item = _get_item(db, item_id, user.family_id)
    if not _can_check(item, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This card is someone else's")

    completion = db.scalar(
        select(Completion).where(
            Completion.item_id == item.id, Completion.date_for == date_for
        )
    )
    if completion is not None:
        db.delete(completion)
        db.commit()

    streak = _streak(db, item, date_for) if item.kind == ItemKind.routine else None
    return _feed_item(item, completed=False, streak=streak)
