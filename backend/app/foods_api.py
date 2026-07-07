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

# USDA foodNutrients are keyed by nutrientNumber; these are the four we surface.
_N_ENERGY_KCAL = "208"
_N_PROTEIN = "203"
_N_FAT = "204"
_N_CARBS = "205"


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


def _num(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


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
            )
        )
    return results


def lookup_barcode(barcode: str) -> FoodResult | None:
    """Look a barcode up in Open Food Facts. Returns None if not found."""
    try:
        r = httpx.get(
            OFF_PRODUCT_URL.format(barcode=barcode),
            params={"fields": "product_name,brands,nutriments"},
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
    )
