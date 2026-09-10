"""Shared pytest fixtures.

The suite runs against an in-memory SQLite database so that it is fast and
requires no services. Model definitions are deliberately dialect-portable (see
``app/db/base.py``); anything genuinely PostgreSQL-specific is exercised by the
migration job in CI, which runs against a real PostgreSQL service.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

# Environment must be configured before app.core.config is first imported.
_TMP_STORAGE = Path(tempfile.mkdtemp(prefix="obseil-test-"))
os.environ.setdefault("OBSEIL_ENV", "test")
os.environ.setdefault("OBSEIL_SECRET_KEY", "test-secret-key-not-used-in-production-0123456789")
os.environ["OBSEIL_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["OBSEIL_STORAGE_PATH"] = str(_TMP_STORAGE)
# bcrypt's real cost is the single slowest thing in this suite. Four is the
# library minimum and is fine here: these tests assert that hashing happens and
# that it salts, never that it is expensive. Production refuses anything below
# `MINIMUM_PRODUCTION_HASH_ROUNDS`, which `test_security.py` asserts.
os.environ["OBSEIL_PASSWORD_HASH_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.ratelimit import InMemoryRateLimiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import registry as _registry  # noqa: E402,F401
from app.models.user import User  # noqa: E402
from app.services import auth_service  # noqa: E402

DEFAULT_PASSWORD = "obseil-test-1234"


@pytest.fixture(autouse=True)
def _database() -> Iterator[None]:
    """Give every test a pristine schema."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _login_attempts() -> Iterator[None]:
    """Give every test a clean slate of login failures.

    The limiter is module state that deliberately outlives a request, so
    without this a test that exhausts the limit would make later tests fail
    depending on the order they ran in.
    """
    from app.api.v1.routes.auth import login_limiter

    if isinstance(login_limiter, InMemoryRateLimiter):
        login_limiter.clear()
    yield
    if isinstance(login_limiter, InMemoryRateLimiter):
        login_limiter.clear()


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """A TestClient whose requests share the test's database session."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- Account helpers --------------------------------------------------------
UserFactory = Callable[..., User]


@pytest.fixture
def make_user(db: Session) -> UserFactory:
    """Create a registered account directly, bypassing the HTTP layer."""
    counter = {"n": 0}

    def _make(
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        full_name: str = "Test Analyst",
    ) -> User:
        counter["n"] += 1
        return auth_service.register_user(
            db,
            email=email or f"analyst{counter['n']}@example.com",
            full_name=full_name,
            password=password,
        )

    return _make


@pytest.fixture
def user(make_user: UserFactory) -> User:
    return make_user()


@pytest.fixture
def auth_headers() -> Callable[[User], dict[str, str]]:
    """Bearer headers for a given user."""

    def _headers(target: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth_service.issue_tokens(target).access_token}"}

    return _headers


@pytest.fixture
def authed_client(
    client: TestClient, user: User, auth_headers: Callable[[User], dict[str, str]]
) -> TestClient:
    """A TestClient already signed in as the `user` fixture."""
    client.headers.update(auth_headers(user))
    return client
