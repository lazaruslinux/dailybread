"""Login rate limiting: repeated failures lock a username out for a while."""

import time

from fastapi.testclient import TestClient

from app import throttle
from tests.conftest import OWNER


def _attempt(app, username, password):
    return TestClient(app).post(
        "/auth/login", json={"username": username, "password": password}
    )


def test_repeated_failures_lock_the_username(app, owner):
    for _ in range(throttle.MAX_FAILURES):
        assert _attempt(app, OWNER["username"], "wrong-pass-123").status_code == 401
    # Locked now — even the CORRECT password is refused until the window cools.
    assert _attempt(app, OWNER["username"], OWNER["password"]).status_code == 429


def test_lockout_is_per_username(app, owner):
    for _ in range(throttle.MAX_FAILURES):
        _attempt(app, "somebody-else", "wrong-pass-123")
    # An attack on one username doesn't lock anyone else's door.
    assert _attempt(app, OWNER["username"], OWNER["password"]).status_code == 200


def test_unknown_usernames_throttle_identically(app):
    # The 429 must not reveal whether the username exists.
    for _ in range(throttle.MAX_FAILURES):
        assert _attempt(app, "ghost-user", "wrong-pass-123").status_code == 401
    assert _attempt(app, "ghost-user", "wrong-pass-123").status_code == 429


def test_successful_login_clears_the_count(app, owner):
    for _ in range(throttle.MAX_FAILURES - 1):
        _attempt(app, OWNER["username"], "wrong-pass-123")
    assert _attempt(app, OWNER["username"], OWNER["password"]).status_code == 200
    # The slate is clean again: one more failure is just a failure, not a lock.
    assert _attempt(app, OWNER["username"], "wrong-pass-123").status_code == 401
    assert _attempt(app, OWNER["username"], OWNER["password"]).status_code == 200


def test_lockout_expires_with_the_window(monkeypatch):
    # Driven at the module level: through HTTP each Argon2 check takes longer
    # than any test-sized window, so failures would age out mid-loop.
    monkeypatch.setattr(throttle, "WINDOW_SECONDS", 0.05)
    for _ in range(throttle.MAX_FAILURES):
        throttle.record_failure("someone")
    assert throttle.too_many_failures("someone") is True
    time.sleep(0.1)
    assert throttle.too_many_failures("someone") is False
