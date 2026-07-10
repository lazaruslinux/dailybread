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
    # A product used in a recipe once is cached; the next scan is served from
    # that cache without an outbound call.
    from tests.test_recipes import make_recipe, usda_line

    line = usda_line(source_id="3017620422003", name="Nutella")
    line["source"] = "off"
    make_recipe(owner, ingredients=[line])

    def must_not_be_called(code):
        raise AssertionError("barcode lookup left the server")

    monkeypatch.setattr(foods_api, "lookup_barcode_off", must_not_be_called)
    res = owner.get("/foods/barcode/3017620422003")
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "off" and res.json()["name"] == "Nutella"


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
