"""Outbound food-database lookups, kept in one module so the routes stay thin
and tests can mock the network. The server makes these calls, never the phones.

USDA FoodData Central provides food search (needs a free api.data.gov key);
Open Food Facts provides barcode lookups (no key). Both are normalised to a
FoodResult with nutrition per 100 g.
"""

import dataclasses

import httpx

USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
_UA = "dailybread/0.1 (self-hosted family app)"
_TIMEOUT = 10.0

# USDA foodNutrients are keyed by nutrientNumber. USDA reports sodium and
# cholesterol in mg and the rest in g — the same units our columns use.
_N_ENERGY_KCAL = "208"
_N_PROTEIN = "203"
_N_FAT = "204"
_N_CARBS = "205"
_N_SATURATED = "606"
_N_TRANS = "605"
_N_CHOLESTEROL = "601"  # mg
_N_SODIUM = "307"  # mg
_N_FIBER = "291"
_N_SUGAR = "269"


class FoodApiError(Exception):
    """A food-database call couldn't be completed; the route turns it into a 502."""


@dataclasses.dataclass
class FoodResult:
    source: str  # "usda" | "off"
    source_id: str
    name: str
    brand: str
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    cholesterol_mg: float | None = None  # mg
    sodium_mg: float | None = None  # mg
    fiber_g: float | None = None
    sugar_g: float | None = None
    serving: str = ""  # human label for the label serving, e.g. "1 slice (21 g)"
    # The label serving as a measurable size: how many of the food's base unit
    # (g for solids, mL for liquids) one serving is. None when the source only
    # gives a household phrase ("1 cup") with no fixed size to trust.
    serving_amount: float | None = None
    base_unit: str = "g"  # "g" | "ml"


