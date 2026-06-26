from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# Every ORM model subclasses this. SQLAlchemy collects their table definitions
# on Base.metadata, which is what create_all() uses to build the schema.
class Base(DeclarativeBase):
    pass


# pool_pre_ping tests a pooled connection with a lightweight query before
# handing it out, so a Postgres restart doesn't give the app a dead socket.
engine: Engine | None = (
    create_engine(settings.database_url, pool_pre_ping=True)
    if settings.database_url
    else None
)

# A factory that produces Session objects bound to our engine. expire_on_commit
# is off so we can still read an object's fields after commit() without a reload.
SessionLocal = (
    sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    if engine is not None
    else None
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: open a DB session per request, always close it."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
