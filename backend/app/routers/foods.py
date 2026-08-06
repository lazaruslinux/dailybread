import datetime as dt
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import food_health, foods_api
from app.config import settings
from app.db import get_db
from app.deps import require_adult, require_family, require_parent
from app.models import (
    DiaryEntry,
    Food,
    FoodServing,
    FoodSource,
    Recipe,
    RecipeIngredient,
    User,
    Village,
)
from app.schemas import (
    FOOD_NUTRIENTS,
    FoodHealthOut,
    FoodIn,
    FoodOut,
    FoodServingOut,
    HealthAssessmentOut,
    RecipeShareOut,
    SavedFoodIn,
)

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
        base_unit=r.base_unit,
        # The client previews a cross-family portion with this, and sends it
        # back when the food is first persisted, so both sides agree.
        density_g_per_ml=r.density_g_per_ml,
        servings=_result_servings(r, FoodServingOut),
        # The health-check fields ride along on the result but aren't part of
        # FOOD_NUTRIENTS (they never enter diary snapshots or recipe macros).
        ingredients_text=r.ingredients_text or None,
        added_sugar_g=r.added_sugar_g,
        additives=r.additives or None,
        nova_group=r.nova_group,
        **{n: getattr(r, n) for n in FOOD_NUTRIENTS},
    )


def _result_servings(r: foods_api.FoodResult, cls):
    """The label serving as a structured portion, so an ingredient line can
    default to "1 serving" the way it does for custom foods. Empty when the
    source gave no measurable size."""
    if r.serving_amount is None:
        return []
    unit = "mL" if r.base_unit == "ml" else "g"
    name = r.serving or f"1 serving ({r.serving_amount:g} {unit})"
    return [cls(name=name, grams=r.serving_amount)]


def _apply_custom_food(food: Food, data: FoodIn) -> None:
    """Set a custom food's nutrition and servings from the create/edit payload.
    Values are entered per the chosen serving (basis_index); we store per-100 of
    the food's base unit (grams for a solid, millilitres for a liquid) so it sits
    alongside USDA/OFF foods and feeds the recipe math. A serving of B base units
    means per-100 = entered * 100 / B."""
    food.name = data.name.strip()
    food.brand = data.brand.strip()
    food.folder = (data.folder or "").strip() or None
    food.source_id = data.barcode
    food.base_unit = data.base_unit
    # Carried through from a scan; nothing here derives one from the servings.
    food.density_g_per_ml = data.density_g_per_ml
    factor = 100.0 / data.servings[data.basis_index].grams
    for n in FOOD_NUTRIENTS:
        entered = getattr(data, n)
        setattr(food, n, round(entered * factor, 2) if entered is not None else None)
    food.servings = [
        FoodServing(name=s.name.strip(), grams=s.grams, position=i)
        for i, s in enumerate(data.servings)
    ]
    # Health-check label data, stored as given (already per-100, not per basis
    # serving). Carries a scanned food's ingredients through "save as custom food"
    # so a later scan of the same barcode still judges the real label.
    food.ingredients_text = (data.ingredients_text or "").strip() or None
    food.added_sugar_g = data.added_sugar_g
    food.additives = (data.additives or "").strip() or None
    food.nova_group = data.nova_group


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
    user: User = Depends(require_adult),
):
    """Search the food database (USDA FoodData Central), server-side. Adult
    only, like every diary surface that uses the picker: minors have no
    nutrition area, so they get no third-party food lookups either."""
    try:
        results = _searched(q)
    except foods_api.FoodApiError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return [_result_out(r) for r in results]


_RECENT_LIMIT = 8


@router.get("/recent", response_model=list[FoodOut])
def recent_foods(db: Session = Depends(get_db), user: User = Depends(require_adult)):
    """The picker's quick-add shelf: foods this member logged in their diary
    lately, then foods the family's recipes recently used, deduped and newest
    first. Personal picks outrank the family's — what YOU eat several times a
    week is the whole point of the shelf."""
    mine = db.execute(
        select(DiaryEntry.food_id, func.max(DiaryEntry.created_at).label("last"))
        .where(DiaryEntry.user_id == user.id, DiaryEntry.food_id.isnot(None))
        .group_by(DiaryEntry.food_id)
        .order_by(func.max(DiaryEntry.created_at).desc())
        .limit(_RECENT_LIMIT * 2)
    ).all()
    cooked = db.execute(
        select(RecipeIngredient.food_id, func.max(RecipeIngredient.id).label("last"))
        .join(Recipe, RecipeIngredient.recipe_id == Recipe.id)
        .where(Recipe.family_id == user.family_id, RecipeIngredient.food_id.isnot(None))
        .group_by(RecipeIngredient.food_id)
        .order_by(func.max(RecipeIngredient.id).desc())
        .limit(_RECENT_LIMIT * 2)
    ).all()

    ordered_ids: list[int] = []
    for food_id, _ in [*mine, *cooked]:
        if food_id not in ordered_ids:
            ordered_ids.append(food_id)
        if len(ordered_ids) == _RECENT_LIMIT:
            break
    if not ordered_ids:
        return []
    rows = db.scalars(
        select(Food).where(Food.id.in_(ordered_ids)).options(selectinload(Food.servings))
    ).all()
    by_id = {f.id: f for f in rows}
    return [by_id[i] for i in ordered_ids if i in by_id]


