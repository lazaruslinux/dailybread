"""The nutrition diary: personal food logging with per-user targets.

Entries snapshot their nutrition at log time (server-computed, never
client-supplied), so later edits to a recipe or food never rewrite history.
Everything here is self-only: family members never see each other's diaries.
"""

import datetime as dt


TODAY = dt.date.today().isoformat()

# An id-less USDA search result, as the picker would send it: 100 kcal,
# 10 g protein, 20 g carbs, 2 g fat per 100 g.
OATS = {
    "source": "usda",
    "source_id": "111222",
    "name": "Rolled Oats",
    "brand": "",
    "calories": 100.0,
    "protein_g": 10.0,
    "carbs_g": 20.0,
    "fat_g": 2.0,
    "sugar_g": 1.0,
}


def log(client, **overrides):
    body = {"date_for": TODAY, "slot": "breakfast", "amount": 100, "unit": "g", **OATS}
    body.update(overrides)
    return client.post("/diary", json=body)


def day(client, date=TODAY):
    res = client.get(f"/diary?date={date}")
    assert res.status_code == 200, res.text
    return res.json()


# ---- logging and totals ---------------------------------------------------------


def test_logging_a_food_snapshots_served_nutrition(parent):
    res = log(parent, amount=200, time_of_day="07:30")
    assert res.status_code == 201, res.text
    entry = res.json()
    # 200 g of a per-100g food = 2x the label.
    assert entry["calories"] == 200.0
    assert entry["protein_g"] == 20.0
    assert entry["slot"] == "breakfast"
    assert entry["time_of_day"] == "07:30:00"

    d = day(parent)
    assert d["consumed"]["calories"] == 200.0
    assert d["consumed"]["carbs_g"] == 40.0
    assert len(d["entries"]) == 1


def test_totals_override_fills_in_missing_macros(parent):
    # A scanned product whose source has no carbs (the Open Food Facts gap):
    # the member fills it in from the label and the sheet sends explicit totals.
    res = log(
        parent,
        amount=52,
        carbs_g=None,
        totals={"calories": 100.0, "protein_g": 3.0, "carbs_g": 22.0, "fat_g": 0.0},
    )
    assert res.status_code == 201, res.text
    entry = res.json()
    assert entry["carbs_g"] == 22.0
    assert entry["calories"] == 100.0
    assert entry["fat_g"] == 0.0
    d = day(parent)
    assert d["consumed"]["carbs_g"] == 22.0


def test_totals_override_is_verbatim_not_scaled(parent):
    # The override is absolute per-entry totals, not per-100 to scale by amount.
    res = log(parent, amount=200, totals={"calories": 999.0, "protein_g": 1.0, "carbs_g": 2.0, "fat_g": 3.0})
    assert res.status_code == 201, res.text
    entry = res.json()
    assert entry["calories"] == 999.0  # not 200 (2x the label)
    assert entry["carbs_g"] == 2.0


def test_totals_override_omitted_field_records_unknown(parent):
    # A macro left blank in the editor stays None, same as a missing source value.
    res = log(parent, totals={"calories": 100.0, "protein_g": 3.0, "fat_g": 0.0})
    assert res.status_code == 201, res.text
    assert res.json()["carbs_g"] is None


def test_editing_a_corrected_entrys_portion_keeps_the_override(parent):
    # Fill in a scan's missing carbs, then resize the portion: the override must
    # scale with the snapshot, not revert to the food's (still empty) value.
    entry = log(
        parent,
        amount=52,
        carbs_g=None,
        totals={"calories": 100.0, "protein_g": 3.0, "carbs_g": 22.0, "fat_g": 0.0},
    ).json()
    assert entry["carbs_g"] == 22.0
    res = parent.patch(f"/diary/{entry['id']}", json={"amount": 104})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["carbs_g"] == 44.0  # scaled, not reverted to null
    assert body["calories"] == 200.0


def test_totals_sum_across_entries_and_days_stay_separate(parent):
    log(parent, amount=100)
    log(parent, amount=50, slot="lunch")
    d = day(parent)
    assert d["consumed"]["calories"] == 150.0

    other_day = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    log(parent, amount=100, date_for=other_day)
    assert day(parent)["consumed"]["calories"] == 150.0
    assert day(parent, other_day)["consumed"]["calories"] == 100.0


def test_mass_food_refuses_volume_units(parent):
    res = log(parent, amount=1, unit="cup")
    assert res.status_code == 400


def test_future_dates_are_refused_beyond_clock_tolerance(parent):
    far = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    assert log(parent, date_for=far).status_code == 400
    near = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    assert log(parent, date_for=near).status_code == 201


