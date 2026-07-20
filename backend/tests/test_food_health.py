"""The barcode health check: the pure rule engine (app.food_health) and the
GET /foods/health/{code} endpoint. External food-database calls are mocked, the
same way test_foods.py does it."""

import types

import pytest

from app import food_health, foods_api

THRESHOLD = 5.0


def _serv(grams):
    return types.SimpleNamespace(grams=grams)


def _food(serving_g=None, **fields):
    """A minimal food-like object for the engine: only the attributes assess()
    reads, all defaulting to absent."""
    ns = types.SimpleNamespace(
        ingredients_text=fields.get("ingredients_text"),
        additives=fields.get("additives"),
        nova_group=fields.get("nova_group"),
        added_sugar_g=fields.get("added_sugar_g"),
        trans_fat_g=fields.get("trans_fat_g"),
        saturated_fat_g=fields.get("saturated_fat_g"),
        sodium_mg=fields.get("sodium_mg"),
        sugar_g=fields.get("sugar_g"),
        servings=[_serv(serving_g)] if serving_g else [],
    )
    return ns


def _assess(**fields):
    return food_health.assess(_food(**fields), THRESHOLD)


def _cats(result):
    return {f.category for f in result.flags}


def _by_cat(result, category):
    return next(f for f in result.flags if f.category == category)


# ---- ingredient-term rules -----------------------------------------------------


def test_seed_oil_flags_as_bad():
    r = _assess(ingredients_text="Water, Soybean Oil, Salt")
    assert "seed_oil" in _cats(r)
    assert _by_cat(r, "seed_oil").severity == "bad"
    assert r.verdict == "mixed"


@pytest.mark.parametrize(
    "text", ["Rapeseed Oil", "Soya Oil", "Soy Oil", "Grape Seed Oil"]
)
def test_seed_oil_aliases_trip_the_rule(text):
    assert "seed_oil" in _cats(_assess(ingredients_text=text))


def test_non_hydrogenated_is_not_hydrogenated():
    # A label advertising the ABSENCE of hydrogenation must not earn "poor".
    r = _assess(ingredients_text="Non-Hydrogenated Palm Shortening")
    assert "hydrogenated" not in _cats(r)
    assert "hydrogenated" in _cats(
        _assess(ingredients_text="Partially Hydrogenated Soybean Oil")
    )


@pytest.mark.parametrize(
    "text",
    ["Olive Oil", "Extra Virgin Avocado Oil", "Coconut Oil", "Sunflower Lecithin"],
)
def test_good_oils_and_lecithin_never_trip_the_seed_oil_rule(text):
    r = _assess(ingredients_text=text)
    assert "seed_oil" not in _cats(r)
    # An ingredient list with no concerns reads as clean.
    assert r.verdict == "clean"


def test_hydrogenated_oil_forces_poor():
    r = _assess(ingredients_text="Hydrogenated Palm Oil")
    assert "hydrogenated" in _cats(r)
    assert _by_cat(r, "hydrogenated").severity == "bad"
    assert r.verdict == "poor"  # any hydrogenated oil is poor on its own


def test_partially_hydrogenated_seed_oil_is_poor():
    r = _assess(ingredients_text="Partially Hydrogenated Soybean Oil")
    assert {"hydrogenated", "seed_oil"} <= _cats(r)
    assert r.verdict == "poor"


def test_artificial_sweetener_is_a_bad_flag():
    r = _assess(ingredients_text="Water, Aspartame, Citric Acid")
    assert _by_cat(r, "sweetener").severity == "bad"
    assert r.verdict == "mixed"


def test_sugar_alcohol_is_a_warning():
    r = _assess(ingredients_text="Chocolate, Maltitol")
    assert _by_cat(r, "sugar_alcohol").severity == "warn"
    assert r.verdict == "mixed"


def test_artificial_dye_is_a_bad_flag():
    r = _assess(ingredients_text="Sugar, Red 40, Yellow 5")
    assert _by_cat(r, "dye").severity == "bad"


def test_dye_number_boundary_does_not_overmatch():
    # "Blue 12" must not fire the "Blue 1" dye rule.
    r = _assess(ingredients_text="Blue 12 Filler")
    assert "dye" not in _cats(r)


def test_caramel_color_is_a_warning_dye():
    r = _assess(ingredients_text="Cola, Caramel Color")
    assert _by_cat(r, "dye_warn").severity == "warn"


def test_bad_preservative_flags():
    r = _assess(ingredients_text="Cured Meat, Sodium Nitrite, BHT")
    assert _by_cat(r, "preservative").severity == "bad"


