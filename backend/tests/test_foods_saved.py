"""Saved Foods: the family's pinned quick-reuse shelf."""

PEANUT_BUTTER = {
    "source": "off",
    "source_id": "0051500255162",
    "name": "Peanut Butter",
    "brand": "Jif",
    "calories": 590.0,
    "protein_g": 24.0,
    "carbs_g": 24.0,
    "fat_g": 50.0,
}


def test_save_list_and_unsave(owner, parent):
    res = owner.post("/foods/saved", json=PEANUT_BUTTER)
    assert res.status_code == 201, res.text
    food_id = res.json()["id"]
    assert food_id is not None

    # The whole family sees the shelf, newest first; saving twice is one pin.
    owner.post("/foods/saved", json=PEANUT_BUTTER)
    shelf = parent.get("/foods/saved").json()
    assert [f["name"] for f in shelf] == ["Peanut Butter"]

    assert owner.request("DELETE", f"/foods/saved/{food_id}").status_code == 204
    assert owner.get("/foods/saved").json() == []
    # Unpinning never deletes the food row itself (snapshots may reference it).
    assert owner.request("DELETE", f"/foods/saved/{food_id}").status_code == 204


def test_saving_reuses_the_shared_cache_row(owner):
    first = owner.post("/foods/saved", json=PEANUT_BUTTER).json()
    owner.request("DELETE", f"/foods/saved/{first['id']}")
    again = owner.post("/foods/saved", json=PEANUT_BUTTER).json()
    assert again["id"] == first["id"]  # find-or-create found


def test_shelves_stay_inside_the_family(owner, other):
    owner.post("/foods/saved", json=PEANUT_BUTTER)
    assert other.get("/foods/saved").json() == []
