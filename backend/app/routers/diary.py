import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_adult, require_family
from app.health import computed_for
from app.models import (
    UNIT_TO_BASE,
    DiaryEntry,
    ExerciseEntry,
    Food,
    NutritionTarget,
    Recipe,
    TargetMode,
    User,
    base_unit_of,
)
from app.routers.recipes import _resolve_food, per_serving_macros
from app.routers.health import _exercise_out
from app.schemas import (
    FOOD_NUTRIENTS,
    DiaryDayOut,
    DiaryEntryIn,
    DiaryEntryOut,
    DiaryEntryUpdate,
    RecipeMacros,
    TargetsIn,
    TargetsOut,
)

# Kid mode: minors have no nutrition area at all (see require_adult).
router = APIRouter(prefix="/diary", tags=["diary"], dependencies=[Depends(require_adult)])

# The diary is personal. Any grown member — adult child included — logs their
# own food, and nobody reads anyone else's: every query here filters on
# user_id, and a foreign entry id 404s exactly like a nonexistent one.

_NUTRIENTS = FOOD_NUTRIENTS

# Fresh installs and members who never set targets read as this split until
# they save their own (see NutritionTarget).
_DEFAULT_TARGETS = {"calories": 2000, "protein_pct": 30, "carbs_pct": 40, "fat_pct": 30}


def _r(v: float) -> float:
    return round(v, 1)


def _targets_out(
    db: Session, user_id: int, row: NutritionTarget | None, exercise_kcal: float = 0.0
) -> TargetsOut:
    vals = dict(
        {k: getattr(row, k) for k in _DEFAULT_TARGETS} if row is not None else _DEFAULT_TARGETS
    )
    mode = row.mode if row is not None else TargetMode.manual
    if mode == TargetMode.auto:
        # The health profile owns the budget; the stored calories are only the
        # fallback for a profile that later became incomplete.
        computed = computed_for(db, user_id)
        if computed is not None:
            vals["calories"] = computed["auto_calories"]
    # A day's logged exercise raises that day's budget (Cronometer's
    # "expenditure above baseline"); gram targets scale with it.
    cal = vals["calories"] = vals["calories"] + int(round(exercise_kcal))
    return TargetsOut(
        mode=mode,
        **vals,
        exercise_kcal=exercise_kcal,
        protein_g=_r(cal * vals["protein_pct"] / 100 / 4),
        carbs_g=_r(cal * vals["carbs_pct"] / 100 / 4),
        fat_g=_r(cal * vals["fat_pct"] / 100 / 9),
    )


def _check_date(date_for: dt.date) -> None:
    """Backfilling a forgotten meal is normal; logging the future is not.
    One day of headroom absorbs client/server clock and timezone drift."""
    if date_for > dt.date.today() + dt.timedelta(days=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That date hasn't happened yet")


def _own_entry(db: Session, entry_id: int, user: User) -> DiaryEntry:
    entry = db.get(DiaryEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry")
    return entry


def _food_totals(food, amount: float, unit: str) -> dict[str, float | None]:
    """Scale a food's per-100 nutrition to the served amount."""
    if base_unit_of(unit) != food.base_unit:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"'{food.name}' is measured by {'volume' if food.base_unit == 'ml' else 'weight'}",
        )
    factor = amount * UNIT_TO_BASE[unit] / 100.0
    return {
        n: (_r(getattr(food, n) * factor) if getattr(food, n) is not None else None)
        for n in _NUTRIENTS
    }


def _recipe_totals(recipe: Recipe, servings: float) -> dict[str, float | None]:
    per = per_serving_macros(recipe)
    return {
        n: (_r(getattr(per, n) * servings) if getattr(per, n) is not None else None)
        for n in _NUTRIENTS
    }


def _own_recipe(db: Session, recipe_id: int, family_id: int) -> Recipe:
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.family_id != family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe")
    return recipe


# ---- targets (declared before /{entry_id} so the literal path wins) -------------


@router.get("/targets", response_model=TargetsOut)
def get_targets(db: Session = Depends(get_db), user: User = Depends(require_family)):
    return _targets_out(db, user.id, db.get(NutritionTarget, user.id))


@router.put("/targets", response_model=TargetsOut)
def set_targets(
    data: TargetsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Each member sets their own; there is no family-wide split."""
    if data.protein_pct + data.carbs_pct + data.fat_pct != 100:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Protein, carbs, and fat should add up to 100%"
        )
    if data.mode == TargetMode.auto and computed_for(db, user.id) is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Complete your health profile (and log a weight) to use the automatic target",
        )
    row = db.get(NutritionTarget, user.id)
    if row is None:
        row = NutritionTarget(user_id=user.id)
        db.add(row)
    row.mode = data.mode
    row.calories = data.calories
    row.protein_pct = data.protein_pct
    row.carbs_pct = data.carbs_pct
    row.fat_pct = data.fat_pct
    db.commit()
    return _targets_out(db, user.id, row)


# ---- the day view ----------------------------------------------------------------


@router.get("", response_model=DiaryDayOut)
def get_day(
    date: dt.date,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    entries = db.scalars(
        select(DiaryEntry)
        .where(DiaryEntry.user_id == user.id, DiaryEntry.date_for == date)
        .order_by(DiaryEntry.time_of_day.nulls_last(), DiaryEntry.created_at)
    ).all()

    consumed: dict[str, float | None] = {n: None for n in _NUTRIENTS}
    for e in entries:
        for n in _NUTRIENTS:
            v = getattr(e, n)
            if v is not None:
                consumed[n] = _r((consumed[n] or 0.0) + v)

    workouts = db.scalars(
        select(ExerciseEntry)
        .where(ExerciseEntry.user_id == user.id, ExerciseEntry.date_for == date)
        .order_by(ExerciseEntry.time_of_day.nulls_last(), ExerciseEntry.created_at)
    ).all()
    burned = round(sum(w.kcal for w in workouts), 1)

    return DiaryDayOut(
        date=date,
        targets=_targets_out(db, user.id, db.get(NutritionTarget, user.id), burned),
        consumed=RecipeMacros(**consumed),
        entries=[DiaryEntryOut.model_validate(e) for e in entries],
        exercise=[_exercise_out(w) for w in workouts],
        burned=burned,
    )


# ---- entries ----------------------------------------------------------------------


@router.post("", response_model=DiaryEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    data: DiaryEntryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    _check_date(data.date_for)

    if data.recipe_id is not None:
        recipe = _own_recipe(db, data.recipe_id, user.family_id)
        totals = _recipe_totals(recipe, data.amount)
        name, brand, food_id, unit = recipe.name, "", None, "srv"
    else:
        food = _resolve_food(db, user.family_id, data)
        totals = _food_totals(food, data.amount, data.unit)
        name, brand, food_id, unit = food.name, food.brand, food.id, data.unit

    entry = DiaryEntry(
        family_id=user.family_id,
        user_id=user.id,
        date_for=data.date_for,
        slot=data.slot,
        time_of_day=data.time_of_day,
        name=name,
        brand=brand,
        food_id=food_id,
        recipe_id=data.recipe_id,
        amount=data.amount,
        unit=unit,
        label=data.label,
        **totals,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=DiaryEntryOut)
def update_entry(
    entry_id: int,
    data: DiaryEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    entry = _own_entry(db, entry_id, user)
    fields = data.model_fields_set

    if data.date_for is not None:
        _check_date(data.date_for)
        entry.date_for = data.date_for
    if data.slot is not None:
        entry.slot = data.slot
    if "time_of_day" in fields:
        entry.time_of_day = data.time_of_day
    if "label" in fields:
        entry.label = data.label

    if data.amount is not None or data.unit is not None:
        new_amount = data.amount if data.amount is not None else entry.amount
        new_unit = data.unit if data.unit is not None else entry.unit
        if entry.unit == "srv":
            # Recipe entries are measured in servings; there's no other unit
            # to switch them to.
            if data.unit is not None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "This entry is measured in servings"
                )
            recipe = db.get(Recipe, entry.recipe_id) if entry.recipe_id else None
            totals = (
                _recipe_totals(recipe, new_amount)
                if recipe is not None
                else _scaled(entry, new_amount / entry.amount)
            )
        else:
            food = db.get(Food, entry.food_id) if entry.food_id else None
            if food is not None:
                totals = _food_totals(food, new_amount, new_unit)
            else:
                # The food is gone; nutrition is linear in the base amount, so
                # scaling the snapshot is exact.
                old_base = entry.amount * UNIT_TO_BASE.get(entry.unit, 1.0)
                new_base = new_amount * UNIT_TO_BASE.get(new_unit, 1.0)
                totals = _scaled(entry, new_base / old_base)
        entry.amount = new_amount
        entry.unit = new_unit
        for n, v in totals.items():
            setattr(entry, n, v)

    db.commit()
    db.refresh(entry)
    return entry


def _scaled(entry: DiaryEntry, ratio: float) -> dict[str, float | None]:
    return {
        n: (_r(getattr(entry, n) * ratio) if getattr(entry, n) is not None else None)
        for n in _NUTRIENTS
    }


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    db.delete(_own_entry(db, entry_id, user))
    db.commit()
