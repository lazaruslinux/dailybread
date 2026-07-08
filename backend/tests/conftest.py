"""Shared test fixtures.

Each test gets the real FastAPI app wired to a fresh in-memory SQLite
database (via dependency_overrides on get_db), so tests are fully isolated
from each other and from Postgres. Role fixtures return separate TestClients,
each with its own cookie jar, exercising the real auth endpoints end to end.
"""

import datetime as dt
import os

# Must happen before any app import: Settings reads the environment once.
# 32+ bytes so PyJWT doesn't warn about a weak HS256 key during tests.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-0123456789abcdef")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import throttle
from app.config import settings
from app.db import Base, get_db
from app.main import app as real_app

# Throwaway credentials that exist only inside a single test run.
OWNER = {"username": "owner", "display_name": "Owner Parent", "password": "owner-pass-123"}
PARENT = {"username": "parent2", "display_name": "Second Parent", "password": "parent-pass-123"}
CHILD = {"username": "kid", "display_name": "The Kid", "password": "child-pass-123"}
# A child-role account past 18: child on the board, but not a minor.
ADULT_CHILD = {"username": "grownkid", "display_name": "Grown Kid", "password": "grown-pass-123"}
# A second household, for cross-family isolation checks.
JOSH = {"username": "josh", "display_name": "Josh", "password": "josh-pass-1234"}


@pytest.fixture(autouse=True)
def _push_unconfigured(monkeypatch):
    """Start every test with push OFF, even when the developer's backend/.env
    holds real dev VAPID keys (Settings reads it at import). Tests that want
    push on say so via the `configured` fixture, which runs after this."""
    monkeypatch.setattr(settings, "vapid_public_key", "")
    monkeypatch.setattr(settings, "vapid_private_key", "")


@pytest.fixture(autouse=True)
def _reset_process_state():
    # The login throttle and the food-search cache are process-global; without
    # this, one test's lockouts or cached results would bleed into the next.
    from app.routers import foods as foods_router

    throttle.clear()
    foods_router._search_cache.clear()
    yield


@pytest.fixture()
def app():
    # StaticPool keeps the single in-memory database alive across the many
    # connections the app opens; without it every connection would get its
    # own empty database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ships with foreign keys OFF; turn them on so ON DELETE SET NULL
    # (grocery items falling back to General) behaves like Postgres.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    real_app.dependency_overrides[get_db] = override_get_db
    # Exposed so tests can hook engine events (e.g. counting queries to pin
    # down N+1 regressions).
    real_app.state.test_engine = engine
    yield real_app
    real_app.dependency_overrides.clear()


def login(app, creds) -> TestClient:
    """A fresh client (own cookie jar) signed in as the given account."""
    client = TestClient(app)
    res = client.post(
        "/auth/login", json={"username": creds["username"], "password": creds["password"]}
    )
    assert res.status_code == 200, res.text
    return client


@pytest.fixture()
def anon(app) -> TestClient:
    """No session at all."""
    return TestClient(app)


@pytest.fixture()
def owner(app) -> TestClient:
    """The bootstrap account: parent + admin (bootstrap also signs you in)."""
    client = TestClient(app)
    res = client.post("/auth/bootstrap", json=OWNER)
    assert res.status_code == 201, res.text
    return client


@pytest.fixture()
def parent(app, owner) -> TestClient:
    """A second parent WITHOUT admin, to prove parent and admin are distinct."""
    res = owner.post(
        "/auth/users",
        json={**PARENT, "role": "parent", "is_admin": False},
    )
    assert res.status_code == 201, res.text
    return login(app, PARENT)


@pytest.fixture()
def child(app, owner) -> TestClient:
    """A child with NO birthdate — a minor, mirroring the real household."""
    res = owner.post("/auth/users", json={**CHILD, "role": "child"})
    assert res.status_code == 201, res.text
    return login(app, CHILD)


@pytest.fixture()
def adult_child(app, owner) -> TestClient:
    """Child role, 20 years old: proves restrictions key off age, not role."""
    birthdate = (dt.date.today() - dt.timedelta(days=20 * 366)).isoformat()
    res = owner.post("/auth/users", json={**ADULT_CHILD, "role": "child", "birthdate": birthdate})
    assert res.status_code == 201, res.text
    return login(app, ADULT_CHILD)


@pytest.fixture()
def homeless(app, owner) -> TestClient:
    """A new-household account that hasn't created its family yet."""
    res = owner.post("/auth/users", json={**JOSH, "role": "parent", "new_household": True})
    assert res.status_code == 201, res.text
    return login(app, JOSH)


@pytest.fixture()
def other(homeless) -> TestClient:
    """Family B's head of household, with its family created (for isolation)."""
    res = homeless.post("/families", json={"name": "The Bs"})
    assert res.status_code == 201, res.text
    return homeless


def user_id(client: TestClient) -> int:
    return client.get("/auth/me").json()["id"]


# ---- web push (shared by the push and approval tests) -------------------------


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")


@pytest.fixture()
def outbox(monkeypatch):
    """Record every webpush() call instead of hitting a push service."""
    calls = []

    def fake_webpush(subscription_info, data, **kwargs):
        calls.append(subscription_info["endpoint"])

    monkeypatch.setattr("pywebpush.webpush", fake_webpush)
    return calls
