from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import inbox
from app.db import get_db
from app.deps import require_family, require_parent
from app.models import GroceryItem, Food, FoodSource, Recipe, RecipeIngredient, User
from app.schemas import (
    RecipeShareOut,
    RecipeToGroceryIn,
    FOOD_NUTRIENTS,
    RecipeIn,
    RecipeIngredientIn,
    RecipeIngredientOut,
    RecipeMacros,
    RecipeOut,
    RecipeUpdate,
)

router = APIRouter(prefix="/recipes", tags=["recipes"])

# Permissions: every family member can browse the recipes; only parents create,
# edit, or delete them (same shape as the grocery list). Nutrition is computed
# from the ingredient lines, never stored — see _serialize.

# The nutrients we total per serving: the whole Nutrition Facts label a food
# carries. Foods store each per 100 g, so a recipe just scales and sums them.
_MACROS = FOOD_NUTRIENTS


def _get_recipe(db: Session, recipe_id: int, family_id: int) -> Recipe:
    """Cross-family ids 404 like they don't exist, so nothing leaks."""
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.family_id != family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe")
    return recipe


def _check_name_free(db: Session, family_id: int, name: str, exclude_id: int | None = None) -> None:
    """One recipe name per family (case-insensitive), so the planner's picker
    never shows two identical "Taco Bowls"."""
    existing = db.scalar(
        select(Recipe).where(
            Recipe.family_id == family_id, func.lower(Recipe.name) == name.lower()
        )
    )
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A recipe with that name already exists")


def _resolve_food(db: Session, family_id: int, line: RecipeIngredientIn) -> Food:
    """Turn an ingredient line's food into a saved `foods` row.

    A custom food (or one a prior recipe already cached) arrives with food_id,
    so we just load it and check it's the family's to use. A USDA/OFF food from
    search or a barcode arrives un-saved: we find the shared cache row by
    (source, source_id) or create it now — this is the "persisted only when used
    in a recipe" contract the foods layer promises."""
    if line.food_id is not None:
        food = db.get(Food, line.food_id)
        # A shared cache row (family_id NULL) is fair game for anyone; a custom
        # food is only its own family's. Anything else 404s — no cross-family peek.
        if food is None or (food.family_id is not None and food.family_id != family_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such food")
        return food

    # No id: a database result being used for the first time. Custom foods are
    # created up front (they always have an id), so an id-less line must be USDA
    # or OFF and must carry the source_id we dedupe on.
    if line.source == FoodSource.custom or not line.source_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That ingredient's food can't be saved"
        )

    cached = db.scalar(
        select(Food).where(
            Food.family_id.is_(None),
            Food.source == line.source,
            Food.source_id == line.source_id,
        )
    )
    if cached is not None:
        return cached

    food = Food(
        family_id=None,  # shared across the install, like other cache rows
        source=line.source,
        source_id=line.source_id,
        name=line.name.strip(),
        brand=line.brand.strip(),
        # The measure family and density ride along from the payload so the row
        # is stored as the client was shown it (FoodOut carries both). Without
        # them a liquid landed here as a mass food and every later conversion
        # started from the wrong side.
        base_unit=line.base_unit,
        density_g_per_ml=line.density_g_per_ml,
        **{n: getattr(line, n) for n in _MACROS},
    )
    db.add(food)
    db.flush()  # assign an id so the ingredient row can reference it
    return food


def _set_ingredients(db: Session, recipe: Recipe, lines: list[RecipeIngredientIn]) -> None:
    """Replace a recipe's ingredient lines with the ones the editor sent. Orphan
    cascade deletes the old rows; positions follow the sent order."""
    recipe.ingredients.clear()
    for i, line in enumerate(lines):
        food = _resolve_food(db, recipe.family_id, line)
        # Either measure family is allowed: a line in cups against a per-100g
        # food converts through the food's density (RecipeIngredient.base_amount
        # -> models.to_base), the same way a diary entry does. A food whose label
        # never stated both readings falls back to water, which the editor says
        # out loud before the cook saves.
        recipe.ingredients.append(
            RecipeIngredient(food_id=food.id, position=i, amount=line.amount, unit=line.unit)
        )


