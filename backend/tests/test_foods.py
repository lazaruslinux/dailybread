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
