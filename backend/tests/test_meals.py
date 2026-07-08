"""The family menu: who plans meals, upsert semantics, and isolation."""

import datetime as dt

from tests.test_recipes import make_recipe

TODAY = dt.date.today().isoformat()


def test_parent_plans_a_recipe_dinner(owner):
    recipe = make_recipe(owner, name="Taco Bowls")
    res = owner.put("/meals", json={"date_for": TODAY, "recipe_id": recipe["id"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["slot"] == "dinner"  # the default slot
    assert body["recipe_name"] == "Taco Bowls" and body["custom_title"] is None

    listed = owner.get(f"/meals?start={TODAY}&end={TODAY}").json()
    assert len(listed) == 1 and listed[0]["recipe_name"] == "Taco Bowls"


def test_custom_title_nights_work_without_a_recipe(owner):
    res = owner.put("/meals", json={"date_for": TODAY, "custom_title": "Pizza out"})
    assert res.status_code == 200
    assert res.json()["custom_title"] == "Pizza out"
    assert res.json()["recipe_id"] is None


def test_replanning_replaces_the_same_night(owner):
    recipe = make_recipe(owner, name="Taco Bowls")
    owner.put("/meals", json={"date_for": TODAY, "recipe_id": recipe["id"]})
    owner.put("/meals", json={"date_for": TODAY, "custom_title": "Leftovers"})

    listed = owner.get(f"/meals?start={TODAY}&end={TODAY}").json()
    assert len(listed) == 1  # upsert, not a second row
    assert listed[0]["custom_title"] == "Leftovers" and listed[0]["recipe_id"] is None


def test_kids_see_the_menu_but_cannot_change_it(owner, child):
    owner.put("/meals", json={"date_for": TODAY, "custom_title": "Spaghetti"})
    assert child.get(f"/meals?start={TODAY}&end={TODAY}").status_code == 200
    assert child.put("/meals", json={"date_for": TODAY, "custom_title": "Candy"}).status_code == 403
    assert child.delete(f"/meals?date={TODAY}").status_code == 403


def test_clearing_unplans_the_night(owner):
    owner.put("/meals", json={"date_for": TODAY, "custom_title": "Spaghetti"})
    assert owner.delete(f"/meals?date={TODAY}").status_code == 204
    assert owner.get(f"/meals?start={TODAY}&end={TODAY}").json() == []
    # Clearing an already-clear day is quietly fine.
    assert owner.delete(f"/meals?date={TODAY}").status_code == 204


def test_meal_needs_a_recipe_or_a_title(owner):
    assert owner.put("/meals", json={"date_for": TODAY}).status_code == 400
    assert owner.put("/meals", json={"date_for": TODAY, "custom_title": "  "}).status_code == 400


def test_cross_family_recipes_cannot_be_planned(owner, other):
    recipe = make_recipe(owner, name="Taco Bowls")
    res = other.put("/meals", json={"date_for": TODAY, "recipe_id": recipe["id"]})
    assert res.status_code == 404


def test_menus_are_family_private(owner, other):
    owner.put("/meals", json={"date_for": TODAY, "custom_title": "Spaghetti"})
    assert other.get(f"/meals?start={TODAY}&end={TODAY}").json() == []


def test_deleting_a_recipe_unplans_gracefully(owner):
    recipe = make_recipe(owner, name="Taco Bowls")
    owner.put("/meals", json={"date_for": TODAY, "recipe_id": recipe["id"]})
    owner.delete(f"/recipes/{recipe['id']}")

    listed = owner.get(f"/meals?start={TODAY}&end={TODAY}").json()
    # The row survives with the recipe gone: the night reads unplanned-ish
    # (no name), rather than the whole plan vanishing.
    assert len(listed) == 1
    assert listed[0]["recipe_id"] is None and listed[0]["recipe_name"] is None


def test_range_guards(owner):
    far = (dt.date.today() + dt.timedelta(days=90)).isoformat()
    assert owner.get(f"/meals?start={TODAY}&end={far}").status_code == 400
    assert owner.get(f"/meals?start={far}&end={TODAY}").status_code == 400
