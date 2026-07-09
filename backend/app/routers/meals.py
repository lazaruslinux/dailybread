import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.deps import require_family, require_parent
from app.models import DinnerVote, Meal, MealSlot, Recipe, RecipeIngredient, User
from app.routers.recipes import per_serving_macros
from app.schemas import (
    DinnerPlanOut,
    DinnerVoteIn,
    DinnerVoteOut,
    DinnerVoterOut,
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


# ---- the dinner plan ---------------------------------------------------------------
# Four standing modes, always on for a day until dinner is set. Adults pick
# one (changeable, retractable); each pick shows as that adult's avatar plus
# their short detail. Kids never vote — the client pins their avatars to the
# leading choice. Locking the plan is just setting the normal meal row, so
# unlocking (clearing the meal) brings the untouched votes straight back.


def _plan_out(db: Session, family_id: int, date_for: dt.date) -> DinnerPlanOut:
    rows = db.execute(
        select(DinnerVote, User)
        .join(User, User.id == DinnerVote.user_id)
        .where(DinnerVote.family_id == family_id, DinnerVote.date_for == date_for)
        .order_by(DinnerVote.created_at, DinnerVote.id)
    ).all()
    recipe_ids = [v.recipe_id for v, _ in rows if v.recipe_id is not None]
    names = {
        r.id: r.name
        for r in db.scalars(select(Recipe).where(Recipe.id.in_(recipe_ids)))
    } if recipe_ids else {}
    kids = [
        u
        for u in db.scalars(
            select(User).where(User.family_id == family_id).order_by(User.created_at)
        )
        if u.is_minor
    ]
    return DinnerPlanOut(
        date_for=date_for,
        votes=[
            DinnerVoteOut(
                user=DinnerVoterOut(
                    id=u.id, display_name=u.display_name, avatar_updated_at=u.avatar_updated_at
                ),
                choice=v.choice,
                detail=v.detail,
                recipe_id=v.recipe_id,
                recipe_name=names.get(v.recipe_id),
            )
            for v, u in rows
        ],
        kids=[
            DinnerVoterOut(
                id=k.id, display_name=k.display_name, avatar_updated_at=k.avatar_updated_at
            )
            for k in kids
        ],
    )


@router.get("/plan/week", response_model=list[DinnerPlanOut])
def dinner_plan_week(
    start: dt.date = Query(),
    end: dt.date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """The week planner's view: each day in the span that has votes. Same
    per-day shape as /plan so the client renders both with one code path."""
    if end < start or (end - start).days > 45:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Span too large")
    days = sorted(
        set(
            db.scalars(
                select(DinnerVote.date_for).where(
                    DinnerVote.family_id == user.family_id,
                    DinnerVote.date_for.between(start, end),
                )
            )
        )
    )
    return [_plan_out(db, user.family_id, d) for d in days]


@router.get("/plan", response_model=DinnerPlanOut)
def dinner_plan(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    return _plan_out(db, user.family_id, date_for)


@router.put("/plan", response_model=DinnerPlanOut)
def cast_dinner_vote(
    data: DinnerVoteIn,
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Set (or change) my pick for the night. Adults only — kid avatars are
    display, not ballots."""
    from app.models import DinnerChoice
    from app.routers.recipes import _get_recipe

    if data.choice == DinnerChoice.self_serve and (data.detail or data.recipe_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Self-serve needs no detail")
    if data.recipe_id is not None and data.choice != DinnerChoice.homemade:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only homemade takes a recipe")
    recipe_id = None
    if data.recipe_id is not None:
        recipe_id = _get_recipe(db, data.recipe_id, parent.family_id).id

    first_of_day = (
        db.scalar(
            select(DinnerVote).where(
                DinnerVote.family_id == parent.family_id, DinnerVote.date_for == date_for
            )
        )
        is None
    )

    vote = db.scalar(
        select(DinnerVote).where(
            DinnerVote.family_id == parent.family_id,
            DinnerVote.date_for == date_for,
            DinnerVote.user_id == parent.id,
        )
    )
    if vote is None:
        vote = DinnerVote(family_id=parent.family_id, date_for=date_for, user_id=parent.id)
        db.add(vote)
    vote.choice = data.choice
    vote.detail = data.detail.strip()
    vote.recipe_id = recipe_id
    db.commit()

    # The day's first pick nudges the other adults once; later picks and
    # changes stay quiet — the block is standing, not a conversation thread.
    if first_of_day:
        try:
            from app import push

            if push.enabled():
                first = parent.display_name.split()[0]
                label = {
                    DinnerChoice.self_serve: "Self-serve",
                    DinnerChoice.homemade: "Homemade",
                    DinnerChoice.go_out: "Go out",
                    DinnerChoice.delivery: "Delivery",
                }[data.choice]
                extra = vote.detail or (
                    db.get(Recipe, recipe_id).name if recipe_id else ""
                )
                payload = {
                    "title": f"{first} made a dinner pick",
                    "body": f"{label} · {extra}" if extra else label,
                    "tag": f"dinner-plan-{date_for.isoformat()}",
                    "url": "/",
                }
                for member in db.scalars(
                    select(User).where(
                        User.family_id == parent.family_id, User.id != parent.id
                    )
                ):
                    if not member.is_minor:
                        push.send_to_user(db, member.id, payload)
        except Exception:
            pass  # the vote is saved; a failed nudge is not worth a 500

    return _plan_out(db, parent.family_id, date_for)


@router.delete("/plan", response_model=DinnerPlanOut)
def retract_dinner_vote(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    vote = db.scalar(
        select(DinnerVote).where(
            DinnerVote.family_id == parent.family_id,
            DinnerVote.date_for == date_for,
            DinnerVote.user_id == parent.id,
        )
    )
    if vote is not None:
        db.delete(vote)
        db.commit()
    return _plan_out(db, parent.family_id, date_for)
