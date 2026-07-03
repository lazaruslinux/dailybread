from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

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
    db.delete(store)
    db.commit()


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
    return item


@router.patch("/{item_id}", response_model=GroceryItemOut)
def update_grocery(
    item_id: int,
    data: GroceryItemUpdate,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
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
    db.delete(_get_item(db, item_id, parent.family_id))
    db.commit()


@router.post("/clear-checked", response_model=GroceryStateOut)
def clear_checked(
    list_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Sweep checked lines off ONE list (None = General), not all of them:
    clearing what you grabbed at Walmart shouldn't erase Safeway's progress."""
    _check_list(db, list_id, parent.family_id)
    db.execute(
        delete(GroceryItem).where(
            GroceryItem.family_id == parent.family_id,
            GroceryItem.checked,
            GroceryItem.list_id == list_id if list_id is not None else GroceryItem.list_id.is_(None),
        )
    )
    db.commit()
    return _state(db, parent.family_id)
