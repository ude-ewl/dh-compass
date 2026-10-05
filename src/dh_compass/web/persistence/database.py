"""SQLAlchemy connection factory for the web metadata database."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool

from ..settings import WebSettings


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Enable referential actions for every SQLite connection."""

    @event.listens_for(engine, "connect")
    def _set_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_metadata_engine(settings: WebSettings) -> Engine:
    """Create a SQLite engine for explicit web metadata operations.

    The parent directory is created at the connection boundary, not during
    module import.  In-memory databases use a static pool so migrations and
    requests in a test process observe the same database.
    """

    database_path = settings.metadata_database_path
    if database_path == ":memory:":
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        _enable_sqlite_foreign_keys(engine)
        return engine

    if not isinstance(database_path, Path):
        database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    url = URL.create("sqlite", database=str(database_path))
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    _enable_sqlite_foreign_keys(engine)
    return engine


__all__ = ["create_metadata_engine"]
