"""Turning a provider profile into an Obseil account.

The rules below are short, and one of them carries the security of the whole
feature: **an identity may only attach to an existing account when the provider
says it has verified the email.**

Without that check, anybody who can obtain a provider account claiming
`someone@company.com` - at a provider that never confirms addresses - could
sign in and be handed the existing Obseil account belonging to that address.
Auto-linking on an unverified email is one of the classic ways OAuth is used to
take over accounts, and it looks like a convenience feature right up until it
is exploited.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.oauth.base import OAuthProfile
from app.services.auth_service import normalize_email

logger = logging.getLogger(__name__)

#: Shown when a provider gives us nothing we can safely use as an identity.
_UNUSABLE = (
    "That account could not be used to sign in because {reason}. "
    "Try another provider, or create an account with an email address."
)


def _find_linked(db: Session, profile: OAuthProfile) -> OAuthAccount | None:
    return db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == profile.provider,
            OAuthAccount.provider_account_id == profile.account_id,
        )
    )


def sign_in_with_provider(db: Session, profile: OAuthProfile) -> User:
    """Return the Obseil account for ``profile``, creating or linking as needed."""
    linked = _find_linked(db, profile)
    if linked is not None:
        # The identity is already known. Nothing about the email matters here:
        # the provider's subject id is what was matched, and it cannot be
        # reassigned the way an address can.
        if not linked.user.is_active:
            raise AuthenticationError("This account has been deactivated.", code="account_inactive")
        _refresh_recorded_email(db, linked, profile)
        return linked.user

    if not profile.email:
        raise AuthenticationError(
            _UNUSABLE.format(reason="the provider did not share an email address"),
            code="oauth_no_email",
        )
    if not profile.email_verified:
        # Deliberately refused rather than quietly creating a second account:
        # the person would end up with two, and the more dangerous reading is
        # that we would be accepting an address nobody has proven they own.
        raise AuthenticationError(
            _UNUSABLE.format(reason="the provider has not verified that email address"),
            code="oauth_email_unverified",
        )

    email = normalize_email(profile.email)
    existing = db.scalar(select(User).where(User.email == email))

    if existing is not None:
        if not existing.is_active:
            raise AuthenticationError("This account has been deactivated.", code="account_inactive")
        user = existing
        logger.info(
            "Linked a provider identity to an existing account",
            extra={"user_id": user.id, "provider": profile.provider},
        )
    else:
        user = User(
            email=email,
            full_name=profile.full_name or email.split("@")[0],
            # No password at all, rather than an unguessable one: the account
            # genuinely has no password, and `authenticate_user` refuses it.
            hashed_password=None,
        )
        db.add(user)
        db.flush()
        logger.info(
            "Created an account from a provider identity",
            extra={"user_id": user.id, "provider": profile.provider},
        )

    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=profile.provider,
            provider_account_id=profile.account_id,
            email=profile.email,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Two callbacks for the same brand-new identity raced. The unique
        # constraint is the arbiter; the loser re-reads the winner's row.
        db.rollback()
        linked = _find_linked(db, profile)
        if linked is None:
            raise
        return linked.user

    db.refresh(user)
    return user


def _refresh_recorded_email(db: Session, account: OAuthAccount, profile: OAuthProfile) -> None:
    """Keep the recorded address current, without touching the login email.

    This column is for an operator looking at where an identity came from. The
    account's own email is never changed by a provider, because that would let
    a change at the provider silently move an Obseil login.
    """
    if profile.email and account.email != profile.email:
        account.email = profile.email
        db.commit()


def linked_providers(db: Session, user: User) -> list[str]:
    return list(
        db.scalars(
            select(OAuthAccount.provider)
            .where(OAuthAccount.user_id == user.id)
            .order_by(OAuthAccount.provider)
        )
    )
