"""The nutrition diary: personal food logging with per-user targets.

Entries snapshot their nutrition at log time (server-computed, never
client-supplied), so later edits to a recipe or food never rewrite history.
Everything here is self-only: family members never see each other's diaries.
"""

import datetime as dt

from tests.conftest import login, user_id, CHILD

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