def per_serving_macros(recipe: Recipe) -> RecipeMacros:
    """Total the ingredient lines and divide by servings — the same figures
    _serialize reports, packaged for other features (the dinner planner shows
    tonight's recipe nutrition). A macro stays None until some food supplies
    it, so "unknown" never reads as zero."""
    totals: dict[str, float | None] = {m: None for m in _MACROS}
    for ing in recipe.ingredients:
        factor = ing.grams / 100.0
        for m in _MACROS:
            v = getattr(ing.food, m)
            if v is not None:
                totals[m] = (totals[m] or 0.0) + v * factor
    servings = recipe.servings or 1
    return RecipeMacros(
        **{m: _r(totals[m] / servings) if totals[m] is not None else None for m in _MACROS}
    )


def _serialize(recipe: Recipe, village_names: dict[int, str] | None = None) -> RecipeOut:
    """Build the response, scaling each ingredient's per-100g food macros by its
    grams and totalling them per serving. A macro stays None until some food
    actually supplies it, so "unknown" never masquerades as zero."""
    lines: list[RecipeIngredientOut] = []
    totals: dict[str, float | None] = {m: None for m in _MACROS}

    for ing in recipe.ingredients:
        food = ing.food
        factor = ing.grams / 100.0
        contrib = {
            m: (getattr(food, m) * factor if getattr(food, m) is not None else None)
            for m in _MACROS
        }
        for m in _MACROS:
            if contrib[m] is not None:
                totals[m] = (totals[m] or 0.0) + contrib[m]
        lines.append(
            RecipeIngredientOut(
                id=ing.id,
                food_id=ing.food_id,
                source=food.source,
                source_id=food.source_id,
                name=food.name,
                brand=food.brand,
                amount=ing.amount,
                unit=ing.unit,
                grams=round(ing.grams, 2),
                base_unit=food.base_unit,
                density_g_per_ml=food.density_g_per_ml,
                **{m: _r(contrib[m]) for m in _MACROS},
            )
        )

    servings = recipe.servings or 1
    per_serving = RecipeMacros(
        **{m: _r(totals[m] / servings) if totals[m] is not None else None for m in _MACROS}
    )
    # Where it sits on village shelves, for the "shared" indicator. Shares are
    # live pointers, so this is also the owner's handle for unsharing.
    from sqlalchemy.orm import object_session

    from app.models import Village

    shared_to = []
    session = object_session(recipe)
    if session is not None and recipe.village_shares:
        names = village_names
        if names is None:  # single-recipe callers; list_recipes batches this
            names = {
                v.id: v.name
                for v in session.scalars(
                    select(Village).where(
                        Village.id.in_([sh.village_id for sh in recipe.village_shares])
                    )
                )
            }
        shared_to = [
            RecipeShareOut(
                share_id=sh.id, village_id=sh.village_id, village_name=names.get(sh.village_id, "")
            )
            for sh in recipe.village_shares
        ]
    return RecipeOut(
        id=recipe.id,
        name=recipe.name,
        servings=recipe.servings,
        steps=recipe.steps,
        ingredients=lines,
        per_serving=per_serving,
        shared_to=shared_to,
        provenance=recipe.provenance,
    )


def _r(v: float | None) -> float | None:
    return round(v, 1) if v is not None else None


