from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from multisite_crawler.models import Base

config = context.config
target_metadata = Base.metadata


def require_database_url() -> str:
    """Return an explicit Alembic or environment URL before touching a database."""
    database_url = config.get_main_option("sqlalchemy.url").strip()
    if not database_url:
        database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Alembic requires sqlalchemy.url or DATABASE_URL.")
    config.set_main_option("sqlalchemy.url", database_url)
    return database_url


def run_migrations_offline() -> None:
    """Run migrations without opening a connection."""
    context.configure(
        url=require_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the explicitly configured database."""
    require_database_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
