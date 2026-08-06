"""Family recipe box: who can create/edit/delete, structured ingredients,
computed per-serving nutrition, food caching, and cross-family isolation."""


# A USDA-style ingredient line (an un-saved search result being used the first
# time). Per-100g macros; `amount` grams of it get scaled into the recipe.
def usda_line(source_id="12345", name="Ground beef, 85/15", **overrides):
    return {"source": "usda", "source_id": source_id, "name": name, "brand": "",
            "calories": 250.0, "protein_g": 26.0, "carbs_g": 0.0, "fat_g": 17.0,
            "amount": 200, "unit": "g", **overrides}


def make_recipe(client, **overrides):
    payload = {"name": "Taco Bowls", "servings": 4, "steps": "Cook it.",
               "ingredients": [usda_line()], **overrides}
    res = client.post("/recipes", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_parent_creates_a_recipe_with_computed_macros(owner):
    made = make_recipe(owner)
    assert made["name"] == "Taco Bowls"
    assert len(made["ingredients"]) == 1
    line = made["ingredients"][0]
    assert line["name"] == "Ground beef, 85/15" and line["grams"] == 200.0
    # 200 g of a 250-cal/100g food = 500 cal; over 4 servings = 125 per serving.
    assert line["calories"] == 500.0
    assert made["per_serving"]["calories"] == 125.0
    assert made["per_serving"]["protein_g"] == 13.0  # 52 g / 4

    box = owner.get("/recipes").json()
    assert [r["id"] for r in box] == [made["id"]]


def test_ounces_are_converted_to_grams(owner):
    made = make_recipe(owner, servings=1, ingredients=[usda_line(amount=4, unit="oz")])
    line = made["ingredients"][0]
    assert line["grams"] == 113.4  # 4 oz -> 113.398, rounded
    # 113.4 g of 250 cal/100g ~= 283.5 cal
    assert line["calories"] == 283.5


def test_recipe_can_be_saved_with_no_ingredients(owner):
    made = make_recipe(owner, name="Mystery Stew", ingredients=[])
    assert made["ingredients"] == []
    # No ingredient supplied any nutrient, so every total reads "unknown", not 0.
    assert all(v is None for v in made["per_serving"].values())
    assert "sugar_g" in made["per_serving"]  # the full label is reported


def test_food_is_cached_and_reused_across_recipes(owner):
    a = make_recipe(owner, name="Bowls A")
    b = make_recipe(owner, name="Bowls B")
    # Both used the same USDA source_id, so it was cached once and shared.
    fid_a = a["ingredients"][0]["food_id"]
    fid_b = b["ingredients"][0]["food_id"]
    assert fid_a == fid_b


def test_reusing_a_saved_food_by_id(owner):
    # A custom food is created up front, then referenced by id in a recipe.
    food = owner.post("/foods", json={"name": "Grandma's sauce",
                                      "servings": [{"name": "100 g", "grams": 100}],
                                      "basis_index": 0, "calories": 90,
                                      "protein_g": 2, "carbs_g": 12, "fat_g": 4}).json()
    made = make_recipe(owner, name="Saucy", servings=2, ingredients=[
        {"food_id": food["id"], "source": "custom", "name": "Grandma's sauce",
         "amount": 100, "unit": "g"}])
    assert made["ingredients"][0]["food_id"] == food["id"]
    assert made["per_serving"]["calories"] == 45.0  # 90 cal over 2 servings


def test_child_can_browse_but_not_change_recipes(owner, child):
    made = make_recipe(owner)
    assert any(r["id"] == made["id"] for r in child.get("/recipes").json())
    assert child.post("/recipes", json={"name": "Nope", "ingredients": []}).status_code == 403
    assert child.patch(f"/recipes/{made['id']}", json={"name": "Nope"}).status_code == 403
    assert child.delete(f"/recipes/{made['id']}").status_code == 403


def test_editing_replaces_ingredients(owner):
    made = make_recipe(owner)
    r = owner.patch(f"/recipes/{made['id']}", json={
        "name": "Taco Bowls v2",
        "ingredients": [usda_line(source_id="999", name="Turkey", calories=170,
                                  protein_g=22, carbs_g=0, fat_g=8, amount=100)],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Taco Bowls v2"
    assert len(body["ingredients"]) == 1 and body["ingredients"][0]["name"] == "Turkey"
    assert body["per_serving"]["calories"] == 42.5  # 170 over 4 servings


def test_editing_without_ingredients_key_leaves_them(owner):
    made = make_recipe(owner)
    r = owner.patch(f"/recipes/{made['id']}", json={"servings": 8})
    assert r.status_code == 200
    assert len(r.json()["ingredients"]) == 1  # untouched
    assert r.json()["per_serving"]["calories"] == 62.5  # 500 over 8 now


def test_duplicate_recipe_name_is_rejected(owner):
    make_recipe(owner, name="Chili")
    dupe = owner.post("/recipes", json={"name": "chili", "ingredients": []})
    assert dupe.status_code == 400


def test_deleting_a_recipe_takes_its_ingredients(owner):
    made = make_recipe(owner)
    assert owner.delete(f"/recipes/{made['id']}").status_code == 204
    assert owner.get(f"/recipes/{made['id']}").status_code == 404


def test_recipes_are_isolated_across_families(owner, other):
    made = make_recipe(owner, name="Secret Sauce")
    assert all(r["name"] != "Secret Sauce" for r in other.get("/recipes").json())
    assert other.get(f"/recipes/{made['id']}").status_code == 404
    assert other.delete(f"/recipes/{made['id']}").status_code == 404


def test_cannot_reference_another_familys_custom_food(owner, other):
    # Family B makes a custom food; family A can't sneak it into a recipe by id.
    food = other.post("/foods", json={"name": "B's rub",
                                      "servings": [{"name": "100 g", "grams": 100}],
                                      "basis_index": 0, "calories": 10}).json()
    res = owner.post("/recipes", json={"name": "Sneaky", "ingredients": [
        {"food_id": food["id"], "source": "custom", "name": "B's rub",
         "amount": 50, "unit": "g"}]})
    assert res.status_code == 404


# A liquid custom food, measured by volume (per-100mL after conversion).
def _volume_food(client, name="Almond milk", **over):
    body = {"name": name, "base_unit": "ml",
            "servings": [{"name": "1 cup", "grams": 240}], "basis_index": 0,
            "calories": 60, "protein_g": 2.4}
    body.update(over)
    return client.post("/foods", json=body).json()


def test_volume_food_scales_by_millilitres(owner):
    # 240 mL of a 25-cal/100mL food = 60 cal; also check fl oz -> mL conversion.
    milk = _volume_food(owner)
    made = make_recipe(owner, name="Milk", servings=1, ingredients=[
        {"food_id": milk["id"], "source": "custom", "name": "Almond milk",
         "amount": 240, "unit": "ml"}])
    line = made["ingredients"][0]
    assert line["unit"] == "ml" and line["grams"] == 240.0  # base amount is mL
    assert made["per_serving"]["calories"] == 60.0

    floz = owner.patch(f"/recipes/{made['id']}", json={"ingredients": [
        {"food_id": milk["id"], "source": "custom", "name": "Almond milk",
         "amount": 1, "unit": "floz"}]}).json()
    assert floz["ingredients"][0]["grams"] == 29.57  # 1 fl oz -> 29.5735 mL
    assert floz["per_serving"]["calories"] == 7.4  # 25 * 0.295735


def test_ingredient_units_may_cross_measure_families(owner):
    # A solid poured by the cup and a liquid weighed in grams both convert, the
    # same way the diary does it. Neither food's label ever stated both
    # readings, so both go through water.
    made = make_recipe(owner, name="Cupful", servings=1,
                       ingredients=[usda_line(amount=1, unit="cup")])
    line = made["ingredients"][0]
    assert line["unit"] == "cup" and line["grams"] == 236.59
    assert made["per_serving"]["calories"] == 591.5  # 250 cal/100g * 2.36588

    milk = _volume_food(owner)
    weighed = make_recipe(owner, name="Weighed", servings=1, ingredients=[
        {"food_id": milk["id"], "source": "custom", "name": "Almond milk",
         "amount": 100, "unit": "g"}])
    assert weighed["ingredients"][0]["grams"] == 100.0
    assert weighed["per_serving"]["calories"] == 25.0


def test_a_stated_density_drives_the_crossing(owner):
    # A label that gave both readings: 1.03 g per mL, so 103 g is 100 mL of it.
    milk = _volume_food(owner, name="Whole milk", density_g_per_ml=1.03)
    assert milk["density_g_per_ml"] == 1.03
    made = make_recipe(owner, name="Dense", servings=1, ingredients=[
        {"food_id": milk["id"], "source": "custom", "name": "Whole milk",
         "amount": 103, "unit": "g"}])
    assert made["ingredients"][0]["grams"] == 100.0
    assert made["per_serving"]["calories"] == 25.0


def test_the_recipe_path_persists_a_foods_family_and_density(owner):
    # A search or scan food is first saved when a recipe uses it. Its measure
    # family and density are stored with it, so every later surface converts the
    # way the picker previewed instead of assuming grams.
    line = usda_line(source_id="778899", name="Olive oil", amount=1, unit="tbsp")
    line["base_unit"] = "ml"
    line["density_g_per_ml"] = 0.91
    made = make_recipe(owner, name="Oiled", servings=1, ingredients=[line])
    out = made["ingredients"][0]
    assert out["base_unit"] == "ml" and out["density_g_per_ml"] == 0.91
    assert out["grams"] == 14.79  # a volume food in tbsp is plain millilitres


def test_recipe_mixes_mass_and_volume_ingredients(owner):
    # 200 g of 250-cal/100g beef (500) + 240 mL of 25-cal/100mL milk (60) = 560,
    # over 1 serving. Different measure families total together fine.
    milk = _volume_food(owner)
    made = make_recipe(owner, name="Mixed", servings=1, ingredients=[
        usda_line(amount=200, unit="g"),
        {"food_id": milk["id"], "source": "custom", "name": "Almond milk",
         "amount": 240, "unit": "ml"}])
    assert made["per_serving"]["calories"] == 560.0


def test_recipe_totals_the_full_nutrition_label(owner):
    # A recipe totals the whole label, not just the four base macros: 100 g of a
    # 20 g-sugar / 100 mg-sodium per-100g food, over 2 servings.
    food = owner.post("/foods", json={"name": "Sweet stuff",
                                      "servings": [{"name": "100 g", "grams": 100}],
                                      "basis_index": 0, "calories": 200,
                                      "sugar_g": 20, "sodium_mg": 100}).json()
    made = make_recipe(owner, name="Sweet", servings=2, ingredients=[
        {"food_id": food["id"], "source": "custom", "name": "Sweet stuff",
         "amount": 100, "unit": "g"}])
    assert made["per_serving"]["sugar_g"] == 10.0
    assert made["per_serving"]["sodium_mg"] == 50.0
    # a nutrient no food supplied still reads unknown, not a fake 0
    assert made["per_serving"]["cholesterol_mg"] is None


def test_recipe_ingredients_push_to_the_grocery_list(owner):
    recipe = make_recipe(owner, ingredients=[
        usda_line(),
        usda_line(source_id="777", name="Shredded cheddar", amount=4, unit="oz"),
    ])
    store = owner.post("/grocery/lists", json={"name": "Costco"}).json()

    res = owner.post(f"/recipes/{recipe['id']}/grocery", json={"list_id": store["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["added"] == 2

    state = owner.get("/grocery").json()
    titles = {i["title"]: i["list_id"] for i in state["items"]}
    assert titles["Ground beef, 85/15 · 200 g"] == store["id"]
    assert titles["Shredded cheddar · 4 oz"] == store["id"]

    # No list picked -> the items land in Unsorted (list_id NULL).
    owner.post(f"/recipes/{recipe['id']}/grocery", json={})
    state = owner.get("/grocery").json()
    assert sum(1 for i in state["items"] if i["list_id"] is None) == 2


def test_grocery_push_guards(owner, child, other):
    recipe = make_recipe(owner)
    empty = owner.post("/recipes", json={"name": "Empty", "servings": 1,
                                         "steps": "", "ingredients": []}).json()
    assert child.post(f"/recipes/{recipe['id']}/grocery", json={}).status_code == 403
    assert other.post(f"/recipes/{recipe['id']}/grocery", json={}).status_code == 404
    assert owner.post(f"/recipes/{empty['id']}/grocery", json={}).status_code == 400
    assert owner.post(f"/recipes/{recipe['id']}/grocery", json={"list_id": 999}).status_code == 400