def test_logging_a_recipe_by_servings(owner):
    recipe = owner.post(
        "/recipes",
        json={
            "name": "Oat Bowl",
            "servings": 2,
            "ingredients": [{**OATS, "amount": 200, "unit": "g"}],
        },
    ).json()
    # Two servings of a two-serving recipe = the whole 200 g of oats.
    res = owner.post(
        "/diary",
        json={"date_for": TODAY, "slot": "dinner", "recipe_id": recipe["id"], "amount": 2},
    )
    assert res.status_code == 201, res.text
    entry = res.json()
    assert entry["name"] == "Oat Bowl"
    assert entry["calories"] == 200.0
    assert entry["recipe_id"] == recipe["id"]


def test_deleting_the_recipe_keeps_the_logged_entry(owner):
    recipe = owner.post(
        "/recipes",
        json={
            "name": "Vanishing Bowl",
            "servings": 1,
            "ingredients": [{**OATS, "amount": 100, "unit": "g"}],
        },
    ).json()
    entry = owner.post(
        "/diary",
        json={"date_for": TODAY, "slot": "lunch", "recipe_id": recipe["id"], "amount": 1},
    ).json()
    assert owner.delete(f"/recipes/{recipe['id']}").status_code == 204

    d = day(owner)
    kept = next(e for e in d["entries"] if e["id"] == entry["id"])
    assert kept["calories"] == 100.0  # snapshot survives
    assert kept["recipe_id"] is None  # reference is honestly gone

    # Editing the amount scales the snapshot linearly even without the recipe.
    res = owner.patch(f"/diary/{entry['id']}", json={"amount": 3})
    assert res.status_code == 200
    assert res.json()["calories"] == 300.0


