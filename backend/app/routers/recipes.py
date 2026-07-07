from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_family, require_parent
from app.models import Recipe, User
from app.schemas import RecipeIn, RecipeOut, RecipeUpdate

router = APIRouter(prefix="/recipes", tags=["recipes"])

# Permissions: every family member can browse the recipes; only parents create,
# edit, or delete them (same shape as the grocery list).


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


@router.get("", response_model=list[RecipeOut])
def list_recipes(db: Session = Depends(get_db), user: User = Depends(require_family)):
    """The family recipe box, alphabetical so it reads like a cookbook index."""
    return list(
        db.scalars(
            select(Recipe)
            .where(Recipe.family_id == user.family_id)
            .order_by(func.lower(Recipe.name))
        )
    )


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db), user: User = Depends(require_family)):
    return _get_recipe(db, recipe_id, user.family_id)


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
        calories=data.calories,
        protein_g=data.protein_g,
        carbs_g=data.carbs_g,
        fat_g=data.fat_g,
        ingredients=data.ingredients,
        steps=data.steps,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.patch("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int,
    data: RecipeUpdate,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    recipe = _get_recipe(db, recipe_id, parent.family_id)
    fields = data.model_fields_set  # only touch keys the client actually sent

    if "name" in fields and data.name is not None:
        name = data.name.strip()
        _check_name_free(db, parent.family_id, name, exclude_id=recipe.id)
        recipe.name = name
    if "servings" in fields and data.servings is not None:
        recipe.servings = data.servings
    # Macros are nullable: sending null clears the field, so "in fields" is the
    # right test (a plain None check couldn't tell clear from omit).
    if "calories" in fields:
        recipe.calories = data.calories
    if "protein_g" in fields:
        recipe.protein_g = data.protein_g
    if "carbs_g" in fields:
        recipe.carbs_g = data.carbs_g
    if "fat_g" in fields:
        recipe.fat_g = data.fat_g
    if "ingredients" in fields and data.ingredients is not None:
        recipe.ingredients = data.ingredients
    if "steps" in fields and data.steps is not None:
        recipe.steps = data.steps

    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    db.delete(_get_recipe(db, recipe_id, parent.family_id))
    db.commit()
