"""Food layer: server-proxied USDA search + Open Food Facts barcode, custom
foods, and cross-family isolation. External calls are mocked."""

from app import foods_api


def test_search_is_proxied(owner, monkeypatch):
    # The route calls foods_api.search_usda; mock it so no network is touched.
    def fake_search(query, api_key, limit=25):
        assert query == "ground beef"
        return [
            foods_api.FoodResult("usda", "12345", "Ground beef, 85/15", "Great Value",
                                 250.0, 26.0, 0.0, 17.0)
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


def test_custom_food_crud_and_permissions(owner, child):
    made = owner.post(
        "/foods",
        json={"name": "Grandma's sauce", "brand": "", "calories": 90,
              "protein_g": 2, "carbs_g": 12, "fat_g": 4},
    )
    assert made.status_code == 201, made.text
    fid = made.json()["id"]
    assert made.json()["source"] == "custom" and made.json()["id"] is not None

    # Everyone sees the family's custom foods; only parents add/remove.
    assert any(f["id"] == fid for f in child.get("/foods").json())
    assert child.post("/foods", json={"name": "Nope"}).status_code == 403
    assert child.delete(f"/foods/{fid}").status_code == 403

    assert owner.delete(f"/foods/{fid}").status_code == 204
    assert all(f["id"] != fid for f in owner.get("/foods").json())


def test_custom_foods_are_isolated_across_families(owner, other):
    made = owner.post("/foods", json={"name": "Secret Rub", "calories": 10})
    fid = made.json()["id"]
    assert all(f["name"] != "Secret Rub" for f in other.get("/foods").json())
    # B can't delete A's custom food (looks like it doesn't exist).
    assert other.delete(f"/foods/{fid}").status_code == 404
