"""Database engine and session management.

Synchronous SQLAlchemy is used deliberately: the analysis pipeline is CPU bound
(pandas / scikit-learn) and FastAPI already runs ``def`` route handlers in a
worker threadpool. See ``docs/IMPLEMENTATION_PLAN.md``.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import settings


def _sqlite_path(url: str) -> str:
    """The database portion of a SQLite URL.

    SQLAlchemy spells a *relative* path with three slashes and an *absolute*
    one with four, so exactly one leading slash belongs to the scheme and any
    others belong to the path. Stripping them all silently turns
    ``sqlite:////var/lib/app.db`` into a path relative to the working
    directory - which looks fine on Windows, where absolute paths start with a
    drive letter, and is wrong everywhere else.
    """
    return url.partition("://")[2].partition("?")[0].removeprefix("/")


def _is_in_memory_sqlite(url: str) -> bool:
    """True for SQLite URLs whose database lives inside the connection itself.

    Both spellings count: an explicit ``:memory:`` and the bare ``sqlite://``
    with no path at all.
    """
    return _sqlite_path(url) in {"", ":memory:"}


def ensure_sqlite_directory(url: str) -> None:
    """Create the directory that will hold a file-backed SQLite database.

    SQLite creates the database file but never the directory above it, so a
    URL like ``sqlite:///./var/app.db`` fails with "unable to open database
    file" whenever ``var/`` is absent. It usually is: runtime directories are
    gitignored, so this is the state of every fresh checkout and every CI run.

    Alembic hits this before the application does, because migrations run first
    and nothing has had a chance to create the directory yet.
    """
    if not url.startswith("sqlite") or _is_in_memory_sqlite(url):
        return
    parent = Path(_sqlite_path(url)).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)


def _engine_kwargs(url: str) -> dict[str, object]:
    """Engine options differ between SQLite and PostgreSQL (production)."""
    if url.startswith("sqlite"):
        # `check_same_thread` is off because route handlers are plain `def`, so
        # FastAPI runs them in a threadpool and a connection legitimately moves
        # between threads. The pool still hands each connection to one thread at
        # a time, which is what makes that safe.
        #
        # The pool class is the part that matters. An in-memory database *is*
        # its connection - open a second one and you get a second, empty
        # database - so it needs StaticPool's single shared connection. A
        # file-backed database is the exact opposite: StaticPool would funnel
        # every concurrent request through one connection, and SQLite's driver
        # does not serialise concurrent use of a single connection. That failed
        # as `InterfaceError: bad parameter or other API misuse` and, worse, as
        # queries returning no rows - a freshly created project answering 404 -
        # whenever the dashboard fired its four requests at once.
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool if _is_in_memory_sqlite(url) else QueuePool,
        }
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,  # transparently recycle connections dropped by the server
        "pool_recycle": 1800,
    }


ensure_sqlite_directory(settings.database_url)

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
    if not _is_in_memory_sqlite(settings.database_url):
        # Readers no longer block on the writer, and a writer that does collide
        # waits rather than failing the request outright. Neither applies to an
        # in-memory database, which has exactly one connection.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
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
