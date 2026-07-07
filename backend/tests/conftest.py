"""Shared test fixtures.

Each test gets the real FastAPI app wired to a fresh in-memory SQLite
database (via dependency_overrides on get_db), so tests are fully isolated
from each other and from Postgres. Role fixtures return separate TestClients,
each with its own cookie jar, exercising the real auth endpoints end to end.
"""

import os

# Must happen before any app import: Settings reads the environment once.
# 32+ bytes so PyJWT doesn't warn about a weak HS256 key during tests.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-0123456789abcdef")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app as real_app

# Throwaway credentials that exist only inside a single test run.
OWNER = {"username": "owner", "display_name": "Owner Parent", "password": "owner-pass-123"}
PARENT = {"username": "parent2", "display_name": "Second Parent", "password": "parent-pass-123"}
CHILD = {"username": "kid", "display_name": "The Kid", "password": "child-pass-123"}
# A second household, for cross-family isolation checks.
JOSH = {"username": "josh", "display_name": "Josh", "password": "josh-pass-1234"}


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
    res = owner.post("/auth/users", json={**CHILD, "role": "child"})
    assert res.status_code == 201, res.text
    return login(app, CHILD)


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
