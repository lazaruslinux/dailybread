"""The family itself: reading your own, renaming it, and nothing else."""

from sqlalchemy.orm import sessionmaker

from app import foods_api


def test_my_family_returns_own_name(owner):
    res = owner.get("/families/me")
    assert res.status_code == 200
    assert res.json()["name"] == "Home"


def test_every_member_can_read_the_family_name(child):
    assert child.get("/families/me").status_code == 200


def test_homeless_account_has_no_family_to_read(homeless):
    assert homeless.get("/families/me").status_code == 403


def test_admin_renames_the_family(owner, child):
    res = owner.patch("/families/me", json={"name": "The Breakfast Club"})
    assert res.status_code == 200
    assert res.json()["name"] == "The Breakfast Club"
    # Everyone sees the new name.
    assert child.get("/families/me").json()["name"] == "The Breakfast Club"


def test_rename_is_admin_only(parent, child):
    # A non-admin parent runs the board, not the family's identity.
    assert parent.patch("/families/me", json={"name": "Nope"}).status_code == 403
    assert child.patch("/families/me", json={"name": "Nope"}).status_code == 403


def test_rename_validates_the_name(owner):
    assert owner.patch("/families/me", json={"name": ""}).status_code == 422
    assert owner.patch("/families/me", json={"name": "x" * 81}).status_code == 422


def test_deleting_a_family_removes_its_saved_food_pins(app, owner, other, monkeypatch):
    # Family B scans a barcode (its result caches as a shared row, family_id
    # NULL) and pins it to their shelf. That SavedFood's family_id FK has no
    # cascade, so deleting the family must clear the pin explicitly or the
    # delete hits an FK violation; the shared-cache food itself must survive.
    def fake_barcode(code):
        return foods_api.FoodResult("off", code, "Nutella", "Ferrero", 539.0, 6.3, 57.5, 30.9)

    monkeypatch.setattr(foods_api, "lookup_barcode_off", fake_barcode)
    cached = other.get("/foods/barcode/3017620422003")
    assert cached.status_code == 200, cached.text
    food_id = cached.json()["id"]

    pinned = other.post(
        "/foods/saved",
        json={"food_id": food_id, "source": "off", "source_id": "3017620422003", "name": "Nutella"},
    )
    assert pinned.status_code == 201, pinned.text

    family_id = other.get("/families/me").json()["id"]
    res = owner.delete(f"/families/{family_id}")
    assert res.status_code == 204, res.text

    from app.models import Food, SavedFood

    Session = sessionmaker(bind=app.state.test_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        assert db.query(SavedFood).filter(SavedFood.family_id == family_id).count() == 0
        # The shared-cache food outlives the family that had pinned it.
        assert db.get(Food, food_id) is not None
    finally:
        db.close()
