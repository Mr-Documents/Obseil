"""Anomalous rows surfaced by the ML detector.

Stored separately from findings on purpose. A finding is one reviewable
statement ("14 rows look unusual"); these are the rows behind it. Keeping them
apart stops a hundred individual anomalies from burying the deterministic
findings that state actual facts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ID_LENGTH, Base, JSONColumn, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.dataset import DatasetAnalysis


class Anomaly(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        # The anomalies view is always "this analysis, worst first".
        Index("ix_anomalies_analysis_rank", "analysis_id", "rank"),
    )

    analysis_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("dataset_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #: Positional index into the analysed frame, matching the row explorer.
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 0 = the most unusual row in this analysis.
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Model-native score. Algorithm-specific; kept for reproducibility.
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    #: 0-100 rescaled within this dataset. Not a probability, and not
    #: comparable across datasets.
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)

    #: The feature values the model actually saw for this row.
    feature_values: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn, nullable=True)
    #: Which of those values sit furthest from their column's centre.
    #: Descriptive, not an attribution of the model's decision.
    top_contributors: Mapped[list[Any] | None] = mapped_column(JSONColumn, nullable=True)

    analysis: Mapped[DatasetAnalysis] = relationship(back_populates="anomalies")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Anomaly row={self.row_index} score={self.anomaly_score}>"
