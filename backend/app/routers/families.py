from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.clock import valid_timezone
from app.db import get_db
from app.deps import get_current_user, require_admin, require_family
from app.models import (
    DinnerVote,
    Family,
    Food,
    GroceryItem,
    GroceryList,
    Item,
    Meal,
    Recipe,
    Role,
    SavedFood,
    User,
    Village,
    VillageFamily,
    VillageRecipe,
)
from app.schemas import FamilyIn, FamilyOut

router = APIRouter(prefix="/families", tags=["families"])


def _checked_timezone(data: FamilyIn) -> str | None:
    """The submitted zone, verified against the IANA database. A typo'd zone
    would silently fall back to the server clock forever — refuse it now."""
    if data.timezone is not None and not valid_timezone(data.timezone):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown timezone")
    return data.timezone


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

    family = Family(name=data.name.strip(), timezone=_checked_timezone(data))
    db.add(family)
    db.flush()  # assigns family.id before we point the user at it
    user.family_id = family.id
    user.role = Role.parent
    user.is_admin = True
    db.commit()
    db.refresh(family)
    return family


@router.get("/me", response_model=FamilyOut)
def my_family(db: Session = Depends(get_db), user: User = Depends(require_family)):
    """The signed-in member's own family. There is deliberately no way to
    read any other family — not even its name."""
    return db.get(Family, user.family_id)


@router.patch("/me", response_model=FamilyOut)
def update_family(
    data: FamilyIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Rename the family, or move it to its own clock. Villages show the name
    to linked families, so a fun custom name beats a shared last name. The
    timezone drives reminders and digests; omitted = unchanged, an explicit
    null = back to the server's clock."""
    family = db.get(Family, admin.family_id)
    family.name = data.name.strip()
    if "timezone" in data.model_fields_set:
        family.timezone = _checked_timezone(data)
    db.commit()
    db.refresh(family)
    return family


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family(
    family_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Server admin only: remove a household and everything it owns — its
    members, board, kitchen, diary, the lot. Villages it belonged to lose a
    member (an emptied village is deleted, like the last family leaving);
    recipe copies other families saved stay theirs, exactly as when a family
    leaves a village. The server admin's own family is not deletable, so the
    install always has a working admin."""
    if not admin.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Server admin only")
    if family_id == admin.family_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot remove your own family.")
    family = db.get(Family, family_id)
    if family is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such family")

    village_ids = db.scalars(
        select(VillageFamily.village_id).where(VillageFamily.family_id == family_id)
    ).all()

    # Family-owned rows, children before parents. User-owned rows (diary,
    # weights, moods, subscriptions...) cascade away with the users; item
    # rows (completions, reminder log) cascade with the items.
    db.execute(delete(VillageRecipe).where(VillageRecipe.family_id == family_id))
    db.execute(delete(Item).where(Item.family_id == family_id))
    db.execute(delete(DinnerVote).where(DinnerVote.family_id == family_id))
    db.execute(delete(Meal).where(Meal.family_id == family_id))
    db.execute(delete(GroceryItem).where(GroceryItem.family_id == family_id))
    db.execute(delete(GroceryList).where(GroceryList.family_id == family_id))
    db.execute(delete(Recipe).where(Recipe.family_id == family_id))
    # Saved-food shelf rows must go explicitly: their family_id FK has no cascade,
    # and a shelf entry pointing at a shared-cache food (family_id NULL, which we
    # never delete) wouldn't fall away with the family's own foods below.
    db.execute(delete(SavedFood).where(SavedFood.family_id == family_id))
    db.execute(delete(User).where(User.family_id == family_id))
    # After users: their diary rows (which point at foods) are gone.
    db.execute(delete(Food).where(Food.family_id == family_id))
    db.delete(family)  # membership rows cascade; founded villages get SET NULL
    db.flush()

    # The last family out turns off the lights, same as leaving.
    for village_id in village_ids:
        remaining = db.scalar(
            select(func.count())
            .select_from(VillageFamily)
            .where(VillageFamily.village_id == village_id)
        )
        if remaining == 0:
            village = db.get(Village, village_id)
            if village is not None:
                db.delete(village)
    db.commit()
