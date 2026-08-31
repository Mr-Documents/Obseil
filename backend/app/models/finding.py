"""Finding and feedback models.

A **Finding** is one reviewable problem attached to one analysis. Findings are
re-created on every run rather than updated, because a finding describes what a
specific analysis saw; carrying one forward would make history dishonest.

**FindingFeedback** is the user's verdict on a finding: a real issue, or a false
positive. It is stored separately from the finding's status because the two
answer different questions ("have I dealt with this?" vs "was the detector
right?"), and because the verdicts are the training signal for a future
feedback loop.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ID_LENGTH, Base, JSONColumn, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.dataset import DatasetAnalysis


class FindingStatus(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    IGNORED = "ignored"


class FeedbackVerdict(StrEnum):
    """Was the detector right?

    Deliberately only two values. A three-way scale invites "unsure", which
    carries no signal and is where most triage queues go to die.
    """

    VALID_ISSUE = "valid_issue"
    FALSE_POSITIVE = "false_positive"


class Finding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "findings"
    __table_args__ = (
        # The findings page filters by analysis and sorts by severity.
        Index("ix_findings_analysis_severity", "analysis_id", "severity"),
        Index("ix_findings_dataset_status", "dataset_id", "status"),
    )

    analysis_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("dataset_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Denormalised so dataset- and project-scoped queries do not need joins.
    #: Safe: a finding never moves between datasets.
    dataset_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    #: "rule" or "anomaly" — kept as a column so the UI can separate
    #: deterministic facts from model suggestions without parsing the type.
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="rule", index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    #: Sortable rank for severity; ordering by the string would give
    #: critical < high < low < medium, which is nonsense.
    severity_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    detection_method: Mapped[str] = mapped_column(String(48), nullable=False)

    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    columns: Mapped[list[Any] | None] = mapped_column(JSONColumn, nullable=True)
    affected_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affected_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)

    details: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn, nullable=True)
    sample_row_indices: Mapped[list[Any] | None] = mapped_column(JSONColumn, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(FindingStatus, native_enum=False, length=16, validate_strings=True),
        nullable=False,
        default=FindingStatus.OPEN,
    )

    analysis: Mapped[DatasetAnalysis] = relationship(back_populates="findings")
    feedback: Mapped[FindingFeedback | None] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Finding {self.type} severity={self.severity} status={self.status}>"


class FindingFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One user's verdict on one finding.

    The unique constraint is on ``finding_id`` alone: in the current
    single-owner model a finding has exactly one reviewer. When projects gain
    members this becomes ``(finding_id, user_id)`` — one migration, no change
    to the surrounding code.
    """

    __tablename__ = "finding_feedback"
    __table_args__ = (UniqueConstraint("finding_id", name="uq_finding_feedback_finding"),)

    finding_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    verdict: Mapped[str] = mapped_column(
        Enum(FeedbackVerdict, native_enum=False, length=24, validate_strings=True),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    finding: Mapped[Finding] = relationship(back_populates="feedback")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<FindingFeedback {self.verdict} finding={self.finding_id}>"