@router.get("", response_model=list[RecipeOut])
def list_recipes(db: Session = Depends(get_db), user: User = Depends(require_family)):
    """The family recipe box, alphabetical so it reads like a cookbook index."""
    recipes = db.scalars(
        select(Recipe)
        .options(
            # Same shape meals.py uses: everything _serialize touches rides
            # along, instead of one lazy round-trip per ingredient and share.
            selectinload(Recipe.ingredients).joinedload(RecipeIngredient.food),
            selectinload(Recipe.village_shares),
        )
        .where(Recipe.family_id == user.family_id)
        .order_by(func.lower(Recipe.name))
    ).all()
    # One name lookup for every village any recipe is shared to; _serialize
    # would otherwise run it per recipe.
    from app.models import Village

    village_ids = {sh.village_id for r in recipes for sh in r.village_shares}
    names = (
        {
            v.id: v.name
            for v in db.scalars(select(Village).where(Village.id.in_(village_ids)))
        }
        if village_ids
        else {}
    )
    return [_serialize(r, village_names=names) for r in recipes]


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db), user: User = Depends(require_family)):
    return _serialize(_get_recipe(db, recipe_id, user.family_id))


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(
    data: RecipeIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    name = data.name.strip()
    _check_name_free(db, parent.family_id, name)
    recipe = Recipe(
        family_id=parent.family_id,
        name=name,
        servings=data.servings,
        steps=data.steps,
    )
    db.add(recipe)
    _set_ingredients(db, recipe, data.ingredients)
    db.commit()
    db.refresh(recipe)
    inbox.record_all(
        db, inbox.other_adults(db, parent), "recipe",
        f"{parent.display_name.split()[0]} added a recipe: {recipe.name}",
    )
    return _serialize(recipe)


@router.patch("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int,
    data: RecipeUpdate,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    recipe = _get_recipe(db, recipe_id, parent.family_id)
    before_name = recipe.name

    # Snapshot before applying: a re-save of identical content is not an edit,
    # so it must not repeat the "edited a recipe" Inbox line.
    def _snapshot():
        return (
            recipe.name,
            recipe.servings,
            recipe.steps,
            [(i.food_id, i.position, i.amount, i.unit) for i in recipe.ingredients],
        )

    before = _snapshot()
    fields = data.model_fields_set  # only touch keys the client actually sent

    if "name" in fields and data.name is not None:
        name = data.name.strip()
        _check_name_free(db, parent.family_id, name, exclude_id=recipe.id)
        recipe.name = name
    if "servings" in fields and data.servings is not None:
        recipe.servings = data.servings
    if "steps" in fields and data.steps is not None:
        recipe.steps = data.steps
    # Sending `ingredients` replaces the whole list; omitting it leaves them.
    if "ingredients" in fields and data.ingredients is not None:
        _set_ingredients(db, recipe, data.ingredients)

    db.commit()
    db.refresh(recipe)
    if _snapshot() != before:
        inbox.record_all(
            db, inbox.other_adults(db, parent), "recipe",
            f"{parent.display_name.split()[0]} edited a recipe: {recipe.name}",
            f'Was "{before_name}"' if recipe.name != before_name else "",
        )
    return _serialize(recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    recipe = _get_recipe(db, recipe_id, parent.family_id)
    name = recipe.name
    db.delete(recipe)
    db.commit()
    inbox.record_all(
        db, inbox.other_adults(db, parent), "recipe",
        f"{parent.display_name.split()[0]} removed a recipe: {name}",
    )

# One line on the grocery list per ingredient: "Ground beef, 85/15 · 200 g".
# Titles are capped at the column's 120 chars.
def _grocery_title(name: str, amount: float, unit: str) -> str:
    qty = f"{amount:g} {unit}"
    room = 120 - len(qty) - 3
    return f"{name[:room]} · {qty}"


@router.post("/{recipe_id}/grocery", response_model=dict)
def send_to_grocery(
    recipe_id: int,
    data: RecipeToGroceryIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Push a recipe's ingredients onto the grocery list in one tap — the
    close of the menu loop: plan the night, send what it needs to the store
    list. list_id picks the store; None lands them in Unsorted."""
    recipe = _get_recipe(db, recipe_id, parent.family_id)
    if not recipe.ingredients:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This recipe has no ingredients yet")
    if data.list_id is not None:
        from app.routers.grocery import _check_list

        _check_list(db, data.list_id, parent.family_id)

    for ing in recipe.ingredients:
        db.add(
            GroceryItem(
                family_id=parent.family_id,
                title=_grocery_title(ing.food.name, ing.amount, ing.unit),
                list_id=data.list_id,
            )
        )
    db.commit()
    n = len(recipe.ingredients)
    detail = f"{n} ingredient{'' if n == 1 else 's'}"
    if data.list_id is not None:
        from app.routers.grocery import _store_name

        detail += f" · {_store_name(db, data.list_id, parent.family_id)}"
    inbox.record_all(
        db, inbox.other_adults(db, parent), "grocery",
        f"{parent.display_name.split()[0]} sent {recipe.name} to groceries",
        detail,
    )
    return {"added": n}
