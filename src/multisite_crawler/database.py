from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


class DatabaseUnavailableError(RuntimeError):
    """Raised when a database URL is missing or its connection cannot be used."""


def beijing_now() -> datetime:
    """Return the current Beijing civil time without a timezone offset."""
    return datetime.now(BEIJING_TIMEZONE).replace(tzinfo=None)


def load_database_url(variable_name: str = "DATABASE_URL") -> str:
    """Load a required database URL without including its value in errors."""
    database_url = os.environ.get(variable_name, "").strip()
    if not database_url:
        message = f"{variable_name} is required for database access."
        raise DatabaseUnavailableError(message)
    return database_url


def build_engine(database_url: str) -> Engine:
    """Create a synchronous PostgreSQL engine with stale-connection checks."""
    return create_engine(
        database_url,
        connect_args={"connect_timeout": 3},
        pool_pre_ping=True,
    )


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create sessions bound to a newly configured database engine."""
    return sessionmaker(bind=build_engine(database_url))


def probe_connection(engine: Engine) -> None:
    """Verify an engine can execute a trivial query without exposing its URL."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise DatabaseUnavailableError("Database connection probe failed.") from error