# ---- saved foods ---------------------------------------------------------------
# The family's pinned foods: a scan or search result bookmarked for quick
# re-use. The pin points at the shared cache row (find-or-created exactly like
# a recipe ingredient), so unpinning never loses data a snapshot relies on.


@router.get("/saved", response_model=list[FoodOut])
def saved_foods(db: Session = Depends(get_db), user: User = Depends(require_family)):
    from app.models import SavedFood

    pins = (
        db.scalars(
            select(SavedFood)
            .options(selectinload(SavedFood.food).selectinload(Food.servings))
            .where(SavedFood.family_id == user.family_id)
            .order_by(SavedFood.created_at.desc())
        )
        .unique()
        .all()
    )
    return [pin.food for pin in pins]


@router.post("/saved", response_model=FoodOut, status_code=status.HTTP_201_CREATED)
def save_food(
    data: SavedFoodIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_parent),
):
    # The shelf is family-shared: everyone browses it in the Kitchen, so
    # changing it is a parent's move (same rule as recipes and groceries).
    from app.models import SavedFood
    from app.routers.recipes import _resolve_food
    from app.schemas import RecipeIngredientIn

    food = _resolve_food(
        db, user.family_id, RecipeIngredientIn(**data.model_dump(), amount=1, unit="g")
    )
    existing = db.scalar(
        select(SavedFood).where(
            SavedFood.family_id == user.family_id, SavedFood.food_id == food.id
        )
    )
    if existing is None:
        db.add(SavedFood(family_id=user.family_id, food_id=food.id, saved_by_id=user.id))
        db.commit()
    return food


@router.delete("/saved/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_food(
    food_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_parent),
):
    from app.models import SavedFood

    pin = db.scalar(
        select(SavedFood).where(
            SavedFood.family_id == user.family_id, SavedFood.food_id == food_id
        )
    )
    if pin is not None:
        db.delete(pin)
        db.commit()


def _heal_liquid_unit(db: Session, food: Food) -> None:
    """A barcode scanned before the liquid-unit fix can sit in the shared cache
    as grams though its serving names a volume ("2 Tbsp (30mL)"). Flip such a
    cached row to millilitres in place on the next scan: the stored numbers are
    per-100 either way and FoodServing.grams already holds the right count of
    the base unit, so only the unit label changes. The heal fires only on an
    unambiguous metric/fl-oz mark in the name: has_mass=True suppresses the
    bare cup/spoon tier, here because such a name is unproven either way (a
    cached "0.75 cup" of cereal must never become millilitres; the real pre-fix
    casualties all carry a metric parenthetical). Barcode cache rows only
    (family_id None, USDA/OFF source); a family's own custom food is never
    touched."""
    if (
        food.base_unit != "g"
        or food.family_id is not None
        or food.source == FoodSource.custom
    ):
        return
    if any(
        foods_api._volume_from_text(s.name, has_mass=True) is not None
        for s in food.servings
    ):
        food.base_unit = "ml"
        db.commit()


def _heal_serving_names(db: Session, food: Food) -> None:
    """A barcode scanned before the serving-name fix can sit in the shared cache
    with a raw USDA serving name: a scraped label header wrapping a UNECE unit
    code ("Amount/serving (120 MLT)"). Rewrite each cached serving name to its
    display form ("120 mL") in place on the next scan. Must run BEFORE
    _heal_liquid_unit: a name healed to "120 mL" newly carries the unambiguous
    metric mark the liquid heal requires, so a wrong-unit row gets both heals in
    one scan. Barcode cache rows only (family_id None, USDA/OFF source); a
    family's own custom food is never touched."""
    if food.family_id is not None or food.source == FoodSource.custom:
        return
    changed = False
    for s in food.servings:
        cleaned = foods_api._clean_serving_name(s.name)
        if cleaned != s.name:
            s.name = cleaned
            changed = True
    if changed:
        db.commit()


