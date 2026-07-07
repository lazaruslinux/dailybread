"""Family recipe box: who can create/edit/delete, macros, and isolation."""


def make_recipe(client, **overrides):
    payload = {"name": "Taco Bowls", "servings": 4, "calories": 520,
               "protein_g": 31, "carbs_g": 45, "fat_g": 22,
               "ingredients": "Ground beef\nRice\nBeans", **overrides}
    res = client.post("/recipes", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_parent_creates_and_lists_a_recipe(owner):
    made = make_recipe(owner)
    assert made["name"] == "Taco Bowls"
    assert made["calories"] == 520 and made["protein_g"] == 31
    assert made["ingredients"].splitlines() == ["Ground beef", "Rice", "Beans"]

    box = owner.get("/recipes").json()
    assert [r["id"] for r in box] == [made["id"]]


def test_recipe_can_be_saved_without_macros(owner):
    # Macros are optional; a recipe can be saved before they're worked out.
    made = make_recipe(owner, name="Mystery Stew", calories=None, protein_g=None,
                       carbs_g=None, fat_g=None)
    assert made["calories"] is None and made["protein_g"] is None


def test_child_can_browse_but_not_change_recipes(owner, child):
    made = make_recipe(owner)
    # Kids see the recipe box...
    assert any(r["id"] == made["id"] for r in child.get("/recipes").json())
    # ...but can't create, edit, or delete.
    assert child.post("/recipes", json={"name": "Nope"}).status_code == 403
    assert child.patch(f"/recipes/{made['id']}", json={"name": "Nope"}).status_code == 403
    assert child.delete(f"/recipes/{made['id']}").status_code == 403


def test_editing_a_recipe_and_clearing_a_macro(owner):
    made = make_recipe(owner)
    # Rename + change a macro.
    r = owner.patch(f"/recipes/{made['id']}", json={"name": "Taco Bowls v2", "protein_g": 35})
    assert r.status_code == 200
    assert r.json()["name"] == "Taco Bowls v2" and r.json()["protein_g"] == 35
    # Sending a macro as null clears it; omitted fields stay.
    r = owner.patch(f"/recipes/{made['id']}", json={"calories": None})
    assert r.json()["calories"] is None
    assert r.json()["carbs_g"] == 45  # untouched


def test_duplicate_recipe_name_is_rejected(owner):
    make_recipe(owner, name="Chili")
    dupe = owner.post("/recipes", json={"name": "chili"})  # case-insensitive
    assert dupe.status_code == 400


def test_deleting_a_recipe(owner):
    made = make_recipe(owner)
    assert owner.delete(f"/recipes/{made['id']}").status_code == 204
    assert owner.get(f"/recipes/{made['id']}").status_code == 404


def test_recipes_are_isolated_across_families(owner, other):
    made = make_recipe(owner, name="Secret Sauce")
    # A different household never sees it, and can't fetch it by id.
    assert all(r["name"] != "Secret Sauce" for r in other.get("/recipes").json())
    assert other.get(f"/recipes/{made['id']}").status_code == 404
    assert other.delete(f"/recipes/{made['id']}").status_code == 404
