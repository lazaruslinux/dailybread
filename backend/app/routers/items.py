import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user, require_parent
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


def _get_item(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item")
    return item


def _check_assignee(db: Session, assignee_id: int | None) -> None:
    if assignee_id is not None and db.get(User, assignee_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee does not exist")


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
        assignee=item.assignee,
        time_of_day=item.time_of_day,
        date_for=item.date_for,
        completed=completed,
        streak=streak,
    )


@router.get("/feed", response_model=FeedOut)
def feed(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """The whole home screen in one request: today, anytime, upcoming."""
    _check_date(date_for)
    horizon = date_for + dt.timedelta(days=7)

    items = (
        db.scalars(
            select(Item)
            .options(selectinload(Item.assignee))
            .where(
                (Item.date_for.is_(None)) | (Item.date_for.between(date_for, horizon))
            )
        )
        .unique()
        .all()
    )

    # One query for every completion that could matter today, keyed by item.
    done_today = set(
        db.scalars(select(Completion.item_id).where(Completion.date_for == date_for))
    )
    # Undated todos are "done" once they have a completion on ANY day.
    done_ever = set(
        db.scalars(
            select(Completion.item_id).where(
                Completion.item_id.in_([i.id for i in items if i.date_for is None])
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
            # Undated todo: show until checked, then drop off the board.
            if item.id not in done_ever:
                anytime.append(_feed_item(item, False, None))
        elif item.date_for > date_for:
            upcoming.append(_feed_item(item, False, None))

    # Timed cards in day order; untimed ones sink to the end of the day.
    late = dt.time(23, 59)
    today.sort(key=lambda i: (i.time_of_day or late, i.title.lower()))
    anytime.sort(key=lambda i: i.title.lower())
    upcoming.sort(key=lambda i: (i.date_for, i.time_of_day or late, i.title.lower()))

    return FeedOut(date=date_for, today=today, anytime=anytime, upcoming=upcoming)


@router.post("", response_model=FeedItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    data: ItemIn,
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    """Parents put cards on the board."""
    _check_assignee(db, data.assignee_id)
    if data.kind == ItemKind.routine and data.date_for is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Routines repeat daily; no date")

    item = Item(
        kind=data.kind,
        title=data.title,
        notes=data.notes,
        assignee_id=data.assignee_id,
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
    _parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id)
    fields = data.model_fields_set  # only touch keys the client actually sent

    if "assignee_id" in fields:
        _check_assignee(db, data.assignee_id)
        item.assignee_id = data.assignee_id
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
    _parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id)
    db.delete(item)  # completions cascade away with it
    db.commit()


def _can_check(item: Item, user: User) -> bool:
    """Parents can check anything. Children only their own or family cards."""
    if user.role == Role.parent:
        return True
    return item.assignee_id is None or item.assignee_id == user.id


@router.post("/{item_id}/complete", response_model=FeedItemOut)
def complete_item(
    item_id: int,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_date(date_for)
    item = _get_item(db, item_id)
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
    user: User = Depends(get_current_user),
):
    """Undo an accidental check-off for that day."""
    _check_date(date_for)
    item = _get_item(db, item_id)
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