# How long a shared-cache row is trusted before the next scan refetches it. The
# sources correct their own records (Open Food Facts fixed a syrup whose energy
# was per 100 g beside carbs per 100 mL), and a cache row that never refetched
# served that mistake to the family forever.
_CACHE_TTL = dt.timedelta(days=30)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _cache_is_stale(food: Food) -> bool:
    """NULL fetched_at counts as stale: those rows predate the column, so their
    age is unknown and the next scan is the moment to find out."""
    if food.fetched_at is None:
        return True
    stamped = food.fetched_at
    if stamped.tzinfo is None:  # SQLite hands tz-aware columns back naive
        stamped = stamped.replace(tzinfo=dt.timezone.utc)
    return _utcnow() - stamped > _CACHE_TTL


def _refresh_cached(db: Session, food: Food) -> bool:
    """Re-read a stale shared-cache row from its source and overwrite it in
    place. True means the row was settled this scan — refreshed, or confirmed
    gone upstream. False means the network wouldn't answer and the row is
    untouched, so the next scan tries again.

    Sources are asked in the same order and with the same error tolerance as
    the first fetch: USDA (label-accurate for US products) then Open Food
    Facts, and a USDA outage is a miss rather than a failure."""
    code = food.source_id or ""
    usda_answered = True
    try:
        result = foods_api.lookup_barcode_usda(code, settings.usda_api_key)
    except foods_api.FoodApiError:
        result, usda_answered = None, False
    if result is None:
        try:
            result = foods_api.lookup_barcode_off(code)
        except foods_api.FoodApiError:
            return False
    if result is None:
        # Both sources say the product is gone. Stamp it anyway and keep serving
        # the copy we have: re-asking on every scan for a month buys nothing.
        if not usda_answered:
            return False
        food.fetched_at = _utcnow()
        db.commit()
        return True

    # A diary entry snapshots its own nutrition at log time, so correcting a
    # food here never rewrites what a past day says anyone ate.
    food.source = FoodSource(result.source)
    food.name = result.name
    food.brand = result.brand
    food.base_unit = result.base_unit
    food.density_g_per_ml = result.density_g_per_ml
    for n in FOOD_NUTRIENTS:
        setattr(food, n, getattr(result, n))
    # Same convention as the first cache write: "" for an absent list, never
    # NULL, so the row reads as enriched rather than never-fetched.
    food.ingredients_text = result.ingredients_text
    food.added_sugar_g = result.added_sugar_g
    food.additives = result.additives
    food.nova_group = result.nova_group
    food.servings = [
        FoodServing(name=srv.name, grams=srv.grams, position=0)
        for srv in _result_servings(result, FoodServingOut)
    ]
    food.fetched_at = _utcnow()
    db.commit()
    db.refresh(food)
    return True


def _resolve_barcode(db: Session, user: User, code: str) -> Food:
    """Resolve a scanned barcode to a stored Food, checking home before asking
    the internet: first the family's own custom foods (a product they entered by
    hand after an unknown scan), then foods already cached from earlier lookups,
    and only then the internet — USDA's Branded dataset first (label-accurate for
    US products), Open Food Facts as the fallback. Scanning something you've
    scanned before never leaves the server. Raises HTTPException on a bad code,
    an unreachable database, or no match."""
    # Real printed codes are 8 digits at the shortest (EAN-8; UPC-E includes its
    # number-system and check digits) and 14 at the longest (GTIN-14).
    if not code.isdigit() or not (8 <= len(code) <= 14):
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

    # Barcode-cached usda rows keep the scanned code in source_id; search-
    # cached usda rows keep the fdcId. Barcodes run 8-14 digits, fdcIds are 7
    # today — an 8-digit EAN-8 could in principle collide once fdcIds reach 8
    # digits, at the cost of one wrong cache hit on a rare code shape; worth a
    # source_id prefix (and migration) only if that day comes.
    cached = db.scalar(
        select(Food)
        .where(
            Food.family_id.is_(None),
            Food.source.in_((FoodSource.usda, FoodSource.off)),
            Food.source_id == code,
        )
        .options(selectinload(Food.servings))
        .order_by(Food.id.desc())
        .limit(1)
    )
    if cached is not None:
        refreshed = _cache_is_stale(cached) and _refresh_cached(db, cached)
        if not refreshed:
            # The heals patch two specific old mistakes in place. A row re-read
            # from its source this scan carries the source's current answer, so
            # there is nothing left for them to fix.
            _heal_serving_names(db, cached)
            _heal_liquid_unit(db, cached)
        return cached

    # USDA being down must not break scanning — treat its errors as a miss
    # and let Open Food Facts answer.
    try:
        result = foods_api.lookup_barcode_usda(code, settings.usda_api_key)
    except foods_api.FoodApiError:
        result = None
    if result is None:
        try:
            result = foods_api.lookup_barcode_off(code)
        except foods_api.FoodApiError as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product found for that barcode")

    # A scan is a deliberate, single product (unlike a search's 25 transient
    # hits), so cache it right away: the next scan of this code is answered at
    # home, and the label serving rides along for the ingredient default.
    food = Food(
        family_id=None,
        source=FoodSource(result.source),
        source_id=code,
        name=result.name,
        brand=result.brand,
        base_unit=result.base_unit,
        density_g_per_ml=result.density_g_per_ml,
        # Health-check fields ride along; a successful fetch stores "" for an
        # absent list rather than NULL, so a later health check reads the row as
        # already enriched instead of refetching it (see _heal_health_fields).
        ingredients_text=result.ingredients_text,
        added_sugar_g=result.added_sugar_g,
        additives=result.additives,
        nova_group=result.nova_group,
        fetched_at=_utcnow(),
        **{n: getattr(result, n) for n in FOOD_NUTRIENTS},
    )
    food.servings = [
        FoodServing(name=srv.name, grams=srv.grams, position=0)
        for srv in _result_servings(result, FoodServingOut)
    ]
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


