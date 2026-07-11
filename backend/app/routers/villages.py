"""Villages: private circles of linked families.

A village is invitation-only plumbing between households on the same install.
Nothing is discoverable — no directory, no search, no friend requests — and a
village you don't belong to 404s exactly like it doesn't exist. What crosses
the family wall is deliberately tiny (a shared recipe shelf and opt-in
mood/status, later slices); boards, kitchens, and calendars never do.

Invite codes: 8 characters from an alphabet without lookalikes (no 0/O/1/I/L),
so a code survives being read over the phone. Only the SHA-256 of a code is
stored — a database read never exposes a live door key — and the plaintext is
returned exactly once, by the endpoint that minted it. One active code per
village, single-use (a successful join consumes it), regenerable by any member
family's admin. Wrong, expired, and never-existed codes all answer with the
same 404, and guesses are throttled like failed logins, so probing reveals
nothing about which villages exist.
"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import throttle
from app.invitecodes import hash_code, mint_code, normalize, pretty, still_valid
from app.db import get_db
from app.deps import require_admin, require_family, require_parent
from app.models import (
    Family,
    Food,
    FoodServing,
    FoodSource,
    Recipe,
    RecipeIngredient,
    Role,
    User,
    Village,
    VillageFamily,
    VillageRecipe,
)
from app.schemas import (
    FOOD_NUTRIENTS,
    MoodOut,
    RecipeOut,
    SharedIngredientOut,
    SharedRecipeDetailOut,
    SharedRecipeOut,
    ShareRecipeIn,
    VillageCheckOut,
    VillageCreatedOut,
    VillageFamilyOut,
    VillageIn,
    VillageInviteOut,
    VillageJoinIn,
    VillageOut,
    VillageParentOut,
)

router = APIRouter(prefix="/villages", tags=["villages"])

INVITE_TTL = dt.timedelta(hours=48)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _invite_active(village: Village, now: dt.datetime) -> bool:
    return village.invite_code_hash is not None and still_valid(
        village.invite_expires_at, now
    )


def _member_village(db: Session, village_id: int, family_id: int) -> Village:
    """A village this family doesn't belong to 404s like it doesn't exist."""
    village = db.get(Village, village_id)
    membership = (
        None
        if village is None
        else db.scalar(
            select(VillageFamily).where(
                VillageFamily.village_id == village_id,
                VillageFamily.family_id == family_id,
            )
        )
    )
    if village is None or membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such village")
    return village


def _village_out(db: Session, village: Village, viewer_family_id: int) -> VillageOut:
    rows = db.execute(
        select(VillageFamily, Family)
        .join(Family, Family.id == VillageFamily.family_id)
        .where(VillageFamily.village_id == village.id)
        .order_by(VillageFamily.joined_at, VillageFamily.id)
    ).all()
    # The faces of the village: every member family's PARENTS. Children are
    # never shown across the family wall, whatever their birthdate says.
    # A parent who opted in (village_presence) also shares today's mood
    # (unless hidden — hidden reads exactly like unset). Statuses stay home.
    from app.models import Mood

    parents_by_family: dict[int, list[VillageParentOut]] = {}
    family_ids = [family.id for _, family in rows]
    if family_ids:
        parents = db.scalars(
            select(User)
            .where(User.family_id.in_(family_ids), User.role == Role.parent)
            .order_by(User.created_at, User.id)
        ).all()
        today = dt.date.today()
        sharer_ids = [u.id for u in parents if u.village_presence]
        moods = {
            m.user_id: m
            for m in db.scalars(
                select(Mood).where(Mood.date_for == today, Mood.user_id.in_(sharer_ids))
            )
        } if sharer_ids else {}
        # Reading streaks cross the wall only by their own opt-in, separate
        # from mood presence; the number is all that travels.
        from app.routers.verses import streaks_for

        streaks = streaks_for(
            db,
            [u.id for u in parents if u.share_verse_streak and u.verse_streak_enabled],
            today,
        )
        for user in parents:
            mood = moods.get(user.id)
            sharing = user.village_presence
            parents_by_family.setdefault(user.family_id, []).append(
                VillageParentOut(
                    id=user.id,
                    display_name=user.display_name,
                    avatar_updated_at=user.avatar_updated_at,
                    mood=(
                        MoodOut.model_validate(mood)
                        if sharing and mood is not None and not mood.hidden
                        else None
                    ),
                    verse_streak=streaks.get(user.id) or None,
                )
            )
    active = _invite_active(village, _utcnow())
    return VillageOut(
        id=village.id,
        name=village.name,
        created_at=village.created_at,
        families=[
            VillageFamilyOut(
                id=family.id,
                name=family.name,
                joined_at=vf.joined_at,
                parents=parents_by_family.get(family.id, []),
            )
            for vf, family in rows
        ],
        invite_active=active,
        invite_expires_at=village.invite_expires_at if active else None,
        is_creator=village.created_by_family_id == viewer_family_id,
    )


def _family_in_a_village(db: Session, family_id: int) -> bool:
    return (
        db.scalar(select(VillageFamily).where(VillageFamily.family_id == family_id))
        is not None
    )


@router.get("", response_model=list[VillageOut])
def list_villages(db: Session = Depends(get_db), user: User = Depends(require_family)):
    """The family's villages. Any member may look; only admins change them."""
    villages = db.scalars(
        select(Village)
        .join(VillageFamily, VillageFamily.village_id == Village.id)
        .where(VillageFamily.family_id == user.family_id)
        .order_by(Village.created_at, Village.id)
    ).all()
    return [_village_out(db, v, user.family_id) for v in villages]


