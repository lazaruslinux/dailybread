"""Signup invites: the owner mints a short-lived code; an anonymous visitor
redeems it into a family-less parent account and founds their own household."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import throttle
from app.routers import auth as auth_router

INVITEE = {"username": "cousin", "display_name": "Cousin Carl"}


@pytest.fixture(autouse=True)
def _clean_throttle():
    throttle.clear()
    yield
    throttle.clear()


def mint(owner, **overrides):
    res = owner.post("/auth/invites", json={**INVITEE, **overrides})
    assert res.status_code == 201, res.text
    return res.json()


# ---- minting -------------------------------------------------------------------


def test_owner_mints_a_code_shown_once(owner):
    invite = mint(owner)
    assert invite["username"] == "cousin"
    assert invite["display_name"] == "Cousin Carl"
    assert "-" in invite["code"]


def test_minting_is_server_admin_only(other, parent, child):
    # `other` is family B's ADMIN — but not the install's owner.
    for client in (other, parent, child):
        res = client.post("/auth/invites", json=INVITEE)
        assert res.status_code == 403


def test_taken_username_refused_at_mint(owner):
    res = owner.post("/auth/invites", json={**INVITEE, "username": "owner"})
    assert res.status_code == 409


def test_reminting_replaces_the_pending_invite(app, owner):
    first = mint(owner)
    second = mint(owner)
    anon = TestClient(app)
    res = anon.post("/auth/invites/check", json={"code": first["code"]})
    assert res.status_code == 404
    res = anon.post("/auth/invites/check", json={"code": second["code"]})
    assert res.status_code == 200


# ---- checking ------------------------------------------------------------------


def test_check_greets_without_consuming(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    for _ in range(2):
        res = anon.post("/auth/invites/check", json={"code": invite["code"]})
        assert res.status_code == 200
        assert res.json() == {"username": "cousin", "display_name": "Cousin Carl"}
    # Still redeemable after being checked.
    res = anon.post(
        "/auth/invites/redeem", json={"code": invite["code"], "password": "carl-pass-123"}
    )
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
            "/auth/invites/redeem", json={"code": "WRONGCOD", "password": "irrelevant-123"}
        ).status_code
        == 429
    )


# ---- redeeming -----------------------------------------------------------------


def test_redeem_signs_in_a_family_less_parent(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    res = anon.post(
        "/auth/invites/redeem", json={"code": invite["code"], "password": "carl-pass-123"}
    )
    assert res.status_code == 201
    me = anon.get("/auth/me").json()  # the redeem response set the cookie
    assert me["username"] == "cousin"
    assert me["role"] == "parent"
    assert me["family_id"] is None
    assert me["is_admin"] is False
    assert me["is_owner"] is False
    assert me["must_change_password"] is False


def test_redeem_is_single_use(app, owner):
    invite = mint(owner)
    a, b = TestClient(app), TestClient(app)
    assert (
        a.post(
            "/auth/invites/redeem", json={"code": invite["code"], "password": "carl-pass-123"}
        ).status_code
        == 201
    )
    assert (
        b.post(
            "/auth/invites/redeem", json={"code": invite["code"], "password": "other-pass-123"}
        ).status_code
        == 404
    )


def test_redeem_refuses_short_passwords(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    res = anon.post("/auth/invites/redeem", json={"code": invite["code"], "password": "short"})
    assert res.status_code == 422


def test_username_taken_between_mint_and_redeem(app, owner):
    invite = mint(owner)
    # An admin legitimately creates the same username directly in the meantime.
    res = owner.post(
        "/auth/users",
        json={
            "username": "cousin",
            "display_name": "Other Cousin",
            "password": "other-pass-123",
            "role": "parent",
        },
    )
    assert res.status_code == 201
    anon = TestClient(app)
    res = anon.post(
        "/auth/invites/redeem", json={"code": invite["code"], "password": "carl-pass-123"}
    )
    assert res.status_code == 409
    # The dead invite no longer squats anything: the code is gone.
    assert anon.post("/auth/invites/check", json={"code": invite["code"]}).status_code == 404


def test_redeemed_account_founds_its_own_family(app, owner):
    invite = mint(owner)
    anon = TestClient(app)
    anon.post("/auth/invites/redeem", json={"code": invite["code"], "password": "carl-pass-123"})
    res = anon.post("/families", json={"name": "The Carls"})
    assert res.status_code == 201
    me = anon.get("/auth/me").json()
    assert me["family_id"] is not None
    assert me["role"] == "parent"
    assert me["is_admin"] is True
    assert me["is_owner"] is False