"""Authentication business logic.

Route handlers do not touch the ORM or hashing directly; everything goes
through this module so the rules (email normalisation, timing-safe login,
active-account checks) exist in exactly one place.
"""

from __future__ import annotations

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenPair

logger = logging.getLogger(__name__)

# A real bcrypt hash of a value nobody can supply. Verifying against it when the
# email is unknown keeps login timing roughly constant, so an attacker cannot
# enumerate registered addresses by measuring response times.
#
# Generated at import rather than hardcoded, because the comparison only holds
# if this hash carries the *same* work factor as the stored passwords it stands
# in for. A literal pinned at one cost would start leaking the difference the
# moment an operator changed `OBSEIL_PASSWORD_HASH_ROUNDS` - the timing oracle
# would be back, quietly, on exactly the path built to close it.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def normalize_email(email: str) -> str:
    """Emails are case-insensitive identifiers; store and compare them lowered."""
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def register_user(db: Session, *, email: str, full_name: str, password: str) -> User:
    """Create an account, or raise ``ConflictError`` if the email is taken."""
    normalized = normalize_email(email)

    user = User(
        email=normalized,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # A duplicate can also arrive from a concurrent request that passed the
        # same pre-check, so the unique constraint is the real guard.
        db.rollback()
        raise ConflictError(
            "An account with that email address already exists.",
            code="email_already_registered",
        ) from None

    db.refresh(user)
    logger.info("Registered user", extra={"user_id": user.id})
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    """Verify credentials and return the user, or raise ``AuthenticationError``.

    The same message is returned whether the email is unknown or the password
    is wrong - telling them apart would turn the login form into an account
    enumeration oracle.
    """
    user = get_user_by_email(db, email)

    if user is None:
        verify_password(password, _DUMMY_HASH)
        logger.info("Login failed: unknown email")
        raise AuthenticationError("Incorrect email or password.", code="invalid_credentials")

    if not verify_password(password, user.hashed_password):
        logger.info("Login failed: bad password", extra={"user_id": user.id})
        raise AuthenticationError("Incorrect email or password.", code="invalid_credentials")

    if not user.is_active:
        logger.warning("Login blocked: inactive account", extra={"user_id": user.id})
        raise AuthenticationError("This account has been deactivated.", code="account_inactive")

    return user


def refresh_tokens(db: Session, refresh_token: str) -> tuple[User, TokenPair]:
    """Exchange a valid refresh token for a fresh pair.

    Rotating the refresh token on every use limits the window in which a stolen
    token is useful.
    """
    user_id = decode_token(refresh_token, "refresh")
    user = get_user_by_id(db, user_id)

    if user is None or not user.is_active:
        raise AuthenticationError("Your session is no longer valid. Please sign in again.")

    return user, issue_tokens(user)
