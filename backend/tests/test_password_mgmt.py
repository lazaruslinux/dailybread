"""Password management: changing your own, and an admin resetting a member's.

A self-service change proves the current password and keeps THIS session alive
while ending the account's others. An admin reset hands back a generated
password and flags the account: until its owner picks their own password,
their session is locked down to exactly that (and seeing who they are).
"""

import re

from fastapi.testclient import TestClient

from tests.conftest import CHILD, OWNER, PARENT, login, user_id

# What security.generate_password() promises: two lowercase words and two
# digits, dash-separated — readable over a shoulder, typeable on a phone.
GENERATED_SHAPE = re.compile(r"^[a-z]{3,8}-[a-z]{3,8}-\d{2}$")


def change(client: TestClient, current: str, new: str):
    return client.post(
        "/auth/change-password",
        json={"current_password": current, "new_password": new},
    )


# ---- changing your own password ------------------------------------------------


def test_change_own_password_and_the_old_one_stops_working(app, parent):
    res = change(parent, PARENT["password"], "a-new-password-1")
    assert res.status_code == 200, res.text

    bad = TestClient(app).post(
        "/auth/login", json={"username": PARENT["username"], "password": PARENT["password"]}
    )
    assert bad.status_code == 401
    good = TestClient(app).post(
        "/auth/login", json={"username": PARENT["username"], "password": "a-new-password-1"}
    )
    assert good.status_code == 200


def test_change_with_wrong_current_password_is_refused(app, parent):
    res = change(parent, "not-my-password", "a-new-password-1")
    assert res.status_code == 400

    # Nothing changed: the original password still signs in.
    ok = TestClient(app).post(
        "/auth/login", json={"username": PARENT["username"], "password": PARENT["password"]}
    )
    assert ok.status_code == 200


def test_change_keeps_this_session_but_ends_the_others(app, parent):
    other_device = login(app, PARENT)

    res = change(parent, PARENT["password"], "a-new-password-1")
    assert res.status_code == 200

    # The session that made the change sails on (its cookie was re-issued)...
    assert parent.get("/auth/me").status_code == 200
    # ...while the account's other session is over.
    assert other_device.get("/auth/me").status_code == 401


def test_change_rejects_a_short_new_password(parent):
    res = change(parent, PARENT["password"], "short")
    assert res.status_code == 422


def test_children_can_change_their_own_password_too(app, child):
    res = change(child, CHILD["password"], "kid-picked-this-1")
    assert res.status_code == 200
    ok = TestClient(app).post(
        "/auth/login", json={"username": CHILD["username"], "password": "kid-picked-this-1"}
    )
    assert ok.status_code == 200


# ---- admin reset to a generated password -----------------------------------------


def reset(admin_client: TestClient, target_id: int):
    return admin_client.post(f"/auth/users/{target_id}/reset-password")


def test_reset_generates_a_working_password_and_ends_their_sessions(app, owner, child):
    kid_id = user_id(child)

    res = reset(owner, kid_id)
    assert res.status_code == 200, res.text
    generated = res.json()["password"]
    assert GENERATED_SHAPE.match(generated), generated
    assert res.json()["user"]["must_change_password"] is True

    # The kid's existing session died with the reset...
    assert child.get("/auth/me").status_code == 401
    # ...their old password is gone...
    old = TestClient(app).post(
        "/auth/login", json={"username": CHILD["username"], "password": CHILD["password"]}
    )
    assert old.status_code == 401
    # ...and the generated one signs in.
    fresh = TestClient(app).post(
        "/auth/login", json={"username": CHILD["username"], "password": generated}
    )
    assert fresh.status_code == 200
    assert fresh.json()["must_change_password"] is True


def test_a_flagged_account_can_only_change_its_password(app, owner, child):
    kid_id = user_id(child)
    generated = reset(owner, kid_id).json()["password"]

    flagged = TestClient(app)
    flagged.post("/auth/login", json={"username": CHILD["username"], "password": generated})

    # Everything but the password screen is off limits...
    assert flagged.get("/items/feed").status_code == 403
    assert flagged.get("/grocery").status_code == 403
    # ...but they can see who they are and set their own password.
    assert flagged.get("/auth/me").status_code == 200
    done = change(flagged, generated, "my-own-choice-11")
    assert done.status_code == 200
    assert done.json()["must_change_password"] is False

    # The lock lifts the moment the password is theirs.
    assert flagged.get("/grocery").status_code == 200


def test_admins_cannot_reset_their_own_password_this_way(owner):
    res = reset(owner, user_id(owner))
    assert res.status_code == 400


def test_only_admins_can_reset(owner, parent, child):
    kid_id = user_id(child)
    assert reset(parent, kid_id).status_code == 403
    assert reset(child, user_id(parent)).status_code == 403


def test_cross_family_reset_is_a_404(owner, other, child):
    # Family B's admin can't even learn that the kid's id exists.
    assert reset(other, user_id(child)).status_code == 404


def test_two_resets_generate_different_passwords(owner, child, parent):
    a = reset(owner, user_id(child)).json()["password"]
    b = reset(owner, user_id(parent)).json()["password"]
    assert a != b


def test_manual_password_edit_does_not_force_a_change(app, owner, child):
    """The edit sheet's typed-in reset stays deliberate: no forced-change flag
    (a parent setting a young kid's password shouldn't lock the kid out)."""
    kid_id = user_id(child)
    res = owner.patch(f"/auth/users/{kid_id}", json={"password": "set-by-parent-1"})
    assert res.status_code == 200
    assert res.json()["must_change_password"] is False

    fresh = TestClient(app)
    res = fresh.post(
        "/auth/login", json={"username": CHILD["username"], "password": "set-by-parent-1"}
    )
    assert res.status_code == 200
    assert fresh.get("/grocery").status_code == 200
