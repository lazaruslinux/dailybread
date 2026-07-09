"""Auth, bootstrap lockout, and the admin-management guard rails."""

import datetime as dt

import jwt
from fastapi.testclient import TestClient

from app.config import settings
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


def _token_issued_ago(user_id: int, days: float) -> str:
    """A valid token backdated as if issued `days` ago (still unexpired)."""
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now - dt.timedelta(days=days),
            "exp": now + dt.timedelta(days=settings.session_days - days),
        },
        settings.secret_key,
        algorithm="HS256",
    )


def test_day_old_session_slides_forward(owner):
    owner.cookies.set(settings.cookie_name, _token_issued_ago(user_id(owner), days=3))
    res = owner.get("/auth/me")
    assert res.status_code == 200
    # The stale-but-valid token gets replaced with a fresh one on any
    # authenticated request, keeping the expiry moving as long as you use
    # the app. Same attributes as at login: HttpOnly so JS can't read it.
    reissued = res.headers.get("set-cookie", "")
    assert settings.cookie_name in reissued
    assert "HttpOnly" in reissued


def test_fresh_session_is_left_alone(owner):
    # Right after bootstrap the token is seconds old: no pointless re-issue
    # (a Set-Cookie on every request would churn caches and logs).
    res = owner.get("/auth/me")
    assert res.status_code == 200
    assert "set-cookie" not in res.headers


def test_password_reset_ends_existing_sessions(owner, child):
    # The kid is signed in. Resetting their password kills that session on the
    # spot — the whole point of a reset when a phone is lost — not just the
    # old password. (Tokens carry the version they were minted under; the
    # reset bumps the account's version.)
    assert child.get("/auth/me").status_code == 200
    kid_id = user_id(child)
    res = owner.patch(f"/auth/users/{kid_id}", json={"password": "brand-new-pass-1"})
    assert res.status_code == 200
    assert child.get("/auth/me").status_code == 401


def test_admin_changing_own_password_stays_signed_in(owner):
    # Changing your own password logs out your other sessions but not the one
    # you did it from: the response carries a freshly minted cookie.
    my_id = user_id(owner)
    res = owner.patch(f"/auth/users/{my_id}", json={"password": "my-new-pass-123"})
    assert res.status_code == 200
    assert settings.cookie_name in res.headers.get("set-cookie", "")
    assert owner.get("/auth/me").status_code == 200


# ---- kid mode: birthdate and is_minor -----------------------------------------


def test_child_without_birthdate_is_a_minor(child):
    me = child.get("/auth/me").json()
    assert me["birthdate"] is None
    assert me["is_minor"] is True


def test_parent_is_never_a_minor(owner):
    # Parents have no birthdate either; the flag keys off the child role.
    assert owner.get("/auth/me").json()["is_minor"] is False


def test_child_with_adult_birthdate_is_still_a_minor(grown_child):
    # Kid mode follows the role: age never unlocks it.
    me = grown_child.get("/auth/me").json()
    assert me["birthdate"] is not None
    assert me["is_minor"] is True


def test_create_accepts_birthdate(owner):
    res = owner.post(
        "/auth/users",
        json={
            "username": "birthkid",
            "display_name": "Birth Kid",
            "password": "kid-pass-1234",
            "role": "child",
            "birthdate": "2016-03-05",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["birthdate"] == "2016-03-05"
    assert body["is_minor"] is True


def test_update_sets_and_clears_birthdate(owner, child):
    kid_id = user_id(child)
    grown = (dt.date.today() - dt.timedelta(days=19 * 366)).isoformat()

    res = owner.patch(f"/auth/users/{kid_id}", json={"birthdate": grown})
    assert res.status_code == 200
    assert res.json()["is_minor"] is True  # informational only: still a child

    # Omitting the field leaves it alone...
    res = owner.patch(f"/auth/users/{kid_id}", json={"display_name": "Still Grown"})
    assert res.json()["birthdate"] == grown

    # ...while an explicit null clears it.
    res = owner.patch(f"/auth/users/{kid_id}", json={"birthdate": None})
    assert res.status_code == 200
    assert res.json()["birthdate"] is None
    assert res.json()["is_minor"] is True



# ---- stored theme preference ---------------------------------------------------


def test_theme_follows_the_account(owner):
    assert owner.get("/auth/me").json()["theme"] is None
    res = owner.patch("/me/profile", json={"theme": "dark"})
    assert res.status_code == 200
    assert owner.get("/auth/me").json()["theme"] == "dark"
    # Only the two real schemes are accepted.
    assert owner.patch("/me/profile", json={"theme": "hotdog"}).status_code == 422


# ---- the server overview --------------------------------------------------------


def test_overview_is_owner_only(owner, parent, child, other):
    for client in (parent, child, other):
        assert client.get("/auth/overview").status_code == 403
    assert owner.get("/auth/overview").status_code == 200


def test_overview_trees_the_whole_install(owner, other, child):
    # Link the two families into a village so both branches of the tree show.
    created = owner.post("/villages", json={"name": "Circle"}).json()
    other.post("/villages/join", json={"code": created["invite_code"]})
    # And one account still mid-wizard.
    owner.post(
        "/auth/users",
        json={
            "username": "drifter",
            "display_name": "Drifter",
            "password": "drift-pass-123",
            "role": "parent",
            "new_household": True,
        },
    )

    tree = owner.get("/auth/overview").json()
    assert [v["name"] for v in tree["villages"]] == ["Circle"]
    village_families = {f["name"] for f in tree["villages"][0]["families"]}
    assert village_families == {"Home", "The Bs"}
    home = next(f for f in tree["villages"][0]["families"] if f["name"] == "Home")
    assert {u["username"] for u in home["users"]} >= {"owner", "kid"}
    assert tree["solo_families"] == []
    assert [u["username"] for u in tree["homeless_users"]] == ["drifter"]
