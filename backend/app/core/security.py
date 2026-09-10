"""Password hashing and JWT issuing/verification.

``bcrypt`` is used directly rather than through passlib, which is unmaintained
and incompatible with modern bcrypt releases. Access tokens are short lived;
refresh tokens carry a distinct ``type`` claim so an access token can never be
replayed at the refresh endpoint (and vice versa).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AuthenticationError

TokenType = Literal["access", "refresh"]

# bcrypt silently truncates input beyond 72 bytes; reject rather than truncate.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Return a bcrypt hash for ``password``."""
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(settings.password_hash_rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification of ``password`` against a stored hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed hash is a failed login, never a 500.
        return False


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str) -> str:
    return _create_token(subject, "access", timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(subject: str) -> str:
    return _create_token(subject, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: TokenType) -> str:
    """Validate ``token`` and return its subject, or raise ``AuthenticationError``."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            "Your session has expired. Please sign in again.", code="token_expired"
        ) from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc

    if payload.get("type") != expected_type:
        raise AuthenticationError("Invalid authentication token.")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthenticationError("Invalid authentication token.")
    return subject
