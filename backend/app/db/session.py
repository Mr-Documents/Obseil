"""Database engine and session management.

Synchronous SQLAlchemy is used deliberately: the analysis pipeline is CPU bound
(pandas / scikit-learn) and FastAPI already runs ``def`` route handlers in a
worker threadpool. See ``docs/IMPLEMENTATION_PLAN.md``.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def _engine_kwargs(url: str) -> dict[str, object]:
    """Engine options differ between SQLite (tests) and PostgreSQL (real)."""
    if url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,  # transparently recycle connections dropped by the server
        "pool_recycle": 1800,
    }


engine: Engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    future=True,
    **_engine_kwargs(settings.database_url),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignores foreign keys unless explicitly told not to.

    Without this the authorization tests would not exercise the same referential
    integrity guarantees that PostgreSQL enforces in production.
    """
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for use outside the request lifecycle (CLI, seeds)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
