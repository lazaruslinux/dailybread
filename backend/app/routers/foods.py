from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import foods_api
from app.config import settings
from app.db import get_db
from app.deps import require_family, require_parent
from app.models import Food, FoodSource, User
from app.schemas import FoodIn, FoodOut

router = APIRouter(prefix="/foods", tags=["foods"])

# The server proxies food search (USDA) and barcode lookups (Open Food Facts) so
# the phones never call a third party. Search/barcode results come back un-saved
# (id null); they're persisted only when used in a recipe. Custom foods are a
# family's own, parent-created, for anything the databases lack.


def _result_out(r: foods_api.FoodResult) -> FoodOut:
    return FoodOut(
        source=FoodSource(r.source),
        source_id=r.source_id,
        name=r.name,
        brand=r.brand,
        calories=r.calories,
        protein_g=r.protein_g,
        carbs_g=r.carbs_g,
        fat_g=r.fat_g,
    )


@router.get("/search", response_model=list[FoodOut])
def search_foods(
    q: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Search the food database (USDA FoodData Central), server-side."""
    try:
        results = foods_api.search_usda(q, settings.usda_api_key)
    except foods_api.FoodApiError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return [_result_out(r) for r in results]


@router.get("/barcode/{code}", response_model=FoodOut)
def lookup_barcode(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Look up a scanned barcode in Open Food Facts, server-side."""
    if not code.isdigit() or not (6 <= len(code) <= 14):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That doesn't look like a barcode")
    try:
        result = foods_api.lookup_barcode(code)
    except foods_api.FoodApiError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product found for that barcode")
    return _result_out(result)


@router.get("", response_model=list[FoodOut])
def list_custom_foods(db: Session = Depends(get_db), user: User = Depends(require_family)):
    """The family's own custom foods, alphabetical."""
    return list(
        db.scalars(
            select(Food)
            .where(Food.family_id == user.family_id, Food.source == FoodSource.custom)
            .order_by(func.lower(Food.name))
        )
    )


@router.post("", response_model=FoodOut, status_code=status.HTTP_201_CREATED)
def create_custom_food(
    data: FoodIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    food = Food(
        family_id=parent.family_id,
        source=FoodSource.custom,
        source_id=None,
        name=data.name.strip(),
        brand=data.brand.strip(),
        calories=data.calories,
        protein_g=data.protein_g,
        carbs_g=data.carbs_g,
        fat_g=data.fat_g,
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


@router.delete("/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_food(
    food_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Delete a custom food. Only the family's own custom entries; the shared
    USDA/OFF cache isn't a family's to remove."""
    food = db.get(Food, food_id)
    if (
        food is None
        or food.source != FoodSource.custom
        or food.family_id != parent.family_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such food")
    db.delete(food)
    db.commit()