def test_warn_preservative_flags():
    r = _assess(ingredients_text="Juice, Sodium Benzoate")
    assert _by_cat(r, "preservative_warn").severity == "warn"


def test_additive_tags_flag_and_dedupe_with_text():
    # e102 tartrazine (dye), e211 sodium benzoate (warn preservative), coming
    # purely from the OFF tag list with no ingredient text.
    r = _assess(additives="en:e102,en:e211")
    assert _by_cat(r, "dye").severity == "bad"
    assert _by_cat(r, "preservative_warn").severity == "warn"
    assert r.verdict == "mixed"  # one bad flag


def test_text_and_tag_hit_for_one_concern_is_a_single_flag():
    r = _assess(ingredients_text="Red 40", additives="en:e129")  # both = allura red
    assert len([f for f in r.flags if f.category == "dye"]) == 1


# ---- nutrient rules ------------------------------------------------------------


def test_added_sugar_scales_over_the_threshold_on_a_30g_serving():
    # 20 g per 100 * 0.3 = 6 g per serving, over the 5 g bar.
    r = food_health.assess(
        _food(serving_g=30, added_sugar_g=20, ingredients_text="Sugar, Water"),
        THRESHOLD,
    )
    flag = _by_cat(r, "added_sugar")
    assert flag.severity == "bad" and "6" in flag.detail
    assert r.verdict == "mixed"


def test_added_sugar_under_the_threshold_on_a_30g_serving_is_clean():
    # 10 g per 100 * 0.3 = 3 g per serving, under 5 g.
    r = food_health.assess(
        _food(serving_g=30, added_sugar_g=10, ingredients_text="Water, Milk"),
        THRESHOLD,
    )
    assert "added_sugar" not in _cats(r)
    assert r.verdict == "clean"


def test_added_sugar_alias_fallback_without_a_quantity():
    # No added-sugar nutrient, but the ingredients name it: a bad flag, no grams.
    r = _assess(ingredients_text="Water, High Fructose Corn Syrup")
    flag = _by_cat(r, "added_sugar")
    assert flag.severity == "bad"
    assert not any(ch.isdigit() for ch in flag.detail)


def test_total_sugar_is_a_weak_warning_when_added_is_unknown():
    # No added-sugar nutrient and no sugar aliases, but 20 g total sugar/serving.
    r = _assess(ingredients_text="Cream", sugar_g=20)
    flag = _by_cat(r, "sugar")
    assert flag.severity == "warn"
    assert r.verdict == "mixed"


def test_trans_fat_over_zero_is_bad():
    r = _assess(ingredients_text="Cream", trans_fat_g=0.5)
    assert _by_cat(r, "trans_fat").severity == "bad"


def test_no_trans_fat_no_flag():
    r = _assess(ingredients_text="Cream", trans_fat_g=0)
    assert "trans_fat" not in _cats(r)


def test_saturated_fat_at_and_below_threshold():
    assert "sat_fat" in _cats(_assess(ingredients_text="Cream", saturated_fat_g=4))
    assert "sat_fat" not in _cats(_assess(ingredients_text="Cream", saturated_fat_g=3.9))


def test_sodium_at_and_below_threshold():
    assert "sodium" in _cats(_assess(ingredients_text="Broth", sodium_mg=460))
    assert "sodium" not in _cats(_assess(ingredients_text="Broth", sodium_mg=459))


def test_nova_four_is_an_ultra_processed_warning():
    r = _assess(nova_group=4)
    assert _by_cat(r, "nova").severity == "warn"
    assert r.verdict == "mixed"


def test_nova_one_is_a_positive_and_reads_as_whole():
    r = _assess(nova_group=1)
    assert _by_cat(r, "nova").severity == "info"
    assert r.verdict == "whole"


# ---- verdict mapping -----------------------------------------------------------


def test_two_bad_flags_are_poor():
    r = _assess(ingredients_text="Aspartame, Red 40")
    bad = [f for f in r.flags if f.severity == "bad"]
    assert len(bad) >= 2 and r.verdict == "poor"


def test_no_data_at_all_is_unknown_with_a_limited_data_note():
    r = _assess()
    assert r.verdict == "unknown"
    note = _by_cat(r, "data")
    assert note.severity == "info" and note.label == "Limited data"


def test_clean_when_an_ingredient_list_has_no_concerns():
    r = _assess(ingredients_text="Almonds, Sea Salt")
    assert r.flags == []
    assert r.verdict == "clean"


def test_limited_data_note_absent_when_there_is_ingredient_data():
    r = _assess(ingredients_text="Almonds")
    assert "data" not in _cats(r)


