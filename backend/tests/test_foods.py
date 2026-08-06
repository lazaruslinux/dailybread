"""Food layer: server-proxied USDA search + USDA/Open Food Facts barcode,
custom foods, and cross-family isolation. External calls are mocked."""

import datetime as dt

import pytest

from app import foods_api
from app.config import settings


@pytest.fixture(autouse=True)
def _no_usda_key(monkeypatch):
    """Barcode tests must not depend on whether the developer's .env carries a
    USDA key: without one the USDA barcode path is a guaranteed no-op, so the
    OFF mocks below stay authoritative. USDA-path tests mock the function."""
    monkeypatch.setattr(settings, "usda_api_key", "")


def test_search_is_proxied(owner, monkeypatch):
    # The route calls foods_api.search_usda; mock it so no network is touched.
    def fake_search(query, api_key, limit=25):
        assert query == "ground beef"
        return [
            foods_api.FoodResult(
                "usda", "12345", "Ground beef, 85/15", "Great Value",
                250.0, 26.0, 0.0, 17.0,
                sodium_mg=75.0, sugar_g=0.0, serving="4 oz (113 g)",
            )
        ]

    monkeypatch.setattr(foods_api, "search_usda", fake_search)
    res = owner.get("/foods/search?q=ground beef")
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body) == 1
    f = body[0]
    assert f["id"] is None  # a search result isn't saved until used in a recipe
    assert f["source"] == "usda" and f["source_id"] == "12345"
    assert f["name"] == "Ground beef, 85/15" and f["calories"] == 250.0
    # the extended label + serving pass through to the client
    assert f["serving"] == "4 oz (113 g)"
    assert f["sodium_mg"] == 75.0 and f["sugar_g"] == 0.0


def test_search_surfaces_api_errors_as_502(owner, monkeypatch):
    def boom(query, api_key, limit=25):
        raise foods_api.FoodApiError("Food search isn't set up yet (no USDA API key).")

    monkeypatch.setattr(foods_api, "search_usda", boom)
    res = owner.get("/foods/search?q=milk")
    assert res.status_code == 502
    assert "USDA" in res.json()["detail"]


def test_barcode_lookup_is_proxied(owner, monkeypatch):
    def fake_barcode(code):
        assert code == "3017620422003"
        return foods_api.FoodResult("off", code, "Nutella", "Ferrero", 539.0, 6.3, 57.5, 30.9)

    monkeypatch.setattr(foods_api, "lookup_barcode_off", fake_barcode)
    res = owner.get("/foods/barcode/3017620422003")
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Nutella" and res.json()["source"] == "off"


