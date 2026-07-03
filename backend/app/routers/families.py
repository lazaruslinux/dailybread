from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Family, Role, User
from app.schemas import FamilyIn, FamilyOut

router = APIRouter(prefix="/families", tags=["families"])


@router.post("", response_model=FamilyOut, status_code=status.HTTP_201_CREATED)
def create_family(
    data: FamilyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The create-your-family wizard: a new-household account names its
    family and becomes its head (parent + admin). One family per account,
    ever — everyone else joins a family by being created inside one."""
    if user.family_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are already in a family")

    family = Family(name=data.name.strip())
    db.add(family)
    db.flush()  # assigns family.id before we point the user at it
    user.family_id = family.id
    user.role = Role.parent
    user.is_admin = True
    db.commit()
    db.refresh(family)
    return family
