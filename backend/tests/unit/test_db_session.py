"""Engine configuration, which differs by database and is easy to get wrong."""

from __future__ import annotations

import pytest
from sqlalchemy.pool import QueuePool, StaticPool

from app.db.session import _engine_kwargs, _is_in_memory_sqlite


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
