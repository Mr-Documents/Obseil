"""User-defined quality rule model.

A rule is the mechanism by which a user supplies domain knowledge the built-in
detectors deliberately refuse to invent - see
``app/quality/detectors/validity.py``.

This row is the stored definition. ``app.quality.rules.RuleSpec`` is the domain
object the analysis pipeline receives, and ``app.schemas.rule`` is the HTTP
contract: the same three-layer split the findings already use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ID_LENGTH, Base, JSONColumn, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class Rule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One assertion a user has made about their own data."""

    __tablename__ = "rules"
    __table_args__ = (
        # Every analysis asks exactly one question of this table: "the enabled
        # rules for this project".
        Index("ix_rules_project_enabled", "project_id", "enabled"),
        # A finding's title is derived from its rule's name, so two rules
        # sharing a name within one project would produce two findings nobody
        # could tell apart. Enforced by the database rather than by whichever
        # code path happens to run.
        UniqueConstraint("project_id", "name", name="uq_rules_project_name"),
    )

    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Null for predicates that are not about a single column. Every predicate
    #: requires one today; cross-column predicates arrive in the next slice.
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    predicate: Mapped[str] = mapped_column(String(32), nullable=False)

    #: Predicate-specific configuration: schemaless in the database, strictly
    #: typed in the application by the parameter model the predicate registry
    #: names. The same arrangement as ``DatasetAnalysis.profile``, which is a
    #: JSON document governed by ``DatasetProfile``.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONColumn, nullable=False, default=dict)

    #: Chosen by the rule's author, unlike a detector's severity, which is
    #: derived from the data. The dimension caps in ``app.quality.scoring``
    #: still apply, so an author cannot make their own rule dominate the score.
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    dimension: Mapped[str] = mapped_column(String(24), nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: Bumped when the rule's *meaning* changes - predicate, parameters,
    #: severity, dimension or column. Renaming it does not count. Findings
    #: record the version that judged them, so a history spanning a change can
    #: say which definition applied rather than implying one always did.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[Project] = relationship(back_populates="rules")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Rule {self.name!r} {self.predicate} enabled={self.enabled}>"
