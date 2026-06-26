from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Field names map to upper-case env vars (app_mode reads APP_MODE).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: str = "family"
    demo_mode: bool = False
    database_url: str = ""
    secret_key: str = "change-me"

    # Session/auth settings.
    session_days: int = 7  # how long a login stays valid
    cookie_name: str = "db_session"
    # Whether the session cookie is HTTPS-only. False for local http dev;
    # set COOKIE_SECURE=true on the home server where Caddy serves HTTPS.
    cookie_secure: bool = False


settings = Settings()
