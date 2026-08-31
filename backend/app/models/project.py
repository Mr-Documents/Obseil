"""Project model — the container for datasets and their analyses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ID_LENGTH, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.user import User


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named workspace owned by exactly one user.

    The column is called ``owner_id`` rather than ``user_id`` on purpose: when
    team collaboration arrives, a ``project_members`` join table can be added
    beside it without renaming anything or rewriting the authorisation checks,
    which all funnel through a single ``get_owned_project`` helper.
    """

    __tablename__ = "projects"
    __table_args__ = (
        # Every project listing is scoped to the owner and sorted by recency.
        Index("ix_projects_owner_updated", "owner_id", "updated_at"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped[User] = relationship(back_populates="projects")
    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Dataset.created_at.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Project {self.name!r} owner={self.owner_id}>"
