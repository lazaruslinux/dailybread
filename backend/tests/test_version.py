"""The running version: its lockstep with the frontend, and the announcement
every parent gets when the server comes up on a new one."""

import json
import pathlib

import pytest

import app.push as push_engine
from app.models import AppMeta, InboxEntry
from app.version import APP_VERSION
from tests.conftest import user_id

SUB = {
    "endpoint": "https://push.example/dad-phone",
    "keys": {"p256dh": "k1", "auth": "a1"},
}
SUB2 = {
    "endpoint": "https://push.example/mom-phone",
    "keys": {"p256dh": "k2", "auth": "a2"},
}

# backend/tests/ -> backend/ -> the repo root.
PACKAGE_JSON = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "package.json"


@pytest.mark.skipif(not PACKAGE_JSON.exists(), reason="frontend/ is not in the backend image")
def test_the_backend_and_frontend_versions_match():
    frontend = json.loads(PACKAGE_JSON.read_text())["version"]
    assert frontend == APP_VERSION, (
        "app/version.py and frontend/package.json must be bumped together"
    )


def _stored_version(TestingSession) -> str | None:
    with TestingSession() as db:
        row = db.get(AppMeta, "app_version")
        return row.value if row else None


def _set_version(TestingSession, value: str) -> None:
    with TestingSession() as db:
        db.merge(AppMeta(key="app_version", value=value))
        db.commit()


def _update_lines(TestingSession) -> list[InboxEntry]:
    with TestingSession() as db:
        return list(db.query(InboxEntry).filter(InboxEntry.kind == "update").all())


def test_a_fresh_install_records_the_version_silently(
    owner, configured, push_outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    push_outbox.clear()

    push_engine.announce_update()

    assert _stored_version(engine_db) == APP_VERSION
    assert _update_lines(engine_db) == []
    assert push_outbox == []


def test_a_new_version_tells_every_parent_once(
    owner, parent, configured, push_outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    parent.put("/push/subscription", json=SUB2)
    _set_version(engine_db, "0.0.1")
    push_outbox.clear()

    push_engine.announce_update()

    lines = _update_lines(engine_db)
    assert {line.user_id for line in lines} == {user_id(owner), user_id(parent)}
    assert lines[0].title == f"dailybread was updated to v{APP_VERSION}"
    assert f"/releases/tag/v{APP_VERSION}" in lines[0].body
    endpoints = {endpoint for endpoint, _ in push_outbox}
    assert endpoints == {SUB["endpoint"], SUB2["endpoint"]}
    payload = push_outbox[0][1]
    assert payload["title"] == f"dailybread was updated to v{APP_VERSION}"
    assert payload["url"].endswith(f"/releases/tag/v{APP_VERSION}")
    assert _stored_version(engine_db) == APP_VERSION

    # The next boot is on the same version: nothing more goes out.
    push_outbox.clear()
    push_engine.announce_update()
    assert len(_update_lines(engine_db)) == 2
    assert push_outbox == []


def test_minors_hear_nothing_about_an_update(
    owner, child, configured, push_outbox, engine_db
):
    child.put("/push/subscription", json=SUB2)
    _set_version(engine_db, "0.0.1")
    push_outbox.clear()

    push_engine.announce_update()

    assert {line.user_id for line in _update_lines(engine_db)} == {user_id(owner)}
    assert push_outbox == []  # the only subscribed device belongs to the kid


def test_a_restart_on_the_same_version_says_nothing(
    owner, configured, push_outbox, engine_db
):
    owner.put("/push/subscription", json=SUB)
    _set_version(engine_db, APP_VERSION)
    push_outbox.clear()

    push_engine.announce_update()

    assert _update_lines(engine_db) == []
    assert push_outbox == []