@router.post("", response_model=VillageCreatedOut, status_code=status.HTTP_201_CREATED)
def create_village(
    data: VillageIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Found a village: the creating family is its first member, and the
    response carries the invite code — the only time it is ever shown.
    A family may JOIN many villages but FOUND only one."""
    founded = db.scalar(
        select(Village).where(Village.created_by_family_id == admin.family_id)
    )
    if founded is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Your family already created a village"
        )
    code = mint_code()
    village = Village(
        name=data.name.strip(),
        created_by_family_id=admin.family_id,
        invite_code_hash=hash_code(code),
        invite_expires_at=_utcnow() + INVITE_TTL,
    )
    db.add(village)
    db.flush()
    db.add(VillageFamily(village_id=village.id, family_id=admin.family_id))
    db.commit()
    db.refresh(village)
    base = _village_out(db, village, admin.family_id)
    return VillageCreatedOut(**base.model_dump(), invite_code=pretty(code))


def _village_for_code(db: Session, raw: str, throttle_user: str) -> Village:
    """The throttled door: turn a submitted code into its village, or record
    a failure and answer the uniform 404."""
    key = f"village-join:{throttle_user}"
    if throttle.too_many_failures(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later."
        )
    code = normalize(raw)
    village = (
        db.scalar(select(Village).where(Village.invite_code_hash == hash_code(code)))
        if code
        else None
    )
    if village is None or not _invite_active(village, _utcnow()):
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That code isn't valid")
    return village


@router.post("/join/check", response_model=VillageCheckOut)
def check_join_code(
    data: VillageJoinIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """What would this code join? Drives the "Join <name>?" confirmation
    without consuming the code. Same throttle bucket as joining."""
    village = _village_for_code(db, data.code, admin.username)
    names = db.scalars(
        select(Family.name)
        .join(VillageFamily, VillageFamily.family_id == Family.id)
        .where(VillageFamily.village_id == village.id)
        .order_by(VillageFamily.joined_at, VillageFamily.id)
    ).all()
    return VillageCheckOut(name=village.name, families=list(names))


@router.post("/join", response_model=VillageOut)
def join_village(
    data: VillageJoinIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Join with an invite code. Wrong, expired, and nonexistent codes are one
    indistinguishable 404; attempts are throttled like failed logins."""
    village = _village_for_code(db, data.code, admin.username)

    # A valid code in hand means the village's existence isn't a secret from
    # this caller, so this refusal can say what it is. The code stays live —
    # it was minted for someone else.
    if db.scalar(
        select(VillageFamily).where(
            VillageFamily.village_id == village.id,
            VillageFamily.family_id == admin.family_id,
        )
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Your family is already in this village"
        )

    db.add(VillageFamily(village_id=village.id, family_id=admin.family_id))
    # Single-use: the join consumes the code.
    village.invite_code_hash = None
    village.invite_expires_at = None
    db.commit()
    throttle.clear(f"village-join:{admin.username}")
    db.refresh(village)
    return _village_out(db, village, admin.family_id)


@router.post("/{village_id}/invite", response_model=VillageInviteOut)
def regenerate_invite(
    village_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Mint a fresh invite code (killing any previous one). Codes can never be
    re-shown — losing one costs a regenerate, never a lookup."""
    village = _member_village(db, village_id, admin.family_id)
    code = mint_code()
    village.invite_code_hash = hash_code(code)
    village.invite_expires_at = _utcnow() + INVITE_TTL
    db.commit()
    return VillageInviteOut(
        invite_code=pretty(code), invite_expires_at=village.invite_expires_at
    )


@router.delete("/{village_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_village(
    village_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """The founding family dissolves the village for everyone — the answer
    to stale villages nobody tends. Other families may only leave."""
    village = _member_village(db, village_id, admin.family_id)
    if village.created_by_family_id != admin.family_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the founding family can delete the village"
        )
    db.delete(village)  # memberships and shelf rows cascade away
    db.commit()


@router.delete("/{village_id}/membership", status_code=status.HTTP_204_NO_CONTENT)
def leave_village(
    village_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Leave: the family's shelf entries in this village go with it (saved
    copies in other kitchens are independent rows and survive). The last
    family out turns off the lights — the village row is deleted."""
    village = _member_village(db, village_id, admin.family_id)
    db.execute(
        delete(VillageRecipe).where(
            VillageRecipe.village_id == village.id,
            VillageRecipe.family_id == admin.family_id,
        )
    )
    db.execute(
        delete(VillageFamily).where(
            VillageFamily.village_id == village.id,
            VillageFamily.family_id == admin.family_id,
        )
    )
    remaining = db.scalar(
        select(func.count())
        .select_from(VillageFamily)
        .where(VillageFamily.village_id == village.id)
    )
    if remaining == 0:
        db.delete(village)
    db.commit()


# ---- the recipe shelf ---------------------------------------------------------------
# What a village actually shares. A shelf entry is a POINTER at the owning
# family's recipe (their edits show live on the shelf); "Save a copy" is what
# puts an independent snapshot in another family's kitchen — unsharing,
# leaving, or deleting never reaches into anyone else's recipe box.


def _my_village_ids(db: Session, family_id: int):
    return select(VillageFamily.village_id).where(VillageFamily.family_id == family_id)


def _shelf_row(
    db: Session,
    share: VillageRecipe,
    recipe: Recipe,
    village_name: str,
    family_name: str,
    viewer_family: int,
) -> SharedRecipeOut:
    from app.routers.recipes import per_serving_macros

    sharer = db.get(User, share.shared_by_id) if share.shared_by_id else None
    return SharedRecipeOut(
        share_id=share.id,
        village_id=share.village_id,
        village_name=village_name,
        family_id=share.family_id,
        family_name=family_name,
        shared_by=sharer.display_name.split()[0] if sharer else None,
        is_own=share.family_id == viewer_family,
        name=recipe.name,
        servings=recipe.servings,
        per_serving=per_serving_macros(recipe),
        created_at=share.created_at,
        updated_at=recipe.updated_at,
    )


def _get_share(db: Session, share_id: int, viewer_family: int) -> VillageRecipe:
    """A shelf entry in one of the viewer's villages; anything else 404s."""
    share = db.get(VillageRecipe, share_id)
    if share is None or share.village_id not in set(
        db.scalars(_my_village_ids(db, viewer_family))
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared recipe")
    return share


@router.get("/shelf", response_model=list[SharedRecipeOut])
def shelf(db: Session = Depends(get_db), user: User = Depends(require_family)):
    rows = db.execute(
        select(VillageRecipe, Recipe, Village.name, Family.name)
        .join(Recipe, Recipe.id == VillageRecipe.recipe_id)
        .join(Village, Village.id == VillageRecipe.village_id)
        .join(Family, Family.id == VillageRecipe.family_id)
        .where(VillageRecipe.village_id.in_(_my_village_ids(db, user.family_id)))
        .order_by(VillageRecipe.created_at.desc(), VillageRecipe.id.desc())
    ).all()
    return [
        _shelf_row(db, share, recipe, vname, fname, user.family_id)
        for share, recipe, vname, fname in rows
    ]


@router.get("/shelf/{share_id}", response_model=SharedRecipeDetailOut)
def shared_recipe_detail(
    share_id: int, db: Session = Depends(get_db), user: User = Depends(require_family)
):
    share = _get_share(db, share_id, user.family_id)
    recipe = db.get(Recipe, share.recipe_id)
    village = db.get(Village, share.village_id)
    family = db.get(Family, share.family_id)
    base = _shelf_row(db, share, recipe, village.name, family.name, user.family_id)
    lines = [
        SharedIngredientOut(
            name=ing.food.name,
            brand=ing.food.brand,
            amount=ing.amount,
            unit=ing.unit,
            grams=round(ing.grams, 2),
            **{
                n: (
                    round(getattr(ing.food, n) * ing.grams / 100.0, 1)
                    if getattr(ing.food, n) is not None
                    else None
                )
                for n in FOOD_NUTRIENTS
            },
        )
        for ing in recipe.ingredients
    ]
    return SharedRecipeDetailOut(
        **base.model_dump(), steps=recipe.steps, ingredients=lines
    )


@router.post(
    "/{village_id}/recipes",
    response_model=SharedRecipeOut,
    status_code=status.HTTP_201_CREATED,
)
def share_recipe(
    village_id: int,
    data: ShareRecipeIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Put one of the family's own recipes on the village shelf."""
    from app.routers.recipes import _get_recipe

    village = _member_village(db, village_id, parent.family_id)
    recipe = _get_recipe(db, data.recipe_id, parent.family_id)
    if db.scalar(
        select(VillageRecipe).where(
            VillageRecipe.village_id == village.id, VillageRecipe.recipe_id == recipe.id
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already on the shelf")
    share = VillageRecipe(
        village_id=village.id,
        recipe_id=recipe.id,
        family_id=parent.family_id,
        shared_by_id=parent.id,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    family = db.get(Family, parent.family_id)
    return _shelf_row(db, share, recipe, village.name, family.name, parent.family_id)


@router.delete("/shelf/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def unshare_recipe(
    share_id: int, db: Session = Depends(get_db), parent: User = Depends(require_parent)
):
    """Take an own-family entry off the shelf. Copies others saved survive."""
    share = _get_share(db, share_id, parent.family_id)
    if share.family_id != parent.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared recipe")
    db.delete(share)
    db.commit()


def _matching_custom_food(db: Session, family_id: int, src: Food) -> Food | None:
    """An existing custom food of the destination family that is the same
    thing: same name/brand/base unit AND all ten nutrients equal. Name alone
    could silently swap in different nutrition; this keeps repeated copies
    idempotent without ever lying."""
    from sqlalchemy import func

    candidates = db.scalars(
        select(Food).where(
            Food.family_id == family_id,
            func.lower(Food.name) == src.name.lower(),
            func.lower(Food.brand) == src.brand.lower(),
            Food.base_unit == src.base_unit,
        )
    )
    for cand in candidates:
        if all(getattr(cand, n) == getattr(src, n) for n in FOOD_NUTRIENTS):
            return cand
    return None


@router.post(
    "/shelf/{share_id}/copy", response_model=RecipeOut, status_code=status.HTTP_201_CREATED
)
def save_a_copy(
    share_id: int, db: Session = Depends(get_db), parent: User = Depends(require_parent)
):
    """Adopt a shared recipe: an independent snapshot in the family's own
    kitchen. Shared-cache foods are reused as-is; the sharing family's custom
    foods are copied in (servings and all), deduped against existing ones."""
    from sqlalchemy import func

    from app.routers.recipes import _serialize

    share = _get_share(db, share_id, parent.family_id)
    if share.family_id == parent.family_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "It's already your recipe — no copy needed",
        )
    src = db.get(Recipe, share.recipe_id)

    # Copying must never fail on a name collision: suffix until free.
    name = src.name
    n = 2
    while db.scalar(
        select(Recipe).where(
            Recipe.family_id == parent.family_id, func.lower(Recipe.name) == name.lower()
        )
    ):
        suffix = f" ({n})"
        name = src.name[: 120 - len(suffix)] + suffix
        n += 1

    sharer = db.get(User, share.shared_by_id) if share.shared_by_id else None
    src_family = db.get(Family, share.family_id)
    stamp = dt.datetime.now().strftime("%b %-d, %-I:%M %p")
    provenance = (
        f"Copy of {src.name} shared by "
        f"{sharer.display_name.split()[0] if sharer else src_family.name} "
        f"from {src_family.name} on {stamp}"
    )[:200]
    copy = Recipe(
        family_id=parent.family_id,
        name=name,
        servings=src.servings,
        steps=src.steps,
        provenance=provenance,
    )
    db.add(copy)
    db.flush()

    for ing in src.ingredients:
        food = ing.food
        if food.family_id is not None:  # the sharer's custom food: bring it over
            existing = _matching_custom_food(db, parent.family_id, food)
            if existing is None:
                existing = Food(
                    family_id=parent.family_id,
                    source=FoodSource.custom,
                    source_id=None,
                    name=food.name,
                    brand=food.brand,
                    base_unit=food.base_unit,
                    **{n_: getattr(food, n_) for n_ in FOOD_NUTRIENTS},
                )
                db.add(existing)
                db.flush()
                for serving in food.servings:
                    db.add(
                        FoodServing(
                            food_id=existing.id,
                            name=serving.name,
                            grams=serving.grams,
                            position=serving.position,
                        )
                    )
            food = existing
        db.add(
            RecipeIngredient(
                recipe_id=copy.id,
                food_id=food.id,
                position=ing.position,
                amount=ing.amount,
                unit=ing.unit,
            )
        )
    db.commit()
    db.refresh(copy)
    return _serialize(copy)
