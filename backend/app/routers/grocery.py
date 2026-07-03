from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_parent
from app.models import GroceryItem, User
from app.schemas import GroceryItemIn, GroceryItemOut, GroceryItemUpdate

router = APIRouter(prefix="/grocery", tags=["grocery"])

# Permissions (decided 2026-07-03): every member can SEE the list, but only
# parents can touch it — add, check, rename, delete, clear.


def _get_item(db: Session, item_id: int) -> GroceryItem:
    item = db.get(GroceryItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such grocery item")
    return item


def _full_list(db: Session) -> list[GroceryItem]:
    # Oldest first, so the list reads in the order the family wrote it.
    return list(db.scalars(select(GroceryItem).order_by(GroceryItem.created_at, GroceryItem.id)))


@router.get("", response_model=list[GroceryItemOut])
def list_grocery(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return _full_list(db)


@router.post("", response_model=GroceryItemOut, status_code=status.HTTP_201_CREATED)
def add_grocery(
    data: GroceryItemIn,
    db: Session = Depends(get_db),
    _parent: User = Depends(require_parent),
):
    item = GroceryItem(title=data.title)
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
    if data.title is not None:
        item.title = data.title
    if data.checked is not None:
        item.checked = data.checked
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


@router.post("/clear-checked", response_model=list[GroceryItemOut])
def clear_checked(db: Session = Depends(get_db), _parent: User = Depends(require_parent)):
    """Sweep every checked-off line away; returns what's left to grab."""
    db.execute(delete(GroceryItem).where(GroceryItem.checked))
    db.commit()
    return _full_list(db)
