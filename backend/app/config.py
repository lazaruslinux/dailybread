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

    # Web Push (reminders). Generate a VAPID key pair once per install (see
    # README); both keys are base64url strings. Leaving them empty simply
    # disables push - the app runs fine without it. The subject is a contact
    # URI the push services may use to reach the operator about problems.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    # How many minutes before a timed card its reminder goes out.
    reminder_lead_minutes: int = 15
    # Local hours (0-23) for the day's three scheduled pushes. Each has a
    # window it may send in (morning until noon, midday until 17, evening
    # until 22), so a server that was down at the slot still catches up
    # while the message makes sense - and never later.
    digest_hour: int = 7
    midday_hour: int = 12
    evening_hour: int = 19


settings = Settings()
