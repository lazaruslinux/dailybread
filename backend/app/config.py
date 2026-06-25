from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Field names map to upper-case env vars (app_mode reads APP_MODE).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: str = "family"
    demo_mode: bool = False
    database_url: str = ""
    secret_key: str = "change-me"


settings = Settings()
