from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_parent
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


def _get_item(db: Session, item_id: int) -> GroceryItem:
    item = db.get(GroceryItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such grocery item")
    return item


def _check_list(db: Session, list_id: int | None) -> None:
    """list_id None is always fine: that's the built-in General list."""
    if list_id is not None and db.get(GroceryList, list_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No such store")


def _state(db: Session) -> GroceryStateOut:
    lists = db.scalars(select(GroceryList).order_by(GroceryList.created_at, GroceryList.id)).all()
    # Oldest first, so each list reads in the order the family wrote it.
    items = db.scalars(select(GroceryItem).order_by(GroceryItem.created_at, GroceryItem.id)).all()
    return GroceryStateOut(lists=list(lists), items=list(items))


@router.get("", response_model=GroceryStateOut)
def get_grocery(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return _state(db)


# ---- stores -------------------------------------------------------------------


@router.post("/lists", response_model=GroceryListOut, status_code=status.HTTP_201_CREATED)
def add_store(
    data: GroceryListIn,
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    name = data.name.strip()
    dupe = db.scalar(select(GroceryList).where(func.lower(GroceryList.name) == name.lower()))
    if dupe is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That store already exists")
    store = GroceryList(name=name)
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_store(
    list_id: int,
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    """Remove a store; its items fall back to the General list (FK SET NULL)."""
    store = db.get(GroceryList, list_id)
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such store")
    db.delete(store)
    db.commit()


# ---- items --------------------------------------------------------------------


@router.post("", response_model=GroceryItemOut, status_code=status.HTTP_201_CREATED)
def add_grocery(
    data: GroceryItemIn,
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    _check_list(db, data.list_id)
    item = GroceryItem(title=data.title, list_id=data.list_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=GroceryItemOut)
def update_grocery(
    item_id: int,
    data: GroceryItemUpdate,
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    item = _get_item(db, item_id)
    fields = data.model_fields_set  # only touch keys the client actually sent
    if "title" in fields and data.title is not None:
        item.title = data.title
    if "checked" in fields and data.checked is not None:
        item.checked = data.checked
    if "list_id" in fields:
        _check_list(db, data.list_id)
        item.list_id = data.list_id
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grocery(
    item_id: int,
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    db.delete(_get_item(db, item_id))
    db.commit()


@router.post("/clear-checked", response_model=GroceryStateOut)
def clear_checked(
    list_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    """Sweep checked lines off ONE list (None = General), not all of them:
    clearing what you grabbed at Walmart shouldn't erase Safeway's progress."""
    _check_list(db, list_id)
    db.execute(
        delete(GroceryItem).where(
            GroceryItem.checked,
            GroceryItem.list_id == list_id if list_id is not None else GroceryItem.list_id.is_(None),
        )
    )
    db.commit()
    return _state(db)