def _num(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _scale(v, mult: float) -> float | None:
    """Like _num but scaled — Open Food Facts reports sodium/cholesterol in grams
    per 100 g, so we multiply by 1000 to store milligrams like the labels do."""
    n = _num(v)
    return round(n * mult, 2) if n is not None else None


# Label units we can turn into a measurable serving. Mass lands in grams,
# volume in millilitres — covering the g / kg / oz and mL / cL / L / fl oz
# markings food labels actually carry. Anything else (a bare "1 cup", "2
# cookies") has no fixed size we can trust, so it stays display-only.
_MASS_TO_G = {"g": 1.0, "gram": 1.0, "grams": 1.0, "grm": 1.0, "kg": 1000.0, "oz": 28.3495}
_VOLUME_TO_ML = {"ml": 1.0, "mlt": 1.0, "cl": 10.0, "l": 1000.0, "fl oz": 29.5735, "floz": 29.5735}


def _serving_in_base(size, unit) -> tuple[float, str] | None:
    """(amount in base units, base unit) for a label serving, or None."""
    n = _num(size)
    if n is None or n <= 0:
        return None
    u = (unit or "").strip().lower()
    if u in _MASS_TO_G:
        return round(n * _MASS_TO_G[u], 2), "g"
    if u in _VOLUME_TO_ML:
        return round(n * _VOLUME_TO_ML[u], 2), "ml"
    return None


def _usda_serving(f: dict) -> str:
    """A display serving from a USDA search hit. Branded foods carry a household
    text ("1 slice") and/or a gram size; we show whichever we have, both when we
    can. Foundation/SR Legacy items usually have neither, so this returns ""."""
    household = (f.get("householdServingFullText") or "").strip()
    grams = ""
    size = _num(f.get("servingSize"))
    if size is not None:
        unit = (f.get("servingSizeUnit") or "").strip()
        grams = f"{size:g} {unit}".strip()
    if household and grams:
        return f"{household} ({grams})"
    return household or grams


def search_usda(query: str, api_key: str, limit: int = 25) -> list[FoodResult]:
    """Search USDA FoodData Central. Raises FoodApiError if not configured or
    the call fails."""
    if not api_key:
        raise FoodApiError("Food search isn't set up yet (no USDA API key).")
    try:
        r = httpx.get(
            USDA_SEARCH_URL,
            params={
                "api_key": api_key,
                "query": query,
                "pageSize": limit,
                "dataType": "Foundation,SR Legacy,Branded",
            },
            headers={"User-Agent": _UA},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise FoodApiError("Couldn't reach the food database.") from e
    if r.status_code == 400:
        # A malformed/unsearchable query (e.g. odd punctuation) — not an outage.
        # Treat it as simply no matches rather than an error.
        return []
    if r.status_code in (401, 403):
        raise FoodApiError("The food database rejected the API key.")
    if r.status_code == 429:
        raise FoodApiError("Food search is busy right now; try again in a moment.")
    if r.status_code >= 400:
        raise FoodApiError("Food search failed.")

    results: list[FoodResult] = []
    for f in r.json().get("foods", []):
        by_number = {str(n.get("nutrientNumber")): n.get("value") for n in f.get("foodNutrients", [])}
        results.append(
            FoodResult(
                source="usda",
                source_id=str(f.get("fdcId")),
                name=(f.get("description") or "").strip(),
                brand=(f.get("brandName") or f.get("brandOwner") or "").strip(),
                calories=_num(by_number.get(_N_ENERGY_KCAL)),
                protein_g=_num(by_number.get(_N_PROTEIN)),
                carbs_g=_num(by_number.get(_N_CARBS)),
                fat_g=_num(by_number.get(_N_FAT)),
                saturated_fat_g=_num(by_number.get(_N_SATURATED)),
                trans_fat_g=_num(by_number.get(_N_TRANS)),
                cholesterol_mg=_num(by_number.get(_N_CHOLESTEROL)),
                sodium_mg=_num(by_number.get(_N_SODIUM)),
                fiber_g=_num(by_number.get(_N_FIBER)),
                sugar_g=_num(by_number.get(_N_SUGAR)),
                serving=_usda_serving(f),
                **_serving_fields(f.get("servingSize"), f.get("servingSizeUnit")),
            )
        )
    return results


def _serving_fields(size, unit) -> dict:
    """FoodResult kwargs for a label serving, when it's measurable."""
    parsed = _serving_in_base(size, unit)
    if parsed is None:
        return {}
    amount, base = parsed
    return {"serving_amount": amount, "base_unit": base}


def lookup_barcode(barcode: str) -> FoodResult | None:
    """Look a barcode up in Open Food Facts. Returns None if not found."""
    try:
        r = httpx.get(
            OFF_PRODUCT_URL.format(barcode=barcode),
            params={
                "fields": "product_name,brands,nutriments,serving_size,"
                "serving_quantity,serving_quantity_unit"
            },
            headers={"User-Agent": _UA},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise FoodApiError("Couldn't reach the barcode database.") from e
    if r.status_code >= 500:
        raise FoodApiError("The barcode database is unavailable.")

    data = r.json()
    if data.get("status") != 1:
        return None
    p = data.get("product", {})
    nut = p.get("nutriments", {})
    return FoodResult(
        source="off",
        source_id=str(barcode),
        name=(p.get("product_name") or "Unknown product").strip(),
        brand=(p.get("brands") or "").split(",")[0].strip(),
        calories=_num(nut.get("energy-kcal_100g")),
        protein_g=_num(nut.get("proteins_100g")),
        carbs_g=_num(nut.get("carbohydrates_100g")),
        fat_g=_num(nut.get("fat_100g")),
        saturated_fat_g=_num(nut.get("saturated-fat_100g")),
        trans_fat_g=_num(nut.get("trans-fat_100g")),
        # OFF stores these in grams per 100 g; labels (and our columns) use mg.
        cholesterol_mg=_scale(nut.get("cholesterol_100g"), 1000),
        sodium_mg=_scale(nut.get("sodium_100g"), 1000),
        fiber_g=_num(nut.get("fiber_100g")),
        sugar_g=_num(nut.get("sugars_100g")),
        serving=(p.get("serving_size") or "").strip(),
        # serving_quantity is normalized (grams, or millilitres for drinks);
        # older records omit the unit, which then means grams.
        **_serving_fields(p.get("serving_quantity"), p.get("serving_quantity_unit") or "g"),
    )