# ---- the endpoint --------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_usda_key(monkeypatch):
    """Keep the USDA barcode path a no-op so the OFF mocks are authoritative."""
    from app.config import settings

    monkeypatch.setattr(settings, "usda_api_key", "")


def _off_result(code, **over):
    fields = dict(
        ingredients_text="Potatoes, Soybean Oil, Salt",
        additives="en:e621",
        nova_group=4,
        sodium_mg=200.0,
        sugar_g=2.0,
    )
    fields.update(over)
    return foods_api.FoodResult(
        "off", code, "Test Chips", "BrandX", 500.0, 5.0, 50.0, 30.0, **fields
    )


def test_health_check_is_closed_to_minors(child):
    assert child.get("/foods/health/0051500255162").status_code == 403


def test_health_check_rejects_a_bad_code(owner):
    assert owner.get("/foods/health/12ab34").status_code == 400


def test_health_check_404_when_the_product_is_unknown(owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", lambda code: None)
    assert owner.get("/foods/health/0000000000000").status_code == 404


def test_custom_food_health_makes_no_network_call_and_is_unknown(owner, monkeypatch):
    def must_not_be_called(code):
        raise AssertionError("barcode lookup left the server")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    made = owner.post(
        "/foods",
        json={
            "name": "Homemade Rub", "barcode": "4099999999991",
            "servings": [{"name": "100 g", "grams": 100}], "basis_index": 0,
            "calories": 10,
        },
    ).json()

    res = owner.get("/foods/health/4099999999991")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["food"]["id"] == made["id"] and body["food"]["source"] == "custom"
    assert body["assessment"]["verdict"] == "unknown"
    labels = [f["label"] for f in body["assessment"]["flags"]]
    assert "Limited data" in labels


def test_health_check_caches_the_new_fields_and_second_call_is_offline(owner, monkeypatch):
    calls: list[str] = []

    def fake_off(code):
        calls.append(code)
        return _off_result(code)

    monkeypatch.setattr(foods_api, "lookup_barcode_off", fake_off)
    res = owner.get("/foods/health/3017620422003")
    assert res.status_code == 200, res.text
    body = res.json()
    # The health fields round-trip onto the cached FoodOut.
    food = body["food"]
    assert food["ingredients_text"] == "Potatoes, Soybean Oil, Salt"
    assert food["additives"] == "en:e621" and food["nova_group"] == 4
    # Soybean oil (bad) + NOVA 4 (warn) -> some concerns.
    cats = {f["category"] for f in body["assessment"]["flags"]}
    assert "seed_oil" in cats and body["assessment"]["verdict"] == "mixed"
    assert calls == ["3017620422003"]

    # The row is now enriched, so a second check never leaves the server.
    def must_not_be_called(code):
        raise AssertionError("barcode lookup left the server")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/health/3017620422003")
    assert again.status_code == 200
    assert again.json()["food"]["ingredients_text"] == "Potatoes, Soybean Oil, Salt"


def test_health_check_heals_a_pre_0054_cache_row(owner, monkeypatch):
    # A row cached before the health fields existed has them all NULL. Reuse the
    # recipe path to create exactly such a shared-cache row (no health data).
    from tests.test_recipes import make_recipe, usda_line

    line = usda_line(source_id="3017620422003", name="Nutella")
    line["source"] = "off"
    make_recipe(owner, ingredients=[line])

    healed = _off_result("3017620422003", ingredients_text="Sugar, Palm Oil, Hazelnuts")

    def fake_off(code):
        return healed

    monkeypatch.setattr(foods_api, "lookup_barcode_off", fake_off)
    res = owner.get("/foods/health/3017620422003")
    assert res.status_code == 200, res.text
    body = res.json()
    # The heal backfilled the label onto the existing cache row.
    assert body["food"]["ingredients_text"] == "Sugar, Palm Oil, Hazelnuts"
    assert body["food"]["nova_group"] == 4


def test_health_check_tolerates_a_heal_failure(owner, monkeypatch):
    # A pre-0054 cache row whose refetch fails: the row is left untouched and the
    # assessment falls back to the nutrition numbers, still a 200.
    from tests.test_recipes import make_recipe, usda_line

    line = usda_line(source_id="3017620422003", name="Salty Snack", sodium_mg=900.0)
    line["source"] = "off"
    make_recipe(owner, ingredients=[line])

    def boom(code):
        raise foods_api.FoodApiError("Open Food Facts is down.")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", boom)
    res = owner.get("/foods/health/3017620422003")
    assert res.status_code == 200, res.text
    body = res.json()
    # No ingredient list survived, so only the numbers were judged.
    assert body["food"]["ingredients_text"] is None
    labels = [f["label"] for f in body["assessment"]["flags"]]
    assert "Limited data" in labels
