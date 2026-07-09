"""The family itself: reading your own, renaming it, and nothing else."""


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