def test_barcode_not_found_is_404(owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", lambda code: None)
    assert owner.get("/foods/barcode/0000000000000").status_code == 404


def test_barcode_rejects_non_numeric(owner):
    assert owner.get("/foods/barcode/not-a-code").status_code == 400


def test_minors_get_no_food_lookups(child):
    """Kids have no nutrition area, so the picker's third-party lookups are
    closed to them too - search, the recent shelf, and barcode scans."""
    assert child.get("/foods/search?q=apple").status_code == 403
    assert child.get("/foods/recent").status_code == 403
    assert child.get("/foods/barcode/0051500255162").status_code == 403


# A minimal valid custom-food body: one serving, nutrition entered per it.
def _food(name, **over):
    body = {"name": name, "servings": [{"name": "1 serving", "grams": 100}], "basis_index": 0}
    body.update(over)
    return body


def test_custom_food_crud_and_permissions(owner, child):
    made = owner.post("/foods", json=_food("Grandma's sauce", calories=90, carbs_g=12))
    assert made.status_code == 201, made.text
    fid = made.json()["id"]
    assert made.json()["source"] == "custom" and made.json()["id"] is not None

    # Everyone sees the family's custom foods; only parents add/remove.
    assert any(f["id"] == fid for f in child.get("/foods").json())
    assert child.post("/foods", json=_food("Nope")).status_code == 403
    assert child.delete(f"/foods/{fid}").status_code == 403

    assert owner.delete(f"/foods/{fid}").status_code == 204
    assert all(f["id"] != fid for f in owner.get("/foods").json())


def test_custom_food_converts_to_per_100g_and_keeps_servings(owner):
    # Nutrition entered per the 50 g serving is stored per-100g (doubled here).
    made = owner.post(
        "/foods",
        json={
            "name": "Protein bar",
            "brand": "HomeCo",
            "servings": [{"name": "1 bar", "grams": 50}, {"name": "100 g", "grams": 100}],
            "basis_index": 0,
            "calories": 100, "protein_g": 10, "sugar_g": 5, "sodium_mg": 60,
        },
    )
    assert made.status_code == 201, made.text
    f = made.json()
    assert f["calories"] == 200.0 and f["protein_g"] == 20.0  # per-100g
    assert f["sugar_g"] == 10.0 and f["sodium_mg"] == 120.0
    assert f["fat_g"] is None  # unspecified stays unknown, not zero
    assert [s["name"] for s in f["servings"]] == ["1 bar", "100 g"]
    assert f["servings"][0]["grams"] == 50.0


def test_update_custom_food(owner):
    fid = owner.post("/foods", json=_food("Draft", calories=100)).json()["id"]
    edited = owner.put(
        f"/foods/{fid}",
        json={"name": "Final", "servings": [{"name": "1 cup", "grams": 200}],
              "basis_index": 0, "calories": 100},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Final"
    assert edited.json()["calories"] == 50.0  # 100 per 200 g -> 50 per 100 g
    assert edited.json()["servings"][0]["name"] == "1 cup"


def test_custom_food_rejects_bad_basis_index(owner):
    bad = owner.post(
        "/foods",
        json={"name": "Oops", "servings": [{"name": "1", "grams": 10}], "basis_index": 3},
    )
    assert bad.status_code == 422


def test_volume_custom_food_stores_per_100ml(owner):
    # A liquid entered by volume: a 240 mL serving with 60 cal is stored per-100mL
    # (60 * 100 / 240 = 25), and base_unit round-trips as "ml".
    made = owner.post(
        "/foods",
        json={
            "name": "Almond milk", "base_unit": "ml",
            "servings": [{"name": "1 cup", "grams": 240}], "basis_index": 0,
            "calories": 60, "protein_g": 2.4,
        },
    )
    assert made.status_code == 201, made.text
    f = made.json()
    assert f["base_unit"] == "ml"
    assert f["calories"] == 25.0 and f["protein_g"] == 1.0  # per-100mL
    assert f["servings"][0]["grams"] == 240.0  # the serving size, in mL


def test_custom_food_persists_health_fields(owner):
    # The label data a scan carries into "save as custom food" round-trips on the
    # food. The 21 g basis serving proves added_sugar_g is stored as given (it is
    # already per-100) while the printed macros DO go through the basis
    # conversion: sugar 17 per 21 g serving becomes ~80.95 per-100.
    owner.post(
        "/foods",
        json=_food(
            "Labelled snack",
            servings=[{"name": "1 bar", "grams": 21}],
            sugar_g=17,
            ingredients_text="Oats, Honey, Salt",
            added_sugar_g=8, additives="en:e322", nova_group=3,
        ),
    )
    f = next(f for f in owner.get("/foods").json() if f["name"] == "Labelled snack")
    assert f["ingredients_text"] == "Oats, Honey, Salt"
    assert f["added_sugar_g"] == 8.0 and f["additives"] == "en:e322"
    assert f["nova_group"] == 3
    assert f["sugar_g"] is not None and abs(f["sugar_g"] - 80.95) < 0.1


def test_update_custom_food_preserves_health_fields(owner):
    fid = owner.post("/foods", json=_food("Draft", calories=100)).json()["id"]
    edited = owner.put(
        f"/foods/{fid}",
        json=_food(
            "Final", calories=100,
            ingredients_text="Honey.", nova_group=2, added_sugar_g=0,
        ),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["ingredients_text"] == "Honey."
    assert edited.json()["nova_group"] == 2 and edited.json()["added_sugar_g"] == 0.0


def test_custom_food_without_health_fields_stores_null(owner):
    f = owner.post("/foods", json=_food("Plain", calories=50)).json()
    assert f["ingredients_text"] is None and f["added_sugar_g"] is None
    assert f["additives"] is None and f["nova_group"] is None


def test_saved_honey_custom_food_still_reads_clean(owner):
    # The regression this fixes: honey saved from a scan keeps its label, so a
    # later scan of the same barcode resolves to the custom food and still reads
    # "clean" (the single-ingredient sweetener exemption fires) instead of
    # warning "High in sugar" off the total-sugar fallback.
    made = owner.post(
        "/foods",
        json=_food(
            "Raw Honey", barcode="0096619222841",
            servings=[{"name": "1 tbsp", "grams": 21}],
            sugar_g=80.95, ingredients_text="Honey.", nova_group=2,
        ),
    )
    assert made.status_code == 201, made.text
    body = owner.get("/foods/health/0096619222841").json()
    assert body["food"]["ingredients_text"] == "Honey."
    assert body["assessment"]["verdict"] == "clean"
    cats = {f["category"] for f in body["assessment"]["flags"]}
    assert "added_sugar" not in cats and "sugar" not in cats


def test_folder_round_trips_and_normalizes(owner):
    # Set on create, comes back verbatim.
    made = owner.post("/foods", json=_food("Filed", calories=100, folder="Panda Express"))
    assert made.status_code == 201, made.text
    fid = made.json()["id"]
    assert made.json()["folder"] == "Panda Express"

    # Cleared to null when omitted on edit.
    edited = owner.put(f"/foods/{fid}", json=_food("Filed", calories=100))
    assert edited.status_code == 200, edited.text
    assert edited.json()["folder"] is None

    # Whitespace-only stores NULL, not a blank string.
    blank = owner.put(f"/foods/{fid}", json=_food("Filed", calories=100, folder="   "))
    assert blank.json()["folder"] is None

    # 61 characters is over the cap.
    long = owner.post("/foods", json=_food("TooLong", calories=100, folder="x" * 61))
    assert long.status_code == 422


def test_cache_and_barcode_foods_have_null_folder(owner, monkeypatch):
    def fake_search(query, api_key, limit=25):
        return [foods_api.FoodResult("usda", "12345", "Ground beef", "GV", 250.0, 26.0, 0.0, 17.0)]

    monkeypatch.setattr(foods_api, "search_usda", fake_search)
    assert owner.get("/foods/search?q=beef").json()[0]["folder"] is None

    def fake_barcode(code):
        return foods_api.FoodResult("off", code, "Nutella", "Ferrero", 539.0, 6.3, 57.5, 30.9)

    monkeypatch.setattr(foods_api, "lookup_barcode_off", fake_barcode)
    assert owner.get("/foods/barcode/3017620422003").json()["folder"] is None


def test_custom_food_defaults_to_mass(owner):
    f = owner.post("/foods", json=_food("Solid", calories=100)).json()
    assert f["base_unit"] == "g"


def test_custom_foods_are_isolated_across_families(owner, other):
    made = owner.post("/foods", json=_food("Secret Rub", calories=10))
    fid = made.json()["id"]
    assert all(f["name"] != "Secret Rub" for f in other.get("/foods").json())
    # B can't see, edit, or delete A's custom food (looks like it doesn't exist).
    assert other.put(f"/foods/{fid}", json=_food("Hijack")).status_code == 404
    assert other.delete(f"/foods/{fid}").status_code == 404


def test_search_results_are_cached_briefly(owner, monkeypatch):
    calls: list[str] = []

    def fake_search(query, api_key, limit=25):
        calls.append(query)
        return [foods_api.FoodResult("usda", "1", "Milk", "", 60.0, 3.3, 4.8, 3.2)]

    monkeypatch.setattr(foods_api, "search_usda", fake_search)
    owner.get("/foods/search?q=milk")
    owner.get("/foods/search?q=milk")
    owner.get("/foods/search?q=MILK")  # case-insensitive: same cached answer
    assert calls == ["milk"]
    owner.get("/foods/search?q=eggs")  # a different query is a real fetch
    assert calls == ["milk", "eggs"]


def test_search_errors_are_not_cached(owner, monkeypatch):
    # A hiccup (USDA down, no key) must not poison 15 minutes of searches.
    def boom(query, api_key, limit=25):
        raise foods_api.FoodApiError("USDA is unavailable right now.")

    monkeypatch.setattr(foods_api, "search_usda", boom)
    assert owner.get("/foods/search?q=milk").status_code == 502

    def ok(query, api_key, limit=25):
        return [foods_api.FoodResult("usda", "1", "Milk", "", 60.0, 3.3, 4.8, 3.2)]

    monkeypatch.setattr(foods_api, "search_usda", ok)
    assert owner.get("/foods/search?q=milk").status_code == 200


def _custom_food(client, name="Trail mix", barcode=None, **overrides):
    payload = {
        "name": name, "brand": "", "servings": [{"name": "100 g", "grams": 100}],
        "basis_index": 0, "calories": 480.0, **overrides,
    }
    if barcode is not None:
        payload["barcode"] = barcode
    res = client.post("/foods", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_scanned_barcode_resolves_a_custom_food_locally(owner, monkeypatch):
    # A product entered by hand after an unknown scan is found by its barcode
    # forever after, without asking Open Food Facts at all.
    def must_not_be_called(code):
        raise AssertionError("barcode lookup left the server")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    made = _custom_food(owner, barcode="4099999999991")

    res = owner.get("/foods/barcode/4099999999991")
    assert res.status_code == 200, res.text
    found = res.json()
    assert found["id"] == made["id"] and found["source"] == "custom"
    assert found["name"] == "Trail mix"


def test_custom_food_barcode_is_family_private(owner, other, monkeypatch):
    # Another household scanning the same code gets nothing from family A's
    # entry — it falls through to Open Food Facts like any unknown code.
    _custom_food(owner, barcode="4099999999991")
    monkeypatch.setattr(foods_api, "lookup_barcode_off", lambda code: None)
    assert other.get("/foods/barcode/4099999999991").status_code == 404


def test_barcode_resolves_from_the_shared_cache_before_off(owner, monkeypatch):
    # A product used in a recipe once is cached. Nothing ever fetched it by
    # barcode, so its age is unknown and the first scan re-reads it from the
    # source; every scan after that is served from the cache, no outbound call.
    from tests.test_recipes import make_recipe, usda_line

    line = usda_line(source_id="3017620422003", name="Nutella")
    line["source"] = "off"
    make_recipe(owner, ingredients=[line])

    monkeypatch.setattr(
        foods_api,
        "lookup_barcode_off",
        lambda code: foods_api.FoodResult(
            "off", code, "Nutella", "Ferrero", 539.0, 6.3, 57.5, 30.9
        ),
    )
    res = owner.get("/foods/barcode/3017620422003")
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "off" and res.json()["name"] == "Nutella"

    def must_not_be_called(code):
        raise AssertionError("barcode lookup left the server")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/barcode/3017620422003").json()
    assert again["id"] == res.json()["id"] and again["name"] == "Nutella"


# ---- the recently-used shelf ------------------------------------------------------


def _log_diary(client, name: str, source_id: str, **overrides):
    body = {
        "date_for": dt.date.today().isoformat(),
        "slot": "lunch",
        "amount": 100,
        "unit": "g",
        "source": "usda",
        "source_id": source_id,
        "name": name,
        "brand": "",
        "calories": 100.0,
        "protein_g": 5.0,
        "carbs_g": 10.0,
        "fat_g": 1.0,
    }
    body.update(overrides)
    res = client.post("/diary", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_recent_foods_start_empty(owner):
    assert owner.get("/foods/recent").json() == []


def test_recent_foods_are_my_diary_picks_newest_first(owner):
    _log_diary(owner, "Rolled Oats", "900001")
    _log_diary(owner, "Greek Yogurt", "900002")
    names = [f["name"] for f in owner.get("/foods/recent").json()]
    assert names[:2] == ["Greek Yogurt", "Rolled Oats"]


def test_recent_foods_dedupe_repeat_logs(owner):
    _log_diary(owner, "Rolled Oats", "900001")
    _log_diary(owner, "Rolled Oats", "900001")
    names = [f["name"] for f in owner.get("/foods/recent").json()]
    assert names.count("Rolled Oats") == 1


def test_anothers_diary_stays_out_but_family_recipes_count(owner, parent):
    # The other parent's diary pick is theirs alone...
    _log_diary(parent, "Secret Snack", "900009")
    assert owner.get("/foods/recent").json() == []
    # ...but a food used in a family recipe shows for everyone in the family.
    res = owner.post(
        "/recipes",
        json={
            "name": "Oat bowl",
            "servings": 2,
            "ingredients": [
                {
                    "source": "usda",
                    "source_id": "900010",
                    "name": "Steel Cut Oats",
                    "brand": "",
                    "calories": 100.0,
                    "protein_g": 5.0,
                    "carbs_g": 10.0,
                    "fat_g": 1.0,
                    "amount": 80,
                    "unit": "g",
                }
            ],
        },
    )
    assert res.status_code == 201, res.text
    mine = [f["name"] for f in owner.get("/foods/recent").json()]
    theirs = [f["name"] for f in parent.get("/foods/recent").json()]
    assert mine == ["Steel Cut Oats"]
    assert theirs[0] == "Secret Snack"  # their own pick outranks the family's
    assert "Steel Cut Oats" in theirs


def test_bad_barcodes_are_rejected(owner):
    assert owner.get("/foods/barcode/12ab34").status_code == 400
    assert owner.get("/foods/barcode/1234567").status_code == 400  # shorter than EAN-8
    assert owner.get("/foods/barcode/123456789012345").status_code == 400  # longer than GTIN-14
    res = owner.post("/foods", json={
        "name": "X", "servings": [{"name": "100 g", "grams": 100}],
        "basis_index": 0, "barcode": "not-digits",
    })
    assert res.status_code == 422


def test_editing_a_custom_food_keeps_or_updates_its_barcode(owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", lambda code: None)
    made = _custom_food(owner, barcode="4099999999991")
    # An edit that sends the barcode back keeps it; sending null clears it.
    payload = {"name": "Trail mix deluxe", "brand": "", "barcode": "4099999999991",
               "servings": [{"name": "100 g", "grams": 100}], "basis_index": 0}
    res = owner.put(f"/foods/{made['id']}", json=payload)
    assert res.status_code == 200
    assert owner.get("/foods/barcode/4099999999991").json()["name"] == "Trail mix deluxe"

    payload["barcode"] = None
    owner.put(f"/foods/{made['id']}", json=payload)
    assert owner.get("/foods/barcode/4099999999991").status_code == 404


def test_scanned_product_defaults_to_its_label_serving_and_is_cached(owner, monkeypatch):
    # An OFF hit carries its label serving as a structured portion (so the
    # recipe line defaults to "1 serving", not 100 g) and is cached at scan
    # time — the second scan is answered locally, serving included.
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, "Greek Style Pita", "Athens",
            275.0, 8.0, 53.0, 5.0, sugar_g=5.0,
            serving="1 pita (60 g)", serving_amount=60.0, base_unit="g",
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", off_hit)
    res = owner.get("/foods/barcode/4012345678901")
    assert res.status_code == 200, res.text
    first = res.json()
    assert first["id"] is not None  # cached immediately
    assert first["base_unit"] == "g"
    assert first["servings"] == [{"name": "1 pita (60 g)", "grams": 60.0}]

    def must_not_be_called(code):
        raise AssertionError("second scan left the server")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/barcode/4012345678901").json()
    assert again["id"] == first["id"]
    assert again["servings"] == first["servings"]


def test_liquid_scan_keeps_volume_units(owner, monkeypatch):
    # A drink's serving is millilitres; the food lands as a volume food so
    # recipe lines measure it in mL / fl oz, per-100mL nutrition intact.
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, "Orange Juice", "Simply",
            45.0, 0.7, 10.4, 0.1,
            serving="8 fl oz (240 mL)", serving_amount=240.0, base_unit="ml",
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", off_hit)
    body = owner.get("/foods/barcode/4023456789012").json()
    assert body["base_unit"] == "ml"
    assert body["servings"][0]["grams"] == 240.0


def test_search_results_carry_a_structured_serving(owner, monkeypatch):
    def fake_search(query, api_key, limit=25):
        return [
            foods_api.FoodResult(
                "usda", "999", "Bread, pita, white", "",
                275.0, 9.1, 55.7, 1.2,
                serving="1 large (60 g)", serving_amount=60.0, base_unit="g",
            ),
            foods_api.FoodResult(  # no measurable serving -> none offered
                "usda", "998", "Flour, wheat", "", 364.0, 10.3, 76.3, 1.0,
            ),
        ]

    monkeypatch.setattr(foods_api, "search_usda", fake_search)
    body = owner.get("/foods/search?q=pita").json()
    assert body[0]["servings"] == [{"name": "1 large (60 g)", "grams": 60.0}]
    assert body[1]["servings"] == []


def test_label_units_convert_to_base_measures():
    # The g/kg/oz and mL/cL/L/fl-oz markings labels actually use all resolve;
    # household phrases with no fixed size don't.
    assert foods_api._serving_in_base(60, "g") == (60.0, "g")
    assert foods_api._serving_in_base(2, "oz") == (56.7, "g")
    assert foods_api._serving_in_base(0.5, "kg") == (500.0, "g")
    assert foods_api._serving_in_base(8, "fl oz") == (236.59, "ml")
    assert foods_api._serving_in_base(33, "cl") == (330.0, "ml")
    assert foods_api._serving_in_base(1, "cup") is None
    assert foods_api._serving_in_base(None, "g") is None
    assert foods_api._serving_in_base(0, "g") is None


def _fdc(description, data_type="Branded", brand="", gtin="", published="", fdc_id=1):
    """A minimal FDC search hit for ranking tests."""
    return {
        "fdcId": fdc_id,
        "description": description,
        "dataType": data_type,
        "brandName": brand,
        "gtinUpc": gtin,
        "publishedDate": published,
        "foodNutrients": [],
    }


def _fdc_energy(fdc_id, description, nutrients):
    """An FDC hit carrying specific (nutrientNumber, value) energy readings."""
    return {
        "fdcId": fdc_id,
        "description": description,
        "dataType": "Foundation",
        "foodNutrients": [{"nutrientNumber": num, "value": val} for num, val in nutrients],
    }


def test_usda_kilojoule_energy_is_rescued():
    # Only nutrient 268 (kJ) present: convert to kcal so the food isn't dropped.
    hit = _fdc_energy(1, "Muesli", [("268", 1500)])
    assert foods_api._usda_food_result(hit).calories == 358.5  # 1500 / 4.184
    # kcal wins when both are present.
    both = _fdc_energy(2, "Muesli", [("208", 360), ("268", 1500)])
    assert foods_api._usda_food_result(both).calories == 360
    # neither present: no calories.
    assert foods_api._usda_food_result(_fdc_energy(3, "Water", [])).calories is None


def test_search_drops_calorie_less_results(monkeypatch):
    # A food with no energy at all is filtered out before the limit; a kJ-only
    # food survives via the rescue.
    payload = {
        "foods": [
            _fdc_energy(1, "Real Oats", [("208", 380)]),
            _fdc_energy(2, "Kilojoule Oats", [("268", 1500)]),
            _fdc_energy(3, "Mystery Oats", []),
        ]
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(foods_api.httpx, "get", lambda *a, **k: FakeResponse())
    results = foods_api.search_usda("oats", "test-key")
    ids = {r.source_id for r in results}
    assert ids == {"1", "2"}  # the calorie-less "3" is gone
    kj = next(r for r in results if r.source_id == "2")
    assert kj.calories == 358.5


def test_off_kilojoule_energy_is_rescued(monkeypatch):
    # An Open Food Facts product with only energy-kj_100g gains kcal.
    payload = {
        "status": 1,
        "product": {
            "product_name": "Euro Biscuits",
            "brands": "Continental",
            "nutriments": {"energy-kj_100g": 1800, "proteins_100g": 6},
        },
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(foods_api.httpx, "get", lambda *a, **k: FakeResponse())
    result = foods_api.lookup_barcode_off("5901234123457")
    assert result is not None
    assert result.calories == 430.2  # 1800 / 4.184


def test_barcode_keeps_a_calorie_less_product(monkeypatch):
    # A scan is a deliberate single product: return it even with no energy.
    payload = {
        "status": 1,
        "product": {"product_name": "Sparkling Water", "brands": "Fizz", "nutriments": {}},
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(foods_api.httpx, "get", lambda *a, **k: FakeResponse())
    result = foods_api.lookup_barcode_off("1234567890123")
    assert result is not None
    assert result.calories is None
    assert result.name == "Sparkling Water"


def test_search_ranking_dedupes_branded_by_gtin():
    # The same product listed twice (zero-padded EAN vs bare UPC); newest wins.
    old = _fdc("Instant Oats", brand="Quaker", gtin="030000012345", published="2020-01-01")
    new = _fdc("Instant Oats", brand="Quaker", gtin="0030000012345", published="2024-06-01", fdc_id=2)
    ranked = foods_api._rank_usda("oats", [old, new])
    assert len(ranked) == 1
    assert ranked[0]["fdcId"] == 2


def test_search_ranking_dedupes_branded_by_brand_and_name():
    a = _fdc("INSTANT OATS", brand="Quaker", published="2020-01-01")
    b = _fdc("Instant  Oats!", brand="QUAKER", published="2023-01-01", fdc_id=2)
    ranked = foods_api._rank_usda("oats", [a, b])
    assert len(ranked) == 1
    assert ranked[0]["fdcId"] == 2


def test_search_ranking_prefers_query_word_coverage():
    generic = _fdc("Oats, raw", data_type="Foundation")
    quaker = _fdc("Instant Oats, 1 Minute", brand="Quaker", fdc_id=2)
    ranked = foods_api._rank_usda("quaker instant oats", [generic, quaker])
    assert [f["fdcId"] for f in ranked] == [2, 1]


def test_generic_query_keeps_foundation_first():
    # Equal word coverage: the lab-analysed entry outranks the label one even
    # when FDC returned it later.
    branded = _fdc("Chicken Breast", brand="Somebrand")
    foundation = _fdc("Chicken Breast", data_type="Foundation", fdc_id=2)
    ranked = foods_api._rank_usda("chicken breast", [branded, foundation])
    assert [f["fdcId"] for f in ranked] == [2, 1]


def test_query_words_match_as_prefixes():
    # "oat" should still hit "oats" — coverage counts prefixes.
    hit = _fdc("Rolled Oats", brand="Bobs", fdc_id=1)
    miss = _fdc("Wheat Flakes", brand="Bobs", fdc_id=2)
    ranked = foods_api._rank_usda("oat", [miss, hit])
    assert ranked[0]["fdcId"] == 1


def test_shouty_names_are_title_cased():
    assert foods_api._display("QUAKER INSTANT OATMEAL") == "Quaker Instant Oatmeal"
    assert foods_api._display("Log Cabin Original Syrup") == "Log Cabin Original Syrup"
    assert foods_api._display("2% MILK") == "2% Milk"
    assert foods_api._display("") == ""


def test_gtin_normalization():
    assert foods_api._norm_gtin("0030000012345") == "30000012345"
    assert foods_api._norm_gtin("030000012345") == "30000012345"
    assert foods_api._norm_gtin(" 0300-0001 2345") == "30000012345"
    assert foods_api._norm_gtin(None) == ""


def _usda_hit(code):
    return foods_api.FoodResult(
        "usda", code, "Pure Maple Syrup", "Butternut Mountain Farm",
        333.0, 0.0, 87.0, 0.0, serving="1/4 cup (60 ml)",
        serving_amount=60.0, base_unit="ml",
    )


def test_barcode_prefers_usda_branded(owner, monkeypatch):
    code = "022200001234"

    def must_not_be_called(c):
        raise AssertionError("OFF must not be asked when USDA answers")

    monkeypatch.setattr(settings, "usda_api_key", "test-key")
    monkeypatch.setattr(foods_api, "lookup_barcode_usda", lambda c, k: _usda_hit(c))
    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    body = owner.get(f"/foods/barcode/{code}").json()
    assert body["source"] == "usda"
    assert body["source_id"] == code
    assert body["name"] == "Pure Maple Syrup"

    # Second scan: answered from the shared cache, neither API asked.
    def usda_must_not(c, k):
        raise AssertionError("cache should answer the re-scan")

    monkeypatch.setattr(foods_api, "lookup_barcode_usda", usda_must_not)
    again = owner.get(f"/foods/barcode/{code}").json()
    assert again["id"] == body["id"]


def test_barcode_falls_back_to_off(owner, monkeypatch):
    code = "5901234123457"
    monkeypatch.setattr(foods_api, "lookup_barcode_usda", lambda c, k: None)
    monkeypatch.setattr(
        foods_api,
        "lookup_barcode_off",
        lambda c: foods_api.FoodResult("off", c, "Biscuits", "Foreign Brand", 480.0, 6.0, 60.0, 22.0),
    )
    body = owner.get(f"/foods/barcode/{code}").json()
    assert body["source"] == "off"
    assert body["name"] == "Biscuits"


def test_barcode_usda_error_still_tries_off(owner, monkeypatch):
    code = "4001234567890"

    def usda_down(c, k):
        raise foods_api.FoodApiError("down")

    monkeypatch.setattr(foods_api, "lookup_barcode_usda", usda_down)
    monkeypatch.setattr(
        foods_api,
        "lookup_barcode_off",
        lambda c: foods_api.FoodResult("off", c, "Rye Crispbread", "", 350.0, 10.0, 70.0, 2.0),
    )
    assert owner.get(f"/foods/barcode/{code}").status_code == 200


def test_barcode_404_when_both_miss(owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_usda", lambda c, k: None)
    monkeypatch.setattr(foods_api, "lookup_barcode_off", lambda c: None)
    assert owner.get("/foods/barcode/9999999999999").status_code == 404


def test_usda_barcode_requires_exact_gtin(monkeypatch):
    # FDC's text search fuzzy-matches digits: only an exact normalised gtin
    # counts, and among duplicates the newest label wins.
    payload = {
        "foods": [
            {"fdcId": 1, "description": "Wrong Product", "dataType": "Branded",
             "gtinUpc": "099900001111", "publishedDate": "2024-01-01", "foodNutrients": []},
            {"fdcId": 2, "description": "Old Label", "dataType": "Branded",
             "gtinUpc": "0022200001234", "publishedDate": "2019-01-01", "foodNutrients": []},
            {"fdcId": 3, "description": "New Label", "dataType": "Branded",
             "gtinUpc": "022200001234", "publishedDate": "2023-05-01", "foodNutrients": []},
        ]
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(foods_api.httpx, "get", lambda *a, **k: FakeResponse())
    result = foods_api.lookup_barcode_usda("022200001234", "test-key")
    assert result is not None
    assert result.name == "New Label"
    assert result.source_id == "022200001234"

    payload["foods"] = payload["foods"][:1]
    assert foods_api.lookup_barcode_usda("022200001234", "test-key") is None
    assert foods_api.lookup_barcode_usda("022200001234", "") is None


# ---- volume-signal classification ---------------------------------------------------
# Labels routinely stamp a drink's serving with a mass unit; the human serving
# text carries the real volume. These pin the classifier directly (it had none)
# plus the cache-hit heal for rows scanned before the fix.


def test_volume_text_classifies_a_grams_labelled_liquid_as_millilitres():
    # The real failing case: USDA gives servingSize 30 / servingSizeUnit "g" but
    # the household text says "2 Tbsp (30mL)"; the metric mark wins. Stating the
    # serving both ways also gives up the density, alongside and not instead.
    assert foods_api._serving_fields(30, "g", "2 Tbsp (30mL)") == {
        "serving_amount": 30.0,
        "base_unit": "ml",
        "density_g_per_ml": 1.0,
    }
    # bare metric and fl oz phrasings both read as a volume
    assert foods_api._serving_fields(None, None, "240 ml") == {
        "serving_amount": 240.0,
        "base_unit": "ml",
    }
    assert foods_api._serving_fields(None, None, "8 fl oz")["base_unit"] == "ml"
    # a household spoon with no gram companion still converts
    assert foods_api._serving_fields(None, None, "1 tbsp")["base_unit"] == "ml"


def test_volume_text_leaves_solids_as_grams():
    # A solid's household text names no volume, so the source's grams stand.
    assert foods_api._serving_fields(21, "g", "1 slice (21 g)") == {
        "serving_amount": 21.0,
        "base_unit": "g",
    }
    # a cup measure sitting beside a gram weight is a solid (cereal), not a drink
    assert foods_api._serving_fields(30, "g", "0.75 cup (30 g)") == {
        "serving_amount": 30.0,
        "base_unit": "g",
    }


def test_bare_household_cup_with_gram_fields_stays_grams():
    # USDA's real shape: the household text is BARE ("1 cup"); the gram weight
    # lives in servingSize/servingSizeUnit, never in the phrase. That pair is a
    # cup-measured solid; without the field-mass seed it would classify as
    # 236.59 mL and inflate "1 serving" of a 39 g cereal about sixfold.
    f = {
        **_fdc("Toasted Oat Cereal", brand="Big G"),
        "servingSize": 39,
        "servingSizeUnit": "g",
        "householdServingFullText": "1 cup",
    }
    result = foods_api._usda_food_result(f)
    assert result.base_unit == "g" and result.serving_amount == 39.0
    # a metric mark beside the same gram fields still wins (the half & half fix)
    f["servingSize"] = 30
    f["householdServingFullText"] = "2 Tbsp (30mL)"
    result = foods_api._usda_food_result(f)
    assert result.base_unit == "ml" and result.serving_amount == 30.0


def test_exact_volume_fields_outrank_a_converted_household_phrase():
    # When the source's own fields already carry an exact millilitre size, a
    # bare spoon/cup phrase must not replace it with its lossy conversion.
    assert foods_api._serving_fields(30, "ml", "2 tbsp") == {
        "serving_amount": 30.0,
        "base_unit": "ml",
    }
    assert foods_api._serving_fields(240, "ml", "1 cup") == {
        "serving_amount": 240.0,
        "base_unit": "ml",
    }
    # a metric mark in the phrase agrees with the fields; either path lands 30
    assert foods_api._serving_fields(30, "ml", "2 Tbsp (30mL)") == {
        "serving_amount": 30.0,
        "base_unit": "ml",
    }


def test_fraction_servings_never_parse_as_their_denominator():
    # "1/4 cup" must not read as "4 cup"; the fraction token is skipped and the
    # gram fields decide.
    assert foods_api._serving_fields(28, "g", "1/4 cup") == {
        "serving_amount": 28.0,
        "base_unit": "g",
    }
    assert foods_api._volume_from_text("1/2 cup") is None


def test_absurd_volume_readings_are_rejected():
    # A vandalized record's digit string must never cache a non-finite or
    # kiloliter-scale serving.
    assert foods_api._volume_from_text("9" * 400 + " ml") is None
    assert foods_api._volume_from_text("50000 ml") is None
    assert foods_api._volume_from_text("11 l") is None


def test_off_infers_volume_when_the_unit_is_missing(monkeypatch):
    # Open Food Facts often omits serving_quantity_unit; the serving_size text
    # then decides. The old "or 'g'" default would have mislabelled this drink.
    payload = {
        "status": 1,
        "product": {
            "product_name": "Almond Milk",
            "brands": "Silk",
            "serving_size": "240 ml",
            "serving_quantity": 240,
            "nutriments": {"energy-kcal_100g": 17, "proteins_100g": 0.5},
        },
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(foods_api.httpx, "get", lambda *a, **k: FakeResponse())
    result = foods_api.lookup_barcode_off("3450000000001")
    assert result is not None
    assert result.base_unit == "ml" and result.serving_amount == 240.0
    # and a product with no parseable serving stays unstructured (not grams)
    payload["product"]["serving_size"] = "one scoop"
    payload["product"].pop("serving_quantity")
    result = foods_api.lookup_barcode_off("3450000000001")
    assert result.serving_amount is None and result.base_unit == "g"


def test_cache_hit_heals_a_mislabelled_liquid(owner, monkeypatch):
    # A liquid cached as grams before the fix (its serving names a volume) is
    # reclassified to millilitres on the next scan, numbers preserved.
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, "Half & Half", "Land O Lakes",
            130.0, 3.0, 3.0, 12.0,
            serving="2 Tbsp (30mL)", serving_amount=30.0, base_unit="g",
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", off_hit)
    first = owner.get("/foods/barcode/4111111111111").json()
    assert first["base_unit"] == "g"  # cached wrong, as a pre-fix scan would

    def must_not_be_called(code):
        raise AssertionError("the heal must not re-hit the network")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/barcode/4111111111111").json()
    assert again["id"] == first["id"]  # same cached row, flipped in place
    assert again["base_unit"] == "ml"
    assert again["servings"][0]["grams"] == 30.0  # the numbers are untouched


def test_cache_hit_leaves_a_solid_alone(owner, monkeypatch):
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, "Pita", "Athens", 275.0, 8.0, 53.0, 5.0,
            serving="1 slice (21 g)", serving_amount=21.0, base_unit="g",
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", off_hit)
    owner.get("/foods/barcode/4222222222222")

    def must_not_be_called(code):
        raise AssertionError("the heal must not re-hit the network")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/barcode/4222222222222").json()
    assert again["base_unit"] == "g"


def test_cache_hit_never_heals_on_a_bare_household_name(owner, monkeypatch):
    # A cached solid whose serving name is only a bare cup ("0.75 cup" cereal,
    # grams 30) is ambiguous: the heal demands an unambiguous metric/fl-oz mark
    # and must leave it alone. Every real pre-fix liquid casualty carries one.
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, "Toasted Oats", "Big G", 367.0, 12.0, 73.0, 6.0,
            serving="0.75 cup", serving_amount=30.0, base_unit="g",
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", off_hit)
    owner.get("/foods/barcode/4333333333333")

    def must_not_be_called(code):
        raise AssertionError("the heal must not re-hit the network")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/barcode/4333333333333").json()
    assert again["base_unit"] == "g"
    assert again["servings"][0]["grams"] == 30.0


def test_usda_serving_drops_junk_household_and_maps_unece_codes():
    # A scraped label header as the household text is dropped, and the UNECE
    # unit code becomes a display unit: the soup entry yields just "120 mL".
    assert (
        foods_api._usda_serving(
            {"householdServingFullText": "Amount/serving", "servingSize": 120.0, "servingSizeUnit": "MLT"}
        )
        == "120 mL"
    )
    # GRM maps to g.
    assert (
        foods_api._usda_serving(
            {"householdServingFullText": "", "servingSize": 30.0, "servingSizeUnit": "GRM"}
        )
        == "30 g"
    )
    # A real household text is kept alongside the mapped size.
    assert (
        foods_api._usda_serving(
            {"householdServingFullText": "1/2 cup", "servingSize": 120.0, "servingSizeUnit": "ml"}
        )
        == "1/2 cup (120 mL)"
    )
    # An unrecognised unit code passes through unchanged.
    assert (
        foods_api._usda_serving(
            {"householdServingFullText": "", "servingSize": 1.0, "servingSizeUnit": "IU"}
        )
        == "1 IU"
    )


def test_clean_serving_name_behaviour_and_idempotence():
    cases = {
        "Amount/serving (120 MLT)": "120 mL",
        "2 Tbsp (30mL)": "2 Tbsp (30mL)",
        "28.3g": "28.3g",
        "1 serving (28.3 g)": "1 serving (28.3 g)",
        "0.75 cup": "0.75 cup",
        "1 cup (240 MLT)": "1 cup (240 mL)",
        # A vulgar fraction counts as a number: not a junk household header.
        "½ cup serving (120 mL)": "½ cup serving (120 mL)",
    }
    for raw, want in cases.items():
        assert foods_api._clean_serving_name(raw) == want
        # Idempotent: applying twice equals once.
        assert foods_api._clean_serving_name(want) == want


def test_cache_hit_heals_junk_serving_names(owner, monkeypatch):
    # A pre-fix row cached with a raw USDA serving name ("Amount/serving (120
    # MLT)") is rewritten to its display form ("120 mL") on the next scan.
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, "Chicken Soup", "Campbell's",
            40.0, 2.0, 5.0, 1.0,
            serving="Amount/serving (120 MLT)", serving_amount=120.0, base_unit="ml",
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", off_hit)
    first = owner.get("/foods/barcode/4444444444444").json()
    assert first["servings"][0]["name"] == "Amount/serving (120 MLT)"

    def must_not_be_called(code):
        raise AssertionError("the heal must not re-hit the network")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/barcode/4444444444444").json()
    assert again["id"] == first["id"]
    assert again["servings"][0]["name"] == "120 mL"

    # Idempotent: a third scan leaves the healed name in place.
    third = owner.get("/foods/barcode/4444444444444").json()
    assert third["servings"][0]["name"] == "120 mL"


def test_cache_hit_name_heal_enables_liquid_heal_same_request(owner, monkeypatch):
    # A row cached as grams whose serving name is only a junk-wrapped UNECE
    # code heals the NAME to "120 mL" first, which then carries the unambiguous
    # metric mark the liquid heal needs, so the same scan also flips the unit.
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, "Broth", "Swanson",
            30.0, 1.0, 2.0, 0.5,
            serving="Amount/serving (120 MLT)", serving_amount=120.0, base_unit="g",
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", off_hit)
    first = owner.get("/foods/barcode/4555555555555").json()
    assert first["base_unit"] == "g"  # cached wrong, as a pre-fix scan would

    def must_not_be_called(code):
        raise AssertionError("the heal must not re-hit the network")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    again = owner.get("/foods/barcode/4555555555555").json()
    assert again["servings"][0]["name"] == "120 mL"
    assert again["base_unit"] == "ml"


def test_scan_never_renames_a_custom_food(owner):
    # A family's own custom food resolves before the heal, so a weird serving
    # name is left exactly as entered (the heal touches shared cache rows only).
    made = owner.post(
        "/foods",
        json=_food(
            "Homemade Broth", barcode="4666666666666",
            servings=[{"name": "Amount/serving (120 MLT)", "grams": 120}],
        ),
    )
    assert made.status_code == 201, made.text
    scanned = owner.get("/foods/barcode/4666666666666").json()
    assert scanned["servings"][0]["name"] == "Amount/serving (120 MLT)"


# ---- energy consistency ------------------------------------------------------------
# Calories can never sit materially below what a food's SUGARS alone account for.
# A source row that breaks that mixed its units up somewhere (his maple syrup
# read 78 kcal against sugars worth 96); the correction is deliberately
# one-sided, so a drink whose alcohol carries energy no macro column names is
# left alone, and the floor is built on sugars so a sugar-alcohol product's
# perfectly legal label survives untouched.


def _result(**overrides):
    base = {
        "source": "off", "source_id": "1", "name": "Sample", "brand": "",
        "calories": None, "protein_g": None, "carbs_g": None, "fat_g": None,
    }
    base.update(overrides)
    return foods_api.FoodResult(**base)


def test_calories_below_the_sugars_are_corrected():
    # Syrup: 90 g of sugar is 360 kcal on its own, whatever the row claimed.
    fixed = foods_api._fix_energy(
        _result(calories=260.0, protein_g=0.0, carbs_g=90.0, fat_g=0.0, sugar_g=90.0)
    )
    assert fixed.calories == 360.0


def test_a_sugar_alcohol_label_is_left_alone():
    # Erythritol: 98 g of carbohydrate, none of it sugar, 20 kcal. A legal label
    # and a physically real one — polyols carry next to no energy — and a floor
    # built on total carbs would have "corrected" it to 392.
    fixed = foods_api._fix_energy(
        _result(calories=20.0, protein_g=0.0, carbs_g=98.0, fat_g=0.0, sugar_g=0.0)
    )
    assert fixed.calories == 20.0


def test_calories_above_the_sugars_are_left_alone():
    # Alcohol carries 7 kcal a gram and appears in no macro column, so a figure
    # well above what the macros account for is honest.
    fixed = foods_api._fix_energy(
        _result(calories=500.0, protein_g=0.0, carbs_g=20.0, fat_g=0.0, sugar_g=20.0)
    )
    assert fixed.calories == 500.0


def test_energy_guard_skips_what_it_cannot_judge():
    # No sugars datum is not judgeable at all, and neither is a row with no
    # calorie figure to check.
    assert foods_api._fix_energy(_result(calories=5.0, carbs_g=90.0)).calories == 5.0
    assert foods_api._fix_energy(_result(carbs_g=90.0, sugar_g=90.0)).calories is None
    # Trace sugars: the floor is too small for the comparison to mean anything.
    assert foods_api._fix_energy(_result(calories=1.0, sugar_g=4.0)).calories == 1.0


def test_the_repair_gives_fibre_its_allowance():
    # 30 g of carbs, 25 sugar and 20 fibre, claiming 10 kcal. The sugars alone
    # trip the floor; the repair is the full Atwater sum less the fibre that
    # passes through unburned (120 - 40), not the raw 120.
    fixed = foods_api._fix_energy(
        _result(calories=10.0, carbs_g=30.0, sugar_g=25.0, fiber_g=20.0)
    )
    assert fixed.calories == 80.0


def test_off_lookup_corrects_a_broken_energy_row(monkeypatch):
    # The maple syrup as Open Food Facts served it: energy per 100 g beside
    # carbohydrate per 100 mL.
    payload = {
        "status": 1,
        "product": {
            "product_name": "Organic Maple Syrup",
            "brands": "Kirkland",
            "nutriments": {
                "energy-kcal_100g": 78,
                "carbohydrates_100g": 90,
                "sugars_100g": 90,
                "proteins_100g": 0,
                "fat_100g": 0,
            },
        },
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(foods_api.httpx, "get", lambda *a, **k: FakeResponse())
    result = foods_api.lookup_barcode_off("0096619016273")
    assert result.calories == 360.0


# ---- shared-cache refresh ----------------------------------------------------------
# Sources correct their own records; a cache row that never refetched served the
# mistake forever. A row older than 30 days (or of unknown age) is re-read on its
# next scan.


def _cache_session(app):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=app.state.test_engine, expire_on_commit=False)


def _cache_row(app, code: str):
    """The shared cache row for a barcode, servings loaded, detached."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Food

    with _cache_session(app)() as db:
        return db.scalar(
            select(Food)
            .where(Food.source_id == code, Food.family_id.is_(None))
            .options(selectinload(Food.servings))
            .order_by(Food.id.desc())
        )


def _age_cache(app, code: str, days=None):
    """Push a cached row's fetched_at back; None leaves it never-stamped, the
    way every row written before the column reads."""
    from sqlalchemy import select

    from app.models import Food

    with _cache_session(app)() as db:
        row = db.scalar(
            select(Food)
            .where(Food.source_id == code, Food.family_id.is_(None))
            .order_by(Food.id.desc())
        )
        row.fetched_at = (
            None
            if days is None
            else dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        )
        db.commit()


def _syrup(calories, carbs, name="Maple Syrup", serving_amount=60.0):
    def off_hit(code):
        return foods_api.FoodResult(
            "off", code, name, "Kirkland", calories, 0.0, carbs, 0.0,
            serving=f"{serving_amount:g} mL", serving_amount=serving_amount,
            base_unit="ml",
        )

    return off_hit


CODE = "0096619016273"


def test_a_stale_cache_row_is_refetched_on_the_next_scan(app, owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", _syrup(260.0, 65.0))
    first = owner.get(f"/foods/barcode/{CODE}").json()
    assert first["calories"] == 260.0

    _age_cache(app, CODE, days=45)
    monkeypatch.setattr(
        foods_api, "lookup_barcode_off",
        _syrup(360.0, 90.0, name="Organic Maple Syrup", serving_amount=30.0),
    )
    again = owner.get(f"/foods/barcode/{CODE}").json()
    assert again["id"] == first["id"]  # the same row, corrected in place
    assert again["calories"] == 360.0 and again["carbs_g"] == 90.0
    assert again["name"] == "Organic Maple Syrup"
    assert [s["grams"] for s in again["servings"]] == [30.0]
    assert _cache_row(app, CODE).fetched_at is not None


def test_a_cache_row_of_unknown_age_is_refetched(app, owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", _syrup(260.0, 65.0))
    owner.get(f"/foods/barcode/{CODE}")
    _age_cache(app, CODE, days=None)  # as a row written before the column reads

    monkeypatch.setattr(foods_api, "lookup_barcode_off", _syrup(360.0, 90.0))
    assert owner.get(f"/foods/barcode/{CODE}").json()["calories"] == 360.0


def test_a_fresh_cache_row_never_leaves_the_server(owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", _syrup(260.0, 65.0))
    owner.get(f"/foods/barcode/{CODE}")

    def must_not_be_called(code):
        raise AssertionError("a fresh cache row must not refetch")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    assert owner.get(f"/foods/barcode/{CODE}").json()["calories"] == 260.0


def test_a_family_custom_food_is_never_refetched(app, owner, monkeypatch):
    # It resolves before the cache lookup, so nothing ages it or re-reads it.
    def must_not_be_called(code):
        raise AssertionError("a custom food must not refetch")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    made = _custom_food(owner, barcode="4099999999991")
    scanned = owner.get("/foods/barcode/4099999999991").json()
    assert scanned["id"] == made["id"]
    with _cache_session(app)() as db:
        from app.models import Food

        assert db.get(Food, made["id"]).fetched_at is None


def test_a_refetch_that_cannot_reach_the_network_changes_nothing(app, owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", _syrup(260.0, 65.0))
    owner.get(f"/foods/barcode/{CODE}")
    _age_cache(app, CODE, days=45)
    stamped = _cache_row(app, CODE).fetched_at

    def boom(code):
        raise foods_api.FoodApiError("down")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", boom)
    again = owner.get(f"/foods/barcode/{CODE}").json()
    assert again["calories"] == 260.0  # the cached copy still answers
    # Left unstamped as well, so the next scan tries again rather than waiting
    # out another month on a moment's outage.
    assert _cache_row(app, CODE).fetched_at == stamped


def test_a_product_gone_upstream_is_stamped_and_still_served(app, owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode_off", _syrup(260.0, 65.0))
    owner.get(f"/foods/barcode/{CODE}")
    _age_cache(app, CODE, days=45)
    old = _cache_row(app, CODE).fetched_at

    monkeypatch.setattr(foods_api, "lookup_barcode_off", lambda code: None)
    again = owner.get(f"/foods/barcode/{CODE}").json()
    assert again["calories"] == 260.0  # the copy we have is all there is
    fresh = _cache_row(app, CODE).fetched_at
    assert fresh != old  # stamped anyway: don't re-ask for another month

    def must_not_be_called(code):
        raise AssertionError("a stamped miss must not refetch")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    assert owner.get(f"/foods/barcode/{CODE}").status_code == 200


# ---- density from the label --------------------------------------------------------
# A label that states its serving BOTH ways ("1 tbsp (21 g)") gives up what a
# millilitre of the food weighs, which is what lets the diary log it in any unit.


def test_density_from_gram_fields_and_a_volume_phrase():
    # USDA's shape: 21 g in the fields, the spoon in the household text. The
    # base unit stays grams (a bare spoon is no proof of a liquid) and the
    # density rides alongside: 21 g in the 14.79 mL the spoon parsed to.
    fields = foods_api._serving_fields(21, "GRM", "1 tbsp")
    assert fields["base_unit"] == "g" and fields["serving_amount"] == 21.0
    assert fields["density_g_per_ml"] == 1.4199


def test_density_from_millilitre_fields_and_a_gram_phrase():
    # The other way round: the fields measure volume and the phrase names the
    # weight, so the reading is still two-sided.
    fields = foods_api._serving_fields(15, "ml", "1 tbsp (21 g)")
    assert fields["base_unit"] == "ml" and fields["serving_amount"] == 15.0
    assert fields["density_g_per_ml"] == 1.4


def test_an_out_of_range_density_is_dropped():
    # Cereal: 30 g measured by a bare 0.75 cup reads as 0.17 g/mL, which is a
    # misread rather than a discovery, so nothing is stored.
    assert "density_g_per_ml" not in foods_api._serving_fields(30, "GRM", "0.75 cup")
    # And a label naming only one measure has nothing to derive from.
    assert "density_g_per_ml" not in foods_api._serving_fields(21, "GRM", "1 slice")


def test_a_scanned_food_keeps_its_density_through_a_refresh(app, owner, monkeypatch):
    def syrup(density):
        return lambda code: foods_api.FoodResult(
            "off", code, "Maple Syrup", "Kirkland", 260.0, 0.0, 65.0, 0.0,
            serving="1 tbsp (21 g)", serving_amount=15.0, base_unit="ml",
            density_g_per_ml=density,
        )

    monkeypatch.setattr(foods_api, "lookup_barcode_off", syrup(1.4))
    assert owner.get(f"/foods/barcode/{CODE}").json()["density_g_per_ml"] == 1.4

    # A refetch carries the source's current answer, density included.
    _age_cache(app, CODE, days=45)
    monkeypatch.setattr(foods_api, "lookup_barcode_off", syrup(1.32))
    assert owner.get(f"/foods/barcode/{CODE}").json()["density_g_per_ml"] == 1.32


def test_a_custom_food_round_trips_a_scanned_density(owner):
    # "Save as custom food" after a scan keeps what a millilitre weighs, so the
    # family's own copy converts exactly like the cache row it came from.
    made = owner.post(
        "/foods",
        json=_food("Maple Syrup", base_unit="ml", density_g_per_ml=1.32),
    )
    assert made.status_code == 201, made.text
    assert made.json()["density_g_per_ml"] == 1.32
    # An edit that sends it back keeps it; a hand-made food simply has none.
    plain = owner.post("/foods", json=_food("Hand Made"))
    assert plain.json()["density_g_per_ml"] is None
