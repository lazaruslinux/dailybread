"""Auth, bootstrap lockout, and the admin-management guard rails."""

from fastapi.testclient import TestClient

from tests.conftest import CHILD, OWNER, login, user_id


def test_bootstrap_creates_signed_in_parent_admin(owner):
    me = owner.get("/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["role"] == "parent"
    assert body["is_admin"] is True


def test_bootstrap_locked_once_initialized(app, owner):
    res = TestClient(app).post(
        "/auth/bootstrap",
        json={"username": "intruder", "display_name": "X", "password": "sneaky-pass-1"},
    )
    assert res.status_code == 403


def test_setup_state_flips_after_bootstrap(app, anon):
    assert anon.get("/auth/setup").json() == {"initialized": False}
    anon.post("/auth/bootstrap", json=OWNER)
    assert anon.get("/auth/setup").json() == {"initialized": True}


def test_bad_password_and_unknown_user_are_identical(app, owner):
    wrong_pw = TestClient(app).post(
        "/auth/login", json={"username": OWNER["username"], "password": "wrong-pass-1"}
    )
    no_user = TestClient(app).post(
        "/auth/login", json={"username": "ghost", "password": "wrong-pass-1"}
    )
    assert wrong_pw.status_code == no_user.status_code == 401
    # Same body too: no username enumeration.
    assert wrong_pw.json() == no_user.json()


def test_me_requires_a_session(anon):
    assert anon.get("/auth/me").status_code == 401


def test_child_can_never_be_admin(owner):
    res = owner.post(
        "/auth/users",
        json={
            "username": "sneakykid",
            "display_name": "Sneaky",
            "password": "kid-pass-1234",
            "role": "child",
            "is_admin": True,
        },
    )
    assert res.status_code == 400


def test_cannot_promote_existing_child_to_admin(owner, child):
    res = owner.patch(f"/auth/users/{user_id(child)}", json={"is_admin": True})
    assert res.status_code == 400


def test_admin_cannot_demote_or_delete_self(owner):
    my_id = user_id(owner)
    assert owner.patch(f"/auth/users/{my_id}", json={"is_admin": False}).status_code == 400
    assert owner.delete(f"/auth/users/{my_id}").status_code == 400


def test_non_admin_parent_cannot_manage_users(parent, child):
    kid_id = user_id(child)
    assert parent.get("/auth/users").status_code == 403
    assert parent.patch(f"/auth/users/{kid_id}", json={"display_name": "X"}).status_code == 403
    assert parent.delete(f"/auth/users/{kid_id}").status_code == 403


def test_child_cannot_manage_users(child):
    assert child.get("/auth/users").status_code == 403


def test_password_reset_invalidates_old_password(app, owner, child):
    kid_id = user_id(child)
    res = owner.patch(f"/auth/users/{kid_id}", json={"password": "brand-new-pass-1"})
    assert res.status_code == 200

    old = TestClient(app).post(
        "/auth/login", json={"username": CHILD["username"], "password": CHILD["password"]}
    )
    assert old.status_code == 401
    fresh = login(app, {"username": CHILD["username"], "password": "brand-new-pass-1"})
    assert fresh.get("/auth/me").json()["username"] == CHILD["username"]
