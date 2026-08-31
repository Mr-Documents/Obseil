"""Dataset and analysis models.

A **Dataset** is one uploaded file. It is immutable: re-uploading produces a new
dataset row, which is what makes "version 1 vs version 2" comparisons honest.

A **DatasetAnalysis** is one run of the pipeline over a dataset. A dataset can be
re-analysed (after a detector improves, say), so analyses are the unit of
history and comparison.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ID_LENGTH, Base, JSONColumn, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.anomaly import Anomaly
    from app.models.finding import Finding
    from app.models.project import Project


class DatasetStatus(StrEnum):
    UPLOADED = "uploaded"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class AnalysisStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata for one uploaded file. The bytes live in the storage backend."""

    __tablename__ = "datasets"
    __table_args__ = (Index("ix_datasets_project_created", "project_id", "created_at"),)

    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Opaque key for the storage backend. Never a user-supplied path.
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Lets the UI point out that two "different" uploads are byte-identical.
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(DatasetStatus, native_enum=False, length=16, validate_strings=True),
        nullable=False,
        default=DatasetStatus.UPLOADED,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="datasets")
    analyses: Mapped[list[DatasetAnalysis]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DatasetAnalysis.created_at.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Dataset {self.name!r} status={self.status}>"


class DatasetAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One pipeline run: profile, quality checks, anomaly detection, score."""

    __tablename__ = "dataset_analyses"
    __table_args__ = (
        Index("ix_analyses_dataset_created", "dataset_id", "created_at"),
        Index("ix_analyses_project_created", "project_id", "created_at"),
    )

    dataset_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Denormalised from the dataset so project-wide history is a single-table
    #: query. Analyses are never moved between projects, so it cannot drift.
    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        Enum(AnalysisStatus, native_enum=False, length=16, validate_strings=True),
        nullable=False,
        default=AnalysisStatus.RUNNING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The full DatasetProfile document. Stored as JSONB on PostgreSQL.
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn, nullable=True)

    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_cell_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duplicate_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_row_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    #: The headline number, 0-100, with the full derivation beside it so the
    #: UI can always answer "why this score?" without recomputing anything.
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_grade: Mapped[str | None] = mapped_column(String(24), nullable=True)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn, nullable=True)

    #: Anomaly detection outcome. `ml_skipped_reason` is set when detection was
    #: deliberately not run — a normal outcome, not a failure.
    anomaly_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anomaly_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ml_algorithm: Mapped[str | None] = mapped_column(String(48), nullable=True)
    ml_features: Mapped[list[Any] | None] = mapped_column(JSONColumn, nullable=True)
    ml_parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn, nullable=True)
    ml_skipped_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Roll-up counts, denormalised from `findings` so the dashboard and the
    #: history list never need to aggregate the findings table.
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="analyses")
    findings: Mapped[list[Finding]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    anomalies: Mapped[list[Anomaly]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Anomaly.rank",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DatasetAnalysis {self.id} status={self.status}>"
