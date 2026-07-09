import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.deps import require_family, require_parent
from app.models import DinnerOption, DinnerVote, Meal, MealSlot, Recipe, RecipeIngredient, User
from app.routers.recipes import per_serving_macros
from app.schemas import (
    DinnerBallotIn,
    DinnerBallotOut,
    DinnerOptionOut,
    MealIn,
    MealOut,
)

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


# ---- dinner voting ---------------------------------------------------------------
# A parent posts a few candidates for a night; every family member (kids
# included — deliberately their one Kitchen write) votes once, changeable;
# the parent reads the tally and crowns the winner via the normal PUT /meals.


def _ballot_out(db: Session, family_id: int, date_for: dt.date, viewer: User) -> DinnerBallotOut:
    options = db.scalars(
        select(DinnerOption)
        .where(DinnerOption.family_id == family_id, DinnerOption.date_for == date_for)
        .order_by(DinnerOption.position, DinnerOption.id)
    ).all()
    votes = db.execute(
        select(DinnerVote, User.display_name)
        .join(User, User.id == DinnerVote.user_id)
        .where(DinnerVote.family_id == family_id, DinnerVote.date_for == date_for)
        .order_by(DinnerVote.created_at, DinnerVote.id)
    ).all()
    by_option: dict[int, list[tuple[int, str]]] = {}
    for vote, name in votes:
        by_option.setdefault(vote.option_id, []).append((vote.user_id, name.split()[0]))
    return DinnerBallotOut(
        date_for=date_for,
        options=[
            DinnerOptionOut(
                id=o.id,
                title=o.title,
                recipe_id=o.recipe_id,
                votes=len(by_option.get(o.id, [])),
                voters=[n for _, n in by_option.get(o.id, [])],
                my_vote=any(uid == viewer.id for uid, _ in by_option.get(o.id, [])),
            )
            for o in options
        ],
        total_votes=len(votes),
    )


@router.get("/vote", response_model=DinnerBallotOut)
def get_ballot(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    return _ballot_out(db, user.family_id, date_for, user)


@router.put("/vote", response_model=DinnerBallotOut)
def open_ballot(
    data: DinnerBallotIn,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Open (or replace) the night's ballot. Replacing clears cast votes —
    the choices changed, so the votes no longer mean anything."""
    from app.routers.recipes import _get_recipe

    db.execute(
        delete(DinnerVote).where(
            DinnerVote.family_id == parent.family_id, DinnerVote.date_for == date_for
        )
    )
    db.execute(
        delete(DinnerOption).where(
            DinnerOption.family_id == parent.family_id, DinnerOption.date_for == date_for
        )
    )
    for i, opt in enumerate(data.options):
        recipe_id = None
        if opt.recipe_id is not None:
            recipe_id = _get_recipe(db, opt.recipe_id, parent.family_id).id
        db.add(
            DinnerOption(
                family_id=parent.family_id,
                date_for=date_for,
                title=opt.title.strip(),
                recipe_id=recipe_id,
                position=i,
            )
        )
    db.commit()
    return _ballot_out(db, parent.family_id, date_for, parent)


@router.delete("/vote", status_code=status.HTTP_204_NO_CONTENT)
def close_ballot(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    db.execute(
        delete(DinnerVote).where(
            DinnerVote.family_id == parent.family_id, DinnerVote.date_for == date_for
        )
    )
    db.execute(
        delete(DinnerOption).where(
            DinnerOption.family_id == parent.family_id, DinnerOption.date_for == date_for
        )
    )
    db.commit()


@router.post("/vote/{option_id}", response_model=DinnerBallotOut)
def cast_vote(
    option_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """One vote per member per night, changeable until the ballot closes.
    Every member votes — this is the single Kitchen write a child has."""
    option = db.get(DinnerOption, option_id)
    if option is None or option.family_id != user.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such option")
    existing = db.scalar(
        select(DinnerVote).where(
            DinnerVote.family_id == user.family_id,
            DinnerVote.date_for == option.date_for,
            DinnerVote.user_id == user.id,
        )
    )
    if existing is None:
        db.add(
            DinnerVote(
                family_id=user.family_id,
                date_for=option.date_for,
                user_id=user.id,
                option_id=option.id,
            )
        )
    else:
        existing.option_id = option.id
    db.commit()
    return _ballot_out(db, user.family_id, option.date_for, user)
