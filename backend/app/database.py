import sqlite3
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings
from .services.numeric_values import install_sqlite_numeric_adapter


def _enable_sqlite_foreign_keys(
    dbapi_connection: object,
    _connection_record: object,
) -> None:
    """Enable SQLite foreign-key enforcement for each configured connection."""

    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_jobgrid_engine(
    database_url: str,
    *,
    enforce_sqlite_foreign_keys: bool = True,
    **kwargs: Any,
) -> Engine:
    """Create an engine with JobGrid's connection-level database adapters.

    The JG-018 numeric adapter is installed at the SQLAlchemy Engine class level
    so every SQLite DBAPI connection receives `jobgrid_numeric(value)`. SQLite
    engines created through this helper also enforce foreign keys, matching the
    constraint behavior expected from PostgreSQL.
    """

    install_sqlite_numeric_adapter()
    configured_engine = create_engine(database_url, **kwargs)

    if (
        enforce_sqlite_foreign_keys
        and not event.contains(
            configured_engine,
            "connect",
            _enable_sqlite_foreign_keys,
        )
    ):
        event.listen(
            configured_engine,
            "connect",
            _enable_sqlite_foreign_keys,
        )

    return configured_engine


engine = create_jobgrid_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
