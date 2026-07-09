"""Signup invites: the owner mints a short-lived code carrying only the
invitee's name; the invitee picks their own username, display name, and
password at redemption and founds their own household."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import throttle
from app.routers import auth as auth_router

REDEEM = {"username": "cousin", "password": "carl-pass-123"}


@pytest.fixture(autouse=True)
def _clean_throttle():
    throttle.clear()
    yield
    throttle.clear()


def mint(owner, display_name="Cousin Carl"):
    res = owner.post("/auth/invites", json={"display_name": display_name})
    assert res.status_code == 201, res.text
    return res.json()


# ---- minting -------------------------------------------------------------------


def test_owner_mints_a_code_shown_once(owner):
    invite = mint(owner)
    assert invite["display_name"] == "Cousin Carl"
    assert "-" in invite["code"]


def test_minting_is_server_admin_only(other, parent, child):
    # `other` is family B's ADMIN — but not the install's owner.
    for client in (other, parent, child):
        res = client.post("/auth/invites", json={"display_name": "Nope"})
        assert res.status_code == 403


def test_several_invites_can_be_live_at_once(app, owner):
    first = mint(owner, "Aunt Alice")
    second = mint(owner, "Uncle Ben")
    anon = TestClient(app)
    assert anon.post("/auth/invites/check", json={"code": first["code"]}).json() == {
        "display_name": "Aunt Alice"
    }
    assert anon.post("/auth/invites/check", json={"code": second["code"]}).json() == {
        "display_name": "Uncle Ben"
    }


# ---- checking ------------------------------------------------------------------


def test_check_greets_without_consuming(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    for _ in range(2):
        res = anon.post("/auth/invites/check", json={"code": invite["code"]})
        assert res.status_code == 200
        assert res.json() == {"display_name": "Cousin Carl"}
    # Still redeemable after being checked.
    res = anon.post("/auth/invites/redeem", json={"code": invite["code"], **REDEEM})
    assert res.status_code == 201


def test_wrong_and_expired_codes_are_uniform(app, owner, monkeypatch):
    anon = TestClient(app)
    res = anon.post("/auth/invites/check", json={"code": "WRONGCOD"})
    assert res.status_code == 404
    wrong_detail = res.json()["detail"]

    monkeypatch.setattr(auth_router, "SIGNUP_INVITE_TTL", dt.timedelta(minutes=-1))
    invite = mint(owner)
    res = anon.post("/auth/invites/check", json={"code": invite["code"]})
    assert res.status_code == 404
    assert res.json()["detail"] == wrong_detail


def test_anonymous_attempts_share_a_throttle(app, owner):
    anon = TestClient(app)
    for _ in range(auth_router.SIGNUP_MAX_FAILURES):
        assert anon.post("/auth/invites/check", json={"code": "WRONGCOD"}).status_code == 404
    assert anon.post("/auth/invites/check", json={"code": "WRONGCOD"}).status_code == 429
    assert (
        anon.post(
            "/auth/invites/redeem", json={"code": "WRONGCOD", **REDEEM}
        ).status_code
        == 429
    )


# ---- redeeming -----------------------------------------------------------------


def test_redeem_signs_in_a_family_less_parent(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    res = anon.post("/auth/invites/redeem", json={"code": invite["code"], **REDEEM})
    assert res.status_code == 201
    me = anon.get("/auth/me").json()  # the redeem response set the cookie
    assert me["username"] == "cousin"
    assert me["display_name"] == "Cousin Carl"  # the name the admin typed
    assert me["role"] == "parent"
    assert me["family_id"] is None
    assert me["is_admin"] is False
    assert me["is_owner"] is False
    assert me["must_change_password"] is False


def test_invitee_may_adjust_their_display_name(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    res = anon.post(
        "/auth/invites/redeem",
        json={"code": invite["code"], **REDEEM, "display_name": "Carl G."},
    )
    assert res.status_code == 201
    assert anon.get("/auth/me").json()["display_name"] == "Carl G."


def test_redeem_is_single_use(app, owner):
    invite = mint(owner)
    a, b = TestClient(app), TestClient(app)
    assert (
        a.post("/auth/invites/redeem", json={"code": invite["code"], **REDEEM}).status_code
        == 201
    )
    res = b.post(
        "/auth/invites/redeem",
        json={"code": invite["code"], "username": "someone", "password": "other-pass-123"},
    )
    assert res.status_code == 404


def test_redeem_validates_the_chosen_identity(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    # Too-short password and too-short username are schema errors, so the
    # invite survives both.
    res = anon.post(
        "/auth/invites/redeem",
        json={"code": invite["code"], "username": "cousin", "password": "test1"},
    )
    assert res.status_code == 422
    res = anon.post(
        "/auth/invites/redeem",
        json={"code": invite["code"], "username": "ab", "password": "carl-pass-123"},
    )
    assert res.status_code == 422
    assert (
        anon.post("/auth/invites/redeem", json={"code": invite["code"], **REDEEM}).status_code
        == 201
    )


def test_taken_username_is_retryable(app, owner):
    """A collision on the invitee's own choice is a form error, not a dead
    invite: they just pick another name with the same code."""
    invite = mint(owner)
    anon = TestClient(app)
    res = anon.post(
        "/auth/invites/redeem",
        json={"code": invite["code"], "username": "owner", "password": "carl-pass-123"},
    )
    assert res.status_code == 409
    res = anon.post("/auth/invites/redeem", json={"code": invite["code"], **REDEEM})
    assert res.status_code == 201


def test_redeemed_account_founds_its_own_family(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    anon.post("/auth/invites/redeem", json={"code": invite["code"], **REDEEM})
    res = anon.post("/families", json={"name": "The Carls"})
    assert res.status_code == 201
    me = anon.get("/auth/me").json()
    assert me["family_id"] is not None
    assert me["is_admin"] is True
    assert me["is_owner"] is False