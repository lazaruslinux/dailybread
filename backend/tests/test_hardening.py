"""The abuse-surface hardening round: request-body ceilings, the ingest
token-before-body ordering, the auto-Secure session cookie, per-client login
throttling, and the push-endpoint sanity check."""

from fastapi.testclient import TestClient

from app.main import INGEST_MAX_BODY_BYTES, MAX_BODY_BYTES
from tests.conftest import OWNER

JSON = {"content-type": "application/json"}


# ---- body-size ceilings ------------------------------------------------------------


def test_oversized_body_is_413_before_parsing(anon):
    res = anon.post(
        "/auth/login", content=b"x" * (MAX_BODY_BYTES + 1), headers=JSON
    )
    assert res.status_code == 413


def test_chunked_body_without_length_is_cut_off(anon):
    # A generator body goes out chunked, with no Content-Length to check up
    # front, so this exercises the streamed count instead.
    chunk = b"x" * (1024 * 1024)

    def stream():
        for _ in range(MAX_BODY_BYTES // len(chunk) + 2):
            yield chunk

    res = anon.post("/auth/login", content=stream(), headers=JSON)
    assert res.status_code == 413


def test_normal_sized_requests_pass(anon):
    res = anon.post(
        "/auth/login", json={"username": "nobody", "password": "wrong-pass-123"}
    )
    assert res.status_code == 401  # normal handling, not 413


def test_ingest_has_a_tighter_cap(anon):
    res = anon.post(
        "/ingest/health",
        content=b"x" * (INGEST_MAX_BODY_BYTES + 1),
        headers={**JSON, "Authorization": "Bearer whatever"},
    )
    assert res.status_code == 413


# ---- ingest: token checked before the body is read ---------------------------------


def _mint(client) -> str:
    return client.post("/me/fitness/token").json()["token"]


def test_bad_token_is_401_without_parsing_the_body(anon):
    # Deliberately invalid JSON: if the body were parsed first this would 422.
    res = anon.post(
        "/ingest/health",
        content=b"not json at all",
        headers={**JSON, "Authorization": "Bearer not-a-real-token"},
    )
    assert res.status_code == 401


def test_good_token_with_broken_json_is_422(owner):
    token = _mint(owner)
    res = owner.post(
        "/ingest/health",
        content=b"not json at all",
        headers={**JSON, "Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


def test_good_token_with_non_object_json_is_422(owner):
    token = _mint(owner)
    res = owner.post(
        "/ingest/health",
        content=b'["a", "list"]',
        headers={**JSON, "Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


def test_valid_ingest_still_works(owner):
    token = _mint(owner)
    payload = {"data": {"metrics": [], "workouts": []}}
    res = owner.post(
        "/ingest/health", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200


# ---- session cookie: Secure follows how the request arrived ------------------------


def test_https_login_gets_a_secure_cookie(app, owner):
    res = TestClient(app).post(
        "/auth/login",
        json={"username": OWNER["username"], "password": OWNER["password"]},
        headers={"x-forwarded-proto": "https"},
    )
    assert res.status_code == 200
    assert "Secure" in res.headers["set-cookie"]


def test_plain_http_login_gets_no_secure_flag(app, owner):
    res = TestClient(app).post(
        "/auth/login",
        json={"username": OWNER["username"], "password": OWNER["password"]},
    )
    assert res.status_code == 200
    assert "Secure" not in res.headers["set-cookie"]


# ---- login throttle: one hostile client can't lock the owner out -------------------


def test_other_clients_survive_one_clients_lockout(app, owner):
    hostile = {"x-real-ip": "203.0.113.9"}
    for _ in range(10):
        res = TestClient(app).post(
            "/auth/login",
            json={"username": OWNER["username"], "password": "wrong-pass-123"},
            headers=hostile,
        )
        assert res.status_code == 401
    # The hostile client is now locked out of this username...
    assert (
        TestClient(app)
        .post(
            "/auth/login",
            json={"username": OWNER["username"], "password": OWNER["password"]},
            headers=hostile,
        )
        .status_code
        == 429
    )
    # ...but the owner, from their own address, still gets in.
    res = TestClient(app).post(
        "/auth/login",
        json={"username": OWNER["username"], "password": OWNER["password"]},
        headers={"x-real-ip": "192.0.2.20"},
    )
    assert res.status_code == 200


# ---- push subscriptions: only plausible push-service endpoints ---------------------


def _sub(endpoint: str) -> dict:
    return {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}


def test_push_endpoint_must_be_public_https(owner, configured):
    for bad in (
        "http://push.example/device",
        "https://192.168.50.1/device",
        "https://[::1]/device",
        "https://localhost/device",
        "https://nas.local/device",
        "not a url",
    ):
        res = owner.put("/push/subscription", json=_sub(bad))
        assert res.status_code == 400, bad
    assert owner.put("/push/subscription", json=_sub("https://push.example/d")).status_code == 204
