"""Analysis history and comparison contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.dataset import AnalysisSummary


class MetricPolarity(StrEnum):
    """Which direction of change is an improvement.

    Explicit rather than inferred, because the answer differs per metric and
    guessing produces a UI that colours "more rows" green.
    """

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    NEUTRAL = "neutral"


class ComparisonDirection(StrEnum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    #: Moved, but in a direction that is neither good nor bad.
    CHANGED = "changed"


class MetricComparison(BaseModel):
    key: str
    label: str
    baseline: float | None
    current: float | None
    delta: float | None
    direction: ComparisonDirection
    polarity: MetricPolarity
    unit: str | None = None


class FindingTypeChange(BaseModel):
    type: str
    baseline_count: int
    current_count: int
    #: ``resolved`` | ``new`` | ``persisting``
    status: str


class AnalysisComparison(BaseModel):
    """Two analyses, side by side, with what changed and whether it is better."""

    baseline_id: str
    current_id: str
    baseline_at: datetime
    current_at: datetime
    baseline_score: float | None
    current_score: float | None
    score_delta: float | None
    headline: str

    metrics: list[MetricComparison] = Field(default_factory=list)
    dimensions: list[MetricComparison] = Field(default_factory=list)
    finding_types: list[FindingTypeChange] = Field(default_factory=list)
    resolved_types: list[str] = Field(default_factory=list)
    new_types: list[str] = Field(default_factory=list)


class HistoryEntry(AnalysisSummary):
    """An analysis in a history list, with enough context to identify it."""

    dataset_name: str
    dataset_row_count: int | None
    #: Position in the project's history, 1 = the first ever run.
    version: int
