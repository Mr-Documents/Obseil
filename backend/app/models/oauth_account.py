"""A third-party identity linked to an Obseil account."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class OAuthAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One provider identity - a Google or GitHub account - owned by a user.

    A separate table rather than columns on ``users`` because the relationship
    is genuinely one-to-many: somebody can sign in with Google today, link
    GitHub tomorrow, and still have a password. Flattening it into ``users``
    would silently cap every account at a single sign-in method.

    The provider's account id is the identity, never the email. Emails at some
    providers can be changed or reassigned; the subject identifier cannot. The
    email is stored only so an operator can see which address was presented.
    """

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        # One provider identity maps to exactly one Obseil account, so a second
        # user can never claim an identity that is already linked.
        UniqueConstraint("provider", "provider_account_id", name="uq_oauth_provider_account"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(191), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    user: Mapped[User] = relationship(back_populates="oauth_accounts")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OAuthAccount {self.provider}:{self.provider_account_id}>"
