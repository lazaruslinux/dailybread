import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app import inbox
from app.db import get_db
from app.deps import require_family, require_parent
from app.models import (
    DinnerChoice,
    DinnerVote,
    Meal,
    MealSlot,
    Recipe,
    RecipeIngredient,
    User,
)
from app.routers.recipes import per_serving_macros
from app.schemas import (
    DinnerPlanOut,
    DinnerVoteIn,
    DinnerVoteOut,
    DinnerVoterOut,
    MealIn,
    MealOut,
    MealTimeIn,
)

router = APIRouter(prefix="/meals", tags=["meals"])

# Same bound as the calendar: wide enough for any month view, small enough
# that a range request stays cheap.
_MAX_SPAN = dt.timedelta(days=45)


def _clock(t: dt.time) -> str:
    """A wall-clock time the way a person reads it: "5:30 PM"."""
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour}:{t.minute:02d} {suffix}"


# How each dinner vote reads in a line: "Alex voted for dinner" / "Going out".
_CHOICE_LABEL = {
    DinnerChoice.self_serve: "Self-serve",
    DinnerChoice.homemade: "Homemade",
    DinnerChoice.go_out: "Going out",
    DinnerChoice.delivery: "Delivery",
}


def _out(meal: Meal) -> MealOut:
    recipe = meal.recipe
    return MealOut(
        date_for=meal.date_for,
        slot=meal.slot,
        recipe_id=meal.recipe_id,
        recipe_name=recipe.name if recipe is not None else None,
        custom_title=meal.custom_title,
        time_of_day=meal.time_of_day,
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
    # None = no row yet; distinct from any (recipe_id, custom_title) pair, so
    # a fresh plan always counts as a change below.
    before_pick = (meal.recipe_id, meal.custom_title) if meal is not None else None
    if meal is None:
        meal = Meal(family_id=parent.family_id, date_for=data.date_for, slot=data.slot)
        db.add(meal)
    meal.recipe_id = recipe.id if recipe is not None else None
    meal.custom_title = None if recipe is not None else title
    db.commit()
    db.refresh(meal)
    if meal.slot == MealSlot.dinner:
        _push_dinner_lock(db, parent, meal, recipe)
    elif (meal.recipe_id, meal.custom_title) != before_pick:
        # Breakfast and lunch aren't a lock-in moment (only dinner rings), but
        # planning them is still family history worth an Inbox line — when the
        # pick actually changed (re-saving the same plan is not news).
        what = recipe.name if recipe is not None else (meal.custom_title or "")
        inbox.record_all(
            db, inbox.other_adults(db, parent), "dinner",
            f"{parent.display_name.split()[0]} planned {meal.slot.value}: {what}",
        )
    return _out(meal)


def _push_dinner_lock(db: Session, parent: User, meal: Meal, recipe: Recipe | None) -> None:
    """Locking dinner IS setting the meal row, and it's the one dinner moment
    the family hears about ON THE PHONE (votes stay quiet). Clearing the meal
    (unlock) says nothing either."""
    try:
        from app import push

        what = recipe.name if recipe is not None else (meal.custom_title or "")
        body = what
        if meal.time_of_day is not None:
            body = f"{what} · {_clock(meal.time_of_day)}"
        payload = {
            "title": f"{parent.display_name.split()[0]} locked in dinner",
            "body": body,
            "tag": f"dinner-lock-{meal.date_for.isoformat()}",
            "url": "/",
        }
        members = [
            m
            for m in db.scalars(
                select(User).where(User.family_id == parent.family_id, User.id != parent.id)
            )
            if not m.is_minor
        ]
        # Inbox first, committed before the push leg: history survives a
        # failed nudge, and neither depends on push being configured.
        for member in members:
            inbox.record(db, member.id, member.family_id, "dinner", payload["title"], body)
        db.commit()
        if push.enabled():
            for member in members:
                if push.wants(member, "family"):
                    push.send_to_user(db, member.id, payload)
    except Exception:
        db.rollback()  # the plan is saved; a failed nudge is not worth a 500


@router.put("/time", response_model=MealOut)
def set_meal_time(
    data: MealTimeIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Set (or clear) when the slot's meal happens, without touching what it
    is. Clearing the time on a night that has no pick removes the row."""
    meal = db.scalar(
        select(Meal).where(
            Meal.family_id == parent.family_id,
            Meal.date_for == data.date_for,
            Meal.slot == data.slot,
        )
    )
    if meal is None:
        if data.time_of_day is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No time set for that day")
        meal = Meal(family_id=parent.family_id, date_for=data.date_for, slot=data.slot)
        db.add(meal)
    meal.time_of_day = data.time_of_day
    first = parent.display_name.split()[0]
    slot = data.slot.value
    if meal.time_of_day is None and meal.recipe_id is None and not meal.custom_title:
        db.delete(meal)
        db.commit()
        inbox.record_all(
            db, inbox.other_adults(db, parent), "dinner",
            f"{first} cleared the {slot} time",
        )
        return MealOut(
            date_for=data.date_for, slot=data.slot,
            recipe_id=None, recipe_name=None, custom_title=None, time_of_day=None,
        )
    db.commit()
    db.refresh(meal)
    if data.time_of_day is None:
        inbox.record_all(
            db, inbox.other_adults(db, parent), "dinner",
            f"{first} cleared the {slot} time",
        )
    else:
        what = meal.recipe.name if meal.recipe is not None else (meal.custom_title or "")
        detail = " · ".join(
            p for p in (what, _clock(data.time_of_day), meal.date_for.strftime("%a %b %-d")) if p
        )
        inbox.record_all(
            db, inbox.other_adults(db, parent), "dinner",
            f"{first} set a {slot} time",
            detail,
        )
    return _out(meal)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_meal(
    date_for: dt.date = Query(alias="date"),
    slot: MealSlot = Query(default=MealSlot.dinner),
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Un-plan a day's slot. A set time survives the unpick (dinner is still
    at 5, we just don't know what it is again); a timeless row goes away.
    Clearing an unplanned day is a quiet no-op."""
    meal = db.scalar(
        select(Meal).where(
            Meal.family_id == parent.family_id,
            Meal.date_for == date_for,
            Meal.slot == slot,
        )
    )
    if meal is not None:
        had_pick = meal.recipe_id is not None or bool(meal.custom_title)
        what = meal.recipe.name if meal.recipe is not None else (meal.custom_title or "")
        date_txt = meal.date_for.strftime("%a %b %-d")
        if meal.time_of_day is not None:
            meal.recipe_id = None
            meal.custom_title = None
        else:
            db.delete(meal)
        db.commit()
        # Only a real un-plan is news: clearing a night that carried only a
        # time (or nothing) says nothing.
        if had_pick:
            inbox.record_all(
                db, inbox.other_adults(db, parent), "dinner",
                f"{parent.display_name.split()[0]} unplanned {slot.value}",
                f"{what} · {date_txt}",
            )


# ---- the dinner plan ---------------------------------------------------------------
# Four standing modes, always on for a day until dinner is set. Every member
# picks one (changeable, retractable); each pick shows as that member's
# avatar plus their short detail. Kids' votes are advisory by construction:
# only a parent can lock the plan in. A kid who hasn't voted rides along in
# the kids list so the row still shows the whole family. Locking the plan is
# just setting the normal meal row, so unlocking (clearing the meal) brings
# the untouched votes straight back.


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
    # Kids who VOTED are real voter chips; only the ones who haven't weighed
    # in yet ride along here, so every face still shows on the row.
    voted_ids = {v.user_id for v, _ in rows}
    kids = [
        u
        for u in db.scalars(
            select(User).where(User.family_id == family_id).order_by(User.created_at)
        )
        if u.is_minor and u.id not in voted_ids
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
    user: User = Depends(require_family),
):
    """Set (or change) my pick for the night. Every member votes, kids
    included — the ballot only ever touches the caller's own row, and only
    a parent can turn the winning pick into the actual plan (set_meal)."""
    from app.models import DinnerChoice
    from app.routers.recipes import _get_recipe

    if data.choice == DinnerChoice.self_serve and (data.detail or data.recipe_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Self-serve needs no detail")
    if data.recipe_id is not None and data.choice != DinnerChoice.homemade:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only homemade takes a recipe")
    recipe_id = None
    if data.recipe_id is not None:
        recipe_id = _get_recipe(db, data.recipe_id, user.family_id).id

    vote = db.scalar(
        select(DinnerVote).where(
            DinnerVote.family_id == user.family_id,
            DinnerVote.date_for == date_for,
            DinnerVote.user_id == user.id,
        )
    )
    # None = first vote; distinct from any ballot triple, so a new vote always
    # counts as a change below.
    before = (vote.choice, vote.detail, vote.recipe_id) if vote is not None else None
    if vote is None:
        vote = DinnerVote(family_id=user.family_id, date_for=date_for, user_id=user.id)
        db.add(vote)
    vote.choice = data.choice
    vote.detail = data.detail.strip()
    vote.recipe_id = recipe_id
    db.commit()
    # Votes write history but never RING: the family gets pushed only when
    # dinner is LOCKED IN (set_meal), the one moment that decides the night. A
    # kid's vote still records to the adults — every voice on the plan is news.
    # Re-casting the identical ballot is not (voting is a tap UI; taps repeat).
    if (vote.choice, vote.detail, vote.recipe_id) != before:
        extra = ""
        if recipe_id is not None:
            extra = f" · {db.get(Recipe, recipe_id).name}"
        elif vote.detail:
            extra = f" · {vote.detail}"
        inbox.record_all(
            db, inbox.other_adults(db, user), "dinner",
            f"{user.display_name.split()[0]} voted for dinner",
            f"{_CHOICE_LABEL.get(data.choice, '')}{extra} · {date_for.strftime('%a %b %-d')}",
        )
    return _plan_out(db, user.family_id, date_for)


@router.delete("/plan", response_model=DinnerPlanOut)
def retract_dinner_vote(
    date_for: dt.date = Query(alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    vote = db.scalar(
        select(DinnerVote).where(
            DinnerVote.family_id == user.family_id,
            DinnerVote.date_for == date_for,
            DinnerVote.user_id == user.id,
        )
    )
    if vote is not None:
        db.delete(vote)
        db.commit()
        inbox.record_all(
            db, inbox.other_adults(db, user), "dinner",
            f"{user.display_name.split()[0]} took back their dinner vote",
        )
    return _plan_out(db, user.family_id, date_for)
