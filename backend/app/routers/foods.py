import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import foods_api
from app.config import settings
from app.db import get_db
from app.deps import require_family, require_parent
from app.models import Food, FoodServing, FoodSource, User
from app.schemas import FOOD_NUTRIENTS, FoodIn, FoodOut

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
        serving=r.serving,
        **{n: getattr(r, n) for n in FOOD_NUTRIENTS},
    )


def _apply_custom_food(food: Food, data: FoodIn) -> None:
    """Set a custom food's nutrition and servings from the create/edit payload.
    Values are entered per the chosen serving (basis_index); we store per-100 of
    the food's base unit (grams for a solid, millilitres for a liquid) so it sits
    alongside USDA/OFF foods and feeds the recipe math. A serving of B base units
    means per-100 = entered * 100 / B."""
    food.name = data.name.strip()
    food.brand = data.brand.strip()
    food.source_id = data.barcode
    food.base_unit = data.base_unit
    factor = 100.0 / data.servings[data.basis_index].grams
    for n in FOOD_NUTRIENTS:
        entered = getattr(data, n)
        setattr(food, n, round(entered * factor, 2) if entered is not None else None)
    food.servings = [
        FoodServing(name=s.name.strip(), grams=s.grams, position=i)
        for i, s in enumerate(data.servings)
    ]


# Recent search results, kept briefly so retyping a query (or two members
# searching the same thing) doesn't re-hit USDA — the free key covers the whole
# install at ~3600 requests/hour. Errors are never cached; only good answers.
_SEARCH_TTL_SECONDS = 15 * 60
_SEARCH_CACHE_MAX = 200
_search_cache: dict[str, tuple[float, list[foods_api.FoodResult]]] = {}


def _searched(q: str) -> list[foods_api.FoodResult]:
    key = q.strip().lower()
    now = time.monotonic()
    hit = _search_cache.get(key)
    if hit is not None and now - hit[0] < _SEARCH_TTL_SECONDS:
        return hit[1]
    results = foods_api.search_usda(q, settings.usda_api_key)
    if len(_search_cache) >= _SEARCH_CACHE_MAX:
        # Drop the stalest entry; the cache stays small and recent.
        del _search_cache[min(_search_cache, key=lambda k: _search_cache[k][0])]
    _search_cache[key] = (now, results)
    return results


@router.get("/search", response_model=list[FoodOut])
def search_foods(
    q: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Search the food database (USDA FoodData Central), server-side."""
    try:
        results = _searched(q)
    except foods_api.FoodApiError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return [_result_out(r) for r in results]


@router.get("/barcode/{code}", response_model=FoodOut)
def lookup_barcode(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Resolve a scanned barcode, checking home before asking the internet:
    first the family's own custom foods (a product they entered by hand after
    an unknown scan), then foods already cached from earlier lookups, and only
    then Open Food Facts. Scanning something you've scanned before never
    leaves the server."""
    if not code.isdigit() or not (6 <= len(code) <= 14):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That doesn't look like a barcode")

    ours = db.scalar(
        select(Food)
        .where(
            Food.family_id == user.family_id,
            Food.source == FoodSource.custom,
            Food.source_id == code,
        )
        .options(selectinload(Food.servings))
        .order_by(Food.id.desc())
        .limit(1)
    )
    if ours is not None:
        return ours

    cached = db.scalar(
        select(Food)
        .where(
            Food.family_id.is_(None),
            Food.source == FoodSource.off,
            Food.source_id == code,
        )
        .order_by(Food.id.desc())
        .limit(1)
    )
    if cached is not None:
        return cached

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
            .options(selectinload(Food.servings))
            .order_by(func.lower(Food.name))
        )
    )


@router.post("", response_model=FoodOut, status_code=status.HTTP_201_CREATED)
def create_custom_food(
    data: FoodIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    food = Food(family_id=parent.family_id, source=FoodSource.custom, source_id=None)
    _apply_custom_food(food, data)
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


def _own_custom_food(db: Session, food_id: int, parent: User) -> Food:
    """A custom food this family owns, or 404. The shared USDA/OFF cache and other
    families' foods aren't this family's to edit or remove."""
    food = db.get(Food, food_id)
    if (
        food is None
        or food.source != FoodSource.custom
        or food.family_id != parent.family_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such food")
    return food


@router.put("/{food_id}", response_model=FoodOut)
def update_custom_food(
    food_id: int,
    data: FoodIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Edit a custom food. Recipes that reference it recompute from the new
    nutrition on their next read (they hold a food_id, not a snapshot)."""
    food = _own_custom_food(db, food_id, parent)
    _apply_custom_food(food, data)
    db.commit()
    db.refresh(food)
    return food


@router.delete("/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_food(
    food_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Delete a custom food. Only the family's own custom entries."""
    db.delete(_own_custom_food(db, food_id, parent))
    db.commit()
