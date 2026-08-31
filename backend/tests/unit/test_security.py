"""Password hashing and token handling."""

from __future__ import annotations

import time
from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second, "each hash must use a distinct salt"
    assert verify_password("correct horse battery staple", first)
    assert verify_password("correct horse battery staple", second)


def test_wrong_password_is_rejected() -> None:
    assert not verify_password("wrong", hash_password("right"))


def test_malformed_hash_fails_closed_instead_of_raising() -> None:
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_overlong_password_is_rejected_rather_than_truncated() -> None:
    with pytest.raises(ValueError, match="at most 72 bytes"):
        hash_password("x" * 73)


def test_access_token_round_trip() -> None:
    token = create_access_token("user-123")
    assert decode_token(token, "access") == "user-123"


def test_refresh_token_cannot_be_used_as_an_access_token() -> None:
    refresh = create_refresh_token("user-123")
    assert decode_token(refresh, "refresh") == "user-123"
    with pytest.raises(AuthenticationError):
        decode_token(refresh, "access")


def test_token_signed_with_another_key_is_rejected() -> None:
    forged = jwt.encode({"sub": "user-123", "type": "access"}, "another-key", algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_token(forged, "access")


def test_expired_token_reports_a_dedicated_code() -> None:
    expired = jwt.encode(
        {
            "sub": "user-123",
            "type": "access",
            "exp": int(time.time() - timedelta(minutes=1).total_seconds()),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(AuthenticationError) as excinfo:
        decode_token(expired, "access")
    assert excinfo.value.code == "token_expired"
