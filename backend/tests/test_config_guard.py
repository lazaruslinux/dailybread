"""The startup guard: the app must refuse to boot on the repo's placeholder
secrets, and accept a properly filled-in configuration."""

import pytest

from app.config import check_deploy_config, settings

GOOD_URL = "postgresql+psycopg://dailybread:s3cret-and-unique@db:5432/dailybread"


def _configure(monkeypatch, *, secret, url):
    monkeypatch.setattr(settings, "secret_key", secret)
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)


def test_accepts_real_configuration(monkeypatch):
    _configure(monkeypatch, secret="a-real-48-byte-random-string", url=GOOD_URL)
    check_deploy_config()  # must not raise


@pytest.mark.parametrize(
    "secret", ["", "change-me", "change-me-to-a-long-random-string"]
)
def test_refuses_placeholder_secret_key(monkeypatch, secret):
    _configure(monkeypatch, secret=secret, url=GOOD_URL)
    with pytest.raises(SystemExit, match="SECRET_KEY"):
        check_deploy_config()


def test_refuses_empty_database_url(monkeypatch):
    _configure(monkeypatch, secret="a-real-48-byte-random-string", url="")
    with pytest.raises(SystemExit, match="DATABASE_URL is empty"):
        check_deploy_config()


def test_refuses_placeholder_database_password(monkeypatch):
    _configure(
        monkeypatch,
        secret="a-real-48-byte-random-string",
        url="postgresql+psycopg://dailybread:change-me@db:5432/dailybread",
    )
    with pytest.raises(SystemExit, match="placeholder database password"):
        check_deploy_config()


def test_refuses_placeholder_postgres_password_env(monkeypatch):
    _configure(monkeypatch, secret="a-real-48-byte-random-string", url=GOOD_URL)
    monkeypatch.setenv("POSTGRES_PASSWORD", "change-me")
    with pytest.raises(SystemExit, match="POSTGRES_PASSWORD"):
        check_deploy_config()


def test_reports_every_problem_at_once(monkeypatch):
    _configure(monkeypatch, secret="change-me", url="")
    with pytest.raises(SystemExit) as excinfo:
        check_deploy_config()
    message = str(excinfo.value)
    assert "SECRET_KEY" in message and "DATABASE_URL" in message
