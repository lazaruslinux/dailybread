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


settings = Settings()
