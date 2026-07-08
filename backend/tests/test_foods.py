"""Food layer: server-proxied USDA search + Open Food Facts barcode, custom
foods, and cross-family isolation. External calls are mocked."""

from app import foods_api


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

    monkeypatch.setattr(foods_api, "lookup_barcode", fake_barcode)
    res = owner.get("/foods/barcode/3017620422003")
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Nutella" and res.json()["source"] == "off"


def test_barcode_not_found_is_404(owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode", lambda code: None)
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

    monkeypatch.setattr(foods_api, "lookup_barcode", must_not_be_called)
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
    monkeypatch.setattr(foods_api, "lookup_barcode", lambda code: None)
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

    monkeypatch.setattr(foods_api, "lookup_barcode", must_not_be_called)
    res = owner.get("/foods/barcode/3017620422003")
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "off" and res.json()["name"] == "Nutella"


def test_bad_barcodes_are_rejected(owner):
    assert owner.get("/foods/barcode/12ab34").status_code == 400
    assert owner.get("/foods/barcode/12345").status_code == 400  # too short
    res = owner.post("/foods", json={
        "name": "X", "servings": [{"name": "100 g", "grams": 100}],
        "basis_index": 0, "barcode": "not-digits",
    })
    assert res.status_code == 422


def test_editing_a_custom_food_keeps_or_updates_its_barcode(owner, monkeypatch):
    monkeypatch.setattr(foods_api, "lookup_barcode", lambda code: None)
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

    monkeypatch.setattr(foods_api, "lookup_barcode", off_hit)
    res = owner.get("/foods/barcode/4012345678901")
    assert res.status_code == 200, res.text
    first = res.json()
    assert first["id"] is not None  # cached immediately
    assert first["base_unit"] == "g"
    assert first["servings"] == [{"name": "1 pita (60 g)", "grams": 60.0}]

    def must_not_be_called(code):
        raise AssertionError("second scan left the server")

    monkeypatch.setattr(foods_api, "lookup_barcode", must_not_be_called)
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

    monkeypatch.setattr(foods_api, "lookup_barcode", off_hit)
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
