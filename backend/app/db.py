from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings

# pool_pre_ping tests a pooled connection with a lightweight query before
# handing it out, so a Postgres restart doesn't give the app a dead socket.
engine: Engine | None = (
    create_engine(settings.database_url, pool_pre_ping=True)
    if settings.database_url
    else None
)


def db_ok() -> tuple[bool, str]:
    """Return (healthy, detail) after trying a trivial query against Postgres."""
    if engine is None:
        return False, "DATABASE_URL is not set"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # surface any connection/driver error to the caller
        return False, str(exc)
    return True, "ok"
