"""User account model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.oauth_account import OAuthAccount
    from app.models.project import Project


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered Obseil account.

    Emails are stored lower-cased and are the login identifier, so the unique
    constraint is genuinely case-insensitive without needing a database
    extension such as ``citext``. Normalisation happens in the service layer.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Nullable: an account created through Google or GitHub has no password at
    # all. `authenticate_user` treats a null hash as "this account cannot be
    # signed into with a password", never as "any password will do".
    hashed_password: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    projects: Mapped[list[Project]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email}>"
