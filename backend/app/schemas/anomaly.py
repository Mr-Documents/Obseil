"""Anomaly and quality-score contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.quality.scoring import QualityScore
from app.schemas.common import ORMModel


class AnomalyContributor(BaseModel):
    feature: str
    value: float | None
    #: Distance from the column's median, in interquartile ranges.
    deviation_iqr: float


class AnomalyRead(ORMModel):
    id: str
    analysis_id: str
    dataset_id: str
    row_index: int
    rank: int
    raw_score: float
    anomaly_score: float
    feature_values: dict[str, float | None] | None
    top_contributors: list[AnomalyContributor] | None


class AnomalyOverview(BaseModel):
    """Everything the anomalies view needs to explain itself.

    Deliberately verbose about method and limits: a 0-100 score with no context
    invites the reader to treat it as a probability, which it is not.
    """

    analysis_id: str
    ran: bool
    #: Present when detection was deliberately skipped — a normal outcome.
    skipped_reason: str | None = None
    algorithm: str | None = None
    features: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    rows_scored: int = 0
    anomaly_count: int = 0
    anomaly_rate: float = 0.0
    method_note: str = (
        "An Isolation Forest ranks rows by how easily they can be separated from the rest. "
        "The score is relative to this dataset only: it is not a probability, and it is not "
        "comparable with another dataset's scores. The model reports that a row is unusual; "
        "it does not know why."
    )


class QualityScoreRead(QualityScore):
    """The score, with the analysis it belongs to."""

    analysis_id: str
    dataset_id: str
    analysed_at: datetime | None = None