@router.get("/barcode/{code}", response_model=FoodOut)
def lookup_barcode(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    """Resolve a scanned barcode to a food (the picker's scan path)."""
    return _resolve_barcode(db, user, code)


def _heal_health_fields(db: Session, food: Food) -> None:
    """Backfill the health-check fields on a shared-cache row that predates them
    (all three of ingredients_text/additives/nova_group NULL — a row cached
    before 0054, like the migration didn't touch existing data). One refetch
    (USDA then Open Food Facts); a successful fetch backfills in place and
    commits, writing "" for an absent list so it's never refetched again; a
    network failure or a code that no longer resolves leaves the row untouched,
    and the assessment simply falls back to the nutrition numbers. Custom foods
    and a family's own rows are never touched."""
    if food.family_id is not None or food.source == FoodSource.custom:
        return
    if not (
        food.ingredients_text is None
        and food.additives is None
        and food.nova_group is None
    ):
        return
    code = food.source_id or ""
    result = None
    try:
        result = foods_api.lookup_barcode_usda(code, settings.usda_api_key)
    except foods_api.FoodApiError:
        result = None
    if result is not None and not (
        result.ingredients_text or result.additives or result.nova_group
    ):
        # USDA answered but brought no label data; give Open Food Facts a shot
        # before marking the row enriched-but-empty.
        result = None
    if result is None:
        try:
            result = foods_api.lookup_barcode_off(code)
        except foods_api.FoodApiError:
            result = None
    if result is None:
        return
    food.ingredients_text = result.ingredients_text or ""
    food.added_sugar_g = result.added_sugar_g
    food.additives = result.additives or ""
    food.nova_group = result.nova_group
    db.commit()
    db.refresh(food)


@router.get("/health/{code}", response_model=FoodHealthOut)
def health_check(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    """The barcode health check: resolve the scanned code to a food, backfill its
    label data if this is an older cache row, and run the ingredient/nutrient
    rule engine. Adults only, like every other food lookup. Returns the resolved
    food (so the client can then log, save, or add it to a recipe) plus a verdict
    and the flags behind it."""
    food = _resolve_barcode(db, user, code)
    _heal_health_fields(db, food)
    result = food_health.assess(food, settings.health_added_sugar_g)
    return FoodHealthOut(
        food=FoodOut.model_validate(food),
        assessment=HealthAssessmentOut.model_validate(result),
    )


@router.get("", response_model=list[FoodOut])
def list_custom_foods(db: Session = Depends(get_db), user: User = Depends(require_family)):
    """The family's own custom foods, alphabetical."""
    foods = list(
        db.scalars(
            select(Food)
            .where(Food.family_id == user.family_id, Food.source == FoodSource.custom)
            .options(selectinload(Food.servings), selectinload(Food.village_shares))
            .order_by(func.lower(Food.name))
        )
    )
    return _with_shares(db, foods)


def _with_shares(db: Session, foods: list[Food]) -> list[FoodOut]:
    """Attach shared_to — the "Shared" indicator and the owner's unshare handle,
    RecipeOut's shape — to each food. Village names come from ONE batched query
    over the whole list: GET /foods is on the Kitchen hot path, no N+1."""
    village_ids = {sh.village_id for f in foods for sh in f.village_shares}
    names = (
        {
            v.id: v.name
            for v in db.scalars(select(Village).where(Village.id.in_(village_ids)))
        }
        if village_ids
        else {}
    )
    out: list[FoodOut] = []
    for f in foods:
        o = FoodOut.model_validate(f)
        o.shared_to = [
            RecipeShareOut(
                share_id=sh.id,
                village_id=sh.village_id,
                village_name=names.get(sh.village_id, ""),
            )
            for sh in f.village_shares
        ]
        out.append(o)
    return out


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
    # Edits keep their shares (live pointers); the response says so.
    return _with_shares(db, [food])[0]


@router.delete("/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_food(
    food_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Delete a custom food. Only the family's own custom entries."""
    db.delete(_own_custom_food(db, food_id, parent))
    db.commit()