def test_editing_amount_slot_and_time(parent):
    entry = log(parent, amount=100).json()
    res = parent.patch(
        f"/diary/{entry['id']}",
        json={"amount": 50, "slot": "snack", "time_of_day": "15:10"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["calories"] == 50.0
    assert body["slot"] == "snack"


def test_deleting_an_entry(parent):
    entry = log(parent).json()
    assert parent.delete(f"/diary/{entry['id']}").status_code == 204
    assert day(parent)["entries"] == []


# ---- by-serving editing: the entry carries its food's servings -------------------


def _custom_food(client, name="Egg roll", grams=80, **over):
    # A custom food the picker logs by serving: "1 egg roll" = 80 g, 200 cal.
    body = {
        "name": name,
        "servings": [{"name": f"1 {name.lower()}", "grams": grams}],
        "basis_index": 0,
        "calories": 200,
        "protein_g": 8,
    }
    body.update(over)
    res = client.post("/foods", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def log_food(client, food, amount, label):
    # As the picker/edit sheet send a by-serving log: the amount is already in
    # the food's base unit (servings * grams), the phrasing rides in `label`.
    return log(
        client,
        amount=amount,
        unit="g",
        food_id=food["id"],
        name=food["name"],
        source="custom",
        source_id=None,
        label=label,
    )


def test_food_backed_entry_exposes_servings_and_base_unit(parent):
    food = _custom_food(parent, name="Egg roll", grams=80)
    assert log_food(parent, food, amount=80, label="1 egg roll").status_code == 201
    entry = day(parent)["entries"][0]
    assert entry["food_base_unit"] == "g"
    assert [s["name"] for s in entry["food_servings"]] == ["1 egg roll"]
    assert entry["food_servings"][0]["grams"] == 80.0
    assert entry["label"] == "1 egg roll"


def test_idless_food_without_servings_stays_grams_only(parent):
    # A USDA food is cached on first log but carries no named servings, so the
    # edit sheet has nothing to offer by-serving (canServe is false client-side).
    log(parent, amount=100)
    entry = day(parent)["entries"][0]
    assert entry["food_servings"] == []
    assert entry["food_base_unit"] == "g"  # the cache row's base unit


def test_recipe_entry_has_no_food_link(owner):
    owner.post("/recipes", json={"name": "Bowl", "servings": 1, "ingredients": []})
    rid = owner.get("/recipes").json()[0]["id"]
    owner.post("/diary", json={"date_for": TODAY, "slot": "lunch", "recipe_id": rid, "amount": 1})
    entry = day(owner)["entries"][0]
    assert entry["unit"] == "srv"
    assert entry["food_servings"] == []
    assert entry["food_base_unit"] is None


def test_deleted_food_drops_servings_but_entry_survives(parent):
    food = _custom_food(parent, name="Egg roll", grams=80)
    log_food(parent, food, amount=80, label="1 egg roll")
    assert parent.delete(f"/foods/{food['id']}").status_code == 204
    entry = day(parent)["entries"][0]
    assert entry["food_servings"] == []
    assert entry["food_base_unit"] is None
    # The snapshot still reads right and stays editable (scaled linearly).
    assert entry["calories"] == 200.0


def test_editing_by_serving_recomputes_and_keeps_label(parent):
    food = _custom_food(parent, name="Egg roll", grams=80)  # 200 cal / 80 g
    entry = log_food(parent, food, amount=80, label="1 egg roll").json()
    assert entry["calories"] == 200.0
    # The edit sheet turns "2 egg rolls" into 160 g + the new label.
    edited = parent.patch(
        f"/diary/{entry['id']}",
        json={"amount": 160, "unit": "g", "label": "2 egg roll"},
    )
    assert edited.status_code == 200, edited.text
    e = edited.json()
    assert e["amount"] == 160.0 and e["label"] == "2 egg roll"
    assert e["calories"] == 400.0  # 250/100g * 160g


def test_editing_a_recipe_entry_needs_no_unit(owner):
    # The edit sheet must NOT send a unit for a recipe entry (its "srv" is not
    # an AmountUnit); it edits the servings count + slot only. Guards the
    # regression where every save unconditionally sent `unit`.
    owner.post("/recipes", json={"name": "Bowl", "servings": 1, "ingredients": []})
    rid = owner.get("/recipes").json()[0]["id"]
    entry = owner.post(
        "/diary", json={"date_for": TODAY, "slot": "lunch", "recipe_id": rid, "amount": 1}
    ).json()
    res = owner.patch(f"/diary/{entry['id']}", json={"amount": 2, "slot": "dinner"})
    assert res.status_code == 200, res.text
    assert res.json()["slot"] == "dinner" and res.json()["amount"] == 2.0


# ---- privacy: a diary belongs to one person --------------------------------------


def test_family_members_never_see_each_others_entries(app, owner, parent):
    log(parent, amount=100)
    assert day(owner)["entries"] == []

    kid_entry = day(parent)["entries"][0]
    # Even a family admin can't read, edit, or delete a member's entry.
    assert owner.patch(f"/diary/{kid_entry['id']}", json={"amount": 1}).status_code == 404
    assert owner.delete(f"/diary/{kid_entry['id']}").status_code == 404


def test_cross_family_entries_are_invisible(parent, other):
    entry = log(parent).json()
    assert other.patch(f"/diary/{entry['id']}", json={"amount": 1}).status_code == 404
    assert day(other)["entries"] == []


def test_cross_family_recipe_cannot_be_logged(owner, other):
    recipe = owner.post(
        "/recipes",
        json={"name": "Family A Bowl", "servings": 1, "ingredients": []},
    ).json()
    res = other.post(
        "/diary",
        json={"date_for": TODAY, "slot": "dinner", "recipe_id": recipe["id"], "amount": 1},
    )
    assert res.status_code == 404


# ---- targets ---------------------------------------------------------------------


def test_targets_default_until_set(parent):
    d = day(parent)
    t = d["targets"]
    assert t["calories"] == 2000
    assert (t["protein_pct"], t["carbs_pct"], t["fat_pct"]) == (30, 40, 30)
    # Derived gram targets: protein/carbs at 4 kcal/g, fat at 9.
    assert t["protein_g"] == 150.0
    assert t["carbs_g"] == 200.0
    assert round(t["fat_g"], 1) == 66.7


def test_setting_your_own_targets(parent):
    res = parent.put(
        "/diary/targets",
        json={"calories": 1800, "protein_pct": 40, "carbs_pct": 30, "fat_pct": 30},
    )
    assert res.status_code == 200, res.text
    t = day(parent)["targets"]
    assert t["calories"] == 1800
    assert t["protein_g"] == 180.0


def test_targets_must_sum_to_one_hundred(parent):
    res = parent.put(
        "/diary/targets",
        json={"calories": 2000, "protein_pct": 50, "carbs_pct": 40, "fat_pct": 30},
    )
    assert res.status_code == 400


def test_targets_are_per_member(app, owner, parent):
    parent.put(
        "/diary/targets",
        json={"calories": 1600, "protein_pct": 35, "carbs_pct": 35, "fat_pct": 30},
    )
    assert day(owner)["targets"]["calories"] == 2000
    assert day(parent)["targets"]["calories"] == 1600


# ---- kid mode ---------------------------------------------------------------------


def test_minors_have_no_diary(child):
    # Flat 403 on the whole router: reads, writes, and targets alike.
    assert child.get(f"/diary?date={TODAY}").status_code == 403
    assert log(child).status_code == 403
    assert (
        child.put(
            "/diary/targets",
            json={"calories": 1500, "protein_pct": 30, "carbs_pct": 40, "fat_pct": 30},
        ).status_code
        == 403
    )
