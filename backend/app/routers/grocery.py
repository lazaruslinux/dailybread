from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import inbox
from app.db import get_db
from app.deps import require_family, require_parent
from app.models import GroceryItem, GroceryList, User
from app.schemas import (
    GroceryItemIn,
    GroceryItemOut,
    GroceryItemUpdate,
    GroceryListIn,
    GroceryListOut,
    GroceryStateOut,
)

router = APIRouter(prefix="/grocery", tags=["grocery"])

# Permissions (decided 2026-07-03): every member can SEE the lists, but only
# parents can touch them — add, check, rename, move, delete, clear.


def _get_item(db: Session, item_id: int, family_id: int) -> GroceryItem:
    """Cross-family ids 404 like they don't exist, so nothing leaks."""
    item = db.get(GroceryItem, item_id)
    if item is None or item.family_id != family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such grocery item")
    return item


def _check_list(db: Session, list_id: int | None, family_id: int) -> None:
    """list_id None is always fine: that's the built-in General list."""
    if list_id is None:
        return
    store = db.get(GroceryList, list_id)
    if store is None or store.family_id != family_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No such store")


def _store_name(db: Session, list_id: int | None, family_id: int) -> str:
    """A list's display name for an Inbox line; None is the built-in General."""
    if list_id is None:
        return "General"
    store = db.get(GroceryList, list_id)
    return store.name if store is not None and store.family_id == family_id else "General"


def _state(db: Session, family_id: int) -> GroceryStateOut:
    lists = db.scalars(
        select(GroceryList)
        .where(GroceryList.family_id == family_id)
        .order_by(GroceryList.created_at, GroceryList.id)
    ).all()
    # Oldest first, so each list reads in the order the family wrote it.
    items = db.scalars(
        select(GroceryItem)
        .where(GroceryItem.family_id == family_id)
        .order_by(GroceryItem.created_at, GroceryItem.id)
    ).all()
    return GroceryStateOut(lists=list(lists), items=list(items))


@router.get("", response_model=GroceryStateOut)
def get_grocery(db: Session = Depends(get_db), user: User = Depends(require_family)):
    return _state(db, user.family_id)


# ---- stores -------------------------------------------------------------------


@router.post("/lists", response_model=GroceryListOut, status_code=status.HTTP_201_CREATED)
def add_store(
    data: GroceryListIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    name = data.name.strip()
    # Duplicate names only matter within one family; two households can
    # both shop at Costco.
    dupe = db.scalar(
        select(GroceryList).where(
            GroceryList.family_id == parent.family_id,
            func.lower(GroceryList.name) == name.lower(),
        )
    )
    if dupe is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That store already exists")
    store = GroceryList(name=name, family_id=parent.family_id)
    db.add(store)
    db.commit()
    db.refresh(store)
    inbox.record_all(
        db, inbox.other_adults(db, parent), "grocery",
        f"{parent.display_name.split()[0]} added a store: {store.name}",
    )
    return store


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_store(
    list_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Remove a store; its items fall back to the General list (FK SET NULL)."""
    store = db.get(GroceryList, list_id)
    if store is None or store.family_id != parent.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such store")
    name = store.name
    db.delete(store)
    db.commit()
    inbox.record_all(
        db, inbox.other_adults(db, parent), "grocery",
        f"{parent.display_name.split()[0]} removed a store: {name}",
        "Its items moved to General",
    )


# ---- items --------------------------------------------------------------------


@router.post("", response_model=GroceryItemOut, status_code=status.HTTP_201_CREATED)
def add_grocery(
    data: GroceryItemIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    _check_list(db, data.list_id, parent.family_id)
    item = GroceryItem(title=data.title, list_id=data.list_id, family_id=parent.family_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    inbox.record_all(
        db, inbox.other_adults(db, parent), "grocery",
        f"{parent.display_name.split()[0]} added to groceries: {item.title}",
        _store_name(db, item.list_id, parent.family_id),
    )
    return item


@router.patch("/{item_id}", response_model=GroceryItemOut)
def update_grocery(
    item_id: int,
    data: GroceryItemUpdate,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    # No Inbox line here on purpose: check/uncheck taps are the store-aisle hot
    # path, and renames/moves ride the same PATCH — recording any of them would
    # drown the inbox. Adds, deletes, and clears carry the grocery history.
    item = _get_item(db, item_id, parent.family_id)
    fields = data.model_fields_set  # only touch keys the client actually sent
    if "title" in fields and data.title is not None:
        item.title = data.title
    if "checked" in fields and data.checked is not None:
        item.checked = data.checked
    if "list_id" in fields:
        _check_list(db, data.list_id, parent.family_id)
        item.list_id = data.list_id
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grocery(
    item_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id, parent.family_id)
    title, list_id = item.title, item.list_id
    db.delete(item)
    db.commit()
    inbox.record_all(
        db, inbox.other_adults(db, parent), "grocery",
        f"{parent.display_name.split()[0]} removed from groceries: {title}",
        _store_name(db, list_id, parent.family_id),
    )


@router.post("/clear-checked", response_model=GroceryStateOut)
def clear_checked(
    list_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Sweep checked lines off ONE list (None = General), not all of them:
    clearing what you grabbed at Walmart shouldn't erase Safeway's progress."""
    _check_list(db, list_id, parent.family_id)
    result = db.execute(
        delete(GroceryItem).where(
            GroceryItem.family_id == parent.family_id,
            GroceryItem.checked,
            GroceryItem.list_id == list_id if list_id is not None else GroceryItem.list_id.is_(None),
        )
    )
    db.commit()
    n = result.rowcount
    if n:  # clearing a list with nothing checked is a quiet no-op
        inbox.record_all(
            db, inbox.other_adults(db, parent), "grocery",
            f"{parent.display_name.split()[0]} cleared checked-off groceries",
            f"{n} item{'' if n == 1 else 's'} · {_store_name(db, list_id, parent.family_id)}",
        )
    return _state(db, parent.family_id)
