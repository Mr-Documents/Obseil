"""Engine configuration, which differs by database and is easy to get wrong."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.pool import QueuePool, StaticPool

from app.db.session import (
    _engine_kwargs,
    _is_in_memory_sqlite,
    _sqlite_path,
    ensure_sqlite_directory,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite+pysqlite:///:memory:", True),
        ("sqlite://", True),
        ("sqlite:///", True),
        ("sqlite:///:memory:?cache=shared", True),
        ("sqlite+pysqlite:///./var/e2e.db", False),
        ("sqlite:///abs/path.db", False),
        # A file that merely mentions memory in its name is still a file.
        ("sqlite:///memory.db", False),
    ],
)
def test_in_memory_sqlite_is_recognised(url: str, expected: bool) -> None:
    assert _is_in_memory_sqlite(url) is expected


class TestEnginePooling:
    """An in-memory database *is* its connection; a file-backed one is not."""

    def test_in_memory_sqlite_shares_one_connection(self) -> None:
        assert _engine_kwargs("sqlite+pysqlite:///:memory:")["poolclass"] is StaticPool

    def test_file_backed_sqlite_gets_a_real_pool(self) -> None:
        # StaticPool here funnels every request thread through one connection,
        # which SQLite does not serialise: it surfaced as InterfaceError and as
        # queries returning no rows under the dashboard's concurrent requests.
        assert _engine_kwargs("sqlite+pysqlite:///./var/e2e.db")["poolclass"] is QueuePool

    def test_sqlite_always_allows_a_connection_to_cross_threads(self) -> None:
        for url in ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///./var/e2e.db"):
            assert _engine_kwargs(url)["connect_args"] == {"check_same_thread": False}

    def test_postgresql_is_pooled_and_pre_pinged(self) -> None:
        kwargs = _engine_kwargs("postgresql+psycopg://obseil:obseil@localhost:5432/obseil")
        assert kwargs["pool_pre_ping"] is True
        assert "poolclass" not in kwargs


class TestSqliteDirectory:
    """SQLite creates the database file but never the directory holding it."""

    def test_a_missing_directory_is_created(self, tmp_path: Path) -> None:
        """The CI failure this fixes: `var/` is gitignored, so a fresh
        checkout has no directory for the database to live in, and Alembic
        dies with "unable to open database file" before anything can run."""
        target = tmp_path / "var" / "e2e.db"
        ensure_sqlite_directory(f"sqlite+pysqlite:///{target.as_posix()}")
        assert target.parent.is_dir()

    def test_nested_directories_are_created(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c" / "app.db"
        ensure_sqlite_directory(f"sqlite+pysqlite:///{target.as_posix()}")
        assert target.parent.is_dir()

    def test_an_existing_directory_is_left_alone(self, tmp_path: Path) -> None:
        keeper = tmp_path / "keep.txt"
        keeper.write_text("untouched", encoding="utf-8")
        ensure_sqlite_directory(f"sqlite+pysqlite:///{(tmp_path / 'app.db').as_posix()}")
        assert keeper.read_text(encoding="utf-8") == "untouched"

    def test_an_in_memory_database_creates_nothing(self, tmp_path: Path) -> None:
        ensure_sqlite_directory("sqlite+pysqlite:///:memory:")
        assert not list(tmp_path.iterdir())

    def test_postgresql_is_ignored(self, tmp_path: Path) -> None:
        ensure_sqlite_directory("postgresql+psycopg://obseil:obseil@localhost:5432/obseil")
        assert not list(tmp_path.iterdir())

    def test_a_bare_filename_needs_no_directory(self) -> None:
        """Must not raise, and must not create anything called "."."""
        ensure_sqlite_directory("sqlite+pysqlite:///app.db")


class TestSqliteUrlSlashes:
    """Three slashes mean relative, four mean absolute.

    These assert the parsing directly rather than through the filesystem, so
    the distinction is checked on every platform. Going through `tmp_path`
    hides it on Windows, where an absolute path starts with a drive letter and
    survives having its leading slashes stripped - which is exactly how this
    shipped and then failed on Linux CI.
    """

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("sqlite:///relative.db", "relative.db"),
            ("sqlite+pysqlite:///./var/e2e.db", "./var/e2e.db"),
            ("sqlite:///nested/dir/app.db", "nested/dir/app.db"),
            # Four slashes: the path itself is absolute and must stay that way.
            ("sqlite:////var/lib/obseil/app.db", "/var/lib/obseil/app.db"),
            ("sqlite+pysqlite:////tmp/pytest-1/var/e2e.db", "/tmp/pytest-1/var/e2e.db"),
            # Windows spells an absolute path with a drive letter.
            ("sqlite:///C:/data/app.db", "C:/data/app.db"),
            ("sqlite:///:memory:", ":memory:"),
            ("sqlite://", ""),
        ],
    )
    def test_exactly_one_leading_slash_belongs_to_the_scheme(self, url: str, expected: str) -> None:
        assert _sqlite_path(url) == expected

    def test_an_absolute_url_is_not_turned_into_a_relative_path(self) -> None:
        """The regression: a directory created under the working directory
        instead of at the absolute location the operator configured."""
        assert _sqlite_path("sqlite:////var/lib/obseil/app.db").startswith("/")
