import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.deps import require_family, require_parent
from app.models import Meal, MealSlot, Recipe, RecipeIngredient, User
from app.routers.recipes import per_serving_macros
from app.schemas import MealIn, MealOut

router = APIRouter(prefix="/meals", tags=["meals"])

# Same bound as the calendar: wide enough for any month view, small enough
# that a range request stays cheap.
_MAX_SPAN = dt.timedelta(days=45)


def _out(meal: Meal) -> MealOut:
    recipe = meal.recipe
    return MealOut(
        date_for=meal.date_for,
        slot=meal.slot,
        recipe_id=meal.recipe_id,
        recipe_name=recipe.name if recipe is not None else None,
        custom_title=meal.custom_title,
        per_serving=per_serving_macros(recipe) if recipe is not None else None,
    )


@router.get("", response_model=list[MealOut])
def list_meals(
    start: dt.date = Query(),
    end: dt.date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """The family's planned meals across a date range. Every member can see
    the menu; only days that have a plan come back."""
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end must be on or after start")
    if end - start > _MAX_SPAN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Meal range is too wide")
    meals = db.scalars(
        select(Meal)
        .options(
            # The recipe rides along with its ingredient foods loaded, so the
            # per-serving figures come out of this one round of queries.
            joinedload(Meal.recipe)
            .selectinload(Recipe.ingredients)
            .joinedload(RecipeIngredient.food)
        )
        .where(Meal.family_id == user.family_id, Meal.date_for.between(start, end))
        .order_by(Meal.date_for, Meal.slot)
    ).all()
    return [_out(m) for m in meals]


@router.put("", response_model=MealOut)
def set_meal(
    data: MealIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Plan (or replan) a day's slot — an upsert keyed by (date, slot).
    Picking a recipe clears any typed title and vice versa."""
    title = (data.custom_title or "").strip()
    if data.recipe_id is None and not title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick a recipe or type a meal")

    recipe = None
    if data.recipe_id is not None:
        recipe = db.get(Recipe, data.recipe_id)
        # Cross-family recipe ids look like they don't exist, as everywhere.
        if recipe is None or recipe.family_id != parent.family_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe")

    meal = db.scalar(
        select(Meal).where(
            Meal.family_id == parent.family_id,
            Meal.date_for == data.date_for,
            Meal.slot == data.slot,
        )
    )
    if meal is None:
        meal = Meal(family_id=parent.family_id, date_for=data.date_for, slot=data.slot)
        db.add(meal)
    meal.recipe_id = recipe.id if recipe is not None else None
    meal.custom_title = None if recipe is not None else title
    db.commit()
    db.refresh(meal)
    return _out(meal)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_meal(
    date_for: dt.date = Query(alias="date"),
    slot: MealSlot = Query(default=MealSlot.dinner),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Un-plan a day's slot. Clearing an unplanned day is a quiet no-op."""
    meal = db.scalar(
        select(Meal).where(
            Meal.family_id == parent.family_id,
            Meal.date_for == date_for,
            Meal.slot == slot,
        )
    )
    if meal is not None:
        db.delete(meal)
        db.commit()
