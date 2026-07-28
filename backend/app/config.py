import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Field names map to upper-case env vars (app_mode reads APP_MODE).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: str = "family"
    demo_mode: bool = False
    database_url: str = ""
    secret_key: str = "change-me"

    # Session/auth settings. Sessions are sliding: an authenticated request
    # made once the token is a day old gets a fresh one, so a login only
    # expires after session_days of not using the app at all.
    session_days: int = 60  # how long an *idle* login stays valid
    session_refresh_after_hours: int = 24  # re-issue tokens older than this
    cookie_name: str = "db_session"
    # Whether the session cookie is HTTPS-only. False for local http dev; set
    # COOKIE_SECURE=true in production, behind a reverse proxy serving HTTPS.
    cookie_secure: bool = False

    # Where uploaded media (avatar images) are written. Kept on local disk so
    # photos never leave the box; point MEDIA_ROOT at a persistent volume in
    # production. Relative paths resolve against the backend working directory.
    media_root: str = "./media"

    # Food database: the server proxies food search to USDA FoodData Central and
    # barcode lookups to Open Food Facts, so the family's phones never call a
    # third party directly. A free key from https://fdc.nal.usda.gov/api-key-signup
    # enables search; empty disables it (barcodes need no key). Recipes compute
    # their nutrition from foods looked up here.
    usda_api_key: str = ""

    # Barcode health check: grams of sugar per serving at or above which a food
    # is flagged for added sugar (the alias/total-sugar fallbacks use the same
    # bar). Per serving, not per 100 g.
    health_added_sugar_g: float = 5.0

    # Web Push (reminders). Generate a VAPID key pair once per install (see
    # README); both keys are base64url strings. Leaving them empty simply
    # disables push - the app runs fine without it. The subject is a contact
    # URI the push services may use to reach the operator about problems.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    # How many minutes before a timed card its reminder goes out. Appointments
    # get a longer runway: an hour to get shoes on and drive somewhere.
    reminder_lead_minutes: int = 15
    appointment_lead_minutes: int = 60
    # Local hours (0-23) for the day's scheduled pushes. Each has a window it
    # may send in (morning until noon, evening until 22), so a server that
    # was down at the slot still catches up while the message makes sense,
    # and never later.
    digest_hour: int = 7
    evening_hour: int = 19
    # A member's phone counts as quiet when its health sync hasn't posted for
    # this many hours; the nudge repeats at most weekly.
    sync_stale_hours: int = 48


settings = Settings()

# The placeholder secrets shipped in the repo (.env.example and the field
# default above). An install still using one is forgeable by anyone who can
# read the public source, so startup refuses them outright.
_PLACEHOLDER_SECRETS = {"", "change-me", "change-me-to-a-long-random-string"}


def check_deploy_config() -> None:
    """Refuse to start while .env still holds the repo's placeholder values.

    Called once at app import. Raises SystemExit with a plain-language fix
    instead of serving an instance whose session-signing key or database
    password is public knowledge.
    """
    problems = []
    if settings.secret_key in _PLACEHOLDER_SECRETS:
        problems.append(
            "SECRET_KEY is unset or still the placeholder. Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
            "and put it in .env as SECRET_KEY=..."
        )
    if not settings.database_url:
        problems.append("DATABASE_URL is empty. Copy .env.example to .env and fill it in.")
    elif ":change-me@" in settings.database_url:
        problems.append(
            "DATABASE_URL still uses the placeholder database password. Pick a real\n"
            "POSTGRES_PASSWORD in .env and use the same value in DATABASE_URL.\n"
            "Note: Postgres keeps the password it was first started with; if the\n"
            "database volume already exists, see docs/self-hosting.md on changing it."
        )
    # Not a Settings field: the backend only receives this via compose env_file,
    # but catching it here stops the fix-one-forget-the-other mistake before the
    # Postgres volume freezes the placeholder on first init.
    if os.environ.get("POSTGRES_PASSWORD") == "change-me":
        problems.append(
            "POSTGRES_PASSWORD in .env is still the placeholder. Pick a real one\n"
            "and use the same value in DATABASE_URL."
        )
    if problems:
        raise SystemExit(
            "dailybread refused to start: insecure or incomplete configuration.\n\n"
            + "\n\n".join(problems)
        )
