"""Alembic environment. Connects using the app's own settings so there is
exactly one source of truth for the database URL (the DATABASE_URL env var)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import check_deploy_config, settings
from app.db import Base
from app import models  # noqa: F401  (import registers tables on Base.metadata)

# Migrations run before the server in the container entrypoint, so this is the
# first thing a misconfigured install hits; refusing here shows the guard's
# plain-language message instead of a driver traceback.
check_deploy_config()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What autogenerate compares the live database against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade --sql)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the real database."""
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
