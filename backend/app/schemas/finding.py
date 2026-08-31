"""Finding contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, computed_field

from app.models.finding import FeedbackVerdict, FindingStatus
from app.quality.types import DETECTION_METHOD_LABELS, DetectionMethod
from app.schemas.common import ORMModel


class FindingFeedbackRead(ORMModel):
    verdict: FeedbackVerdict
    note: str | None
    created_at: datetime


class FindingRead(ORMModel):
    """One finding, with everything the UI needs to explain it.

    The five questions a finding must answer map to fields directly:
    ``title``/``description`` (what), ``column``/``affected_rows`` (where),
    ``impact`` (why it matters), ``detection_method`` (how it was found) and
    ``recommendation`` (what to do).
    """

    id: str
    analysis_id: str
    dataset_id: str
    type: str
    category: str
    severity: str
    title: str
    description: str
    impact: str
    recommendation: str
    detection_method: str
    column_name: str | None
    columns: list[str] | None
    affected_rows: int | None
    affected_percentage: float | None
    details: dict[str, Any] | None
    sample_row_indices: list[int] | None
    status: FindingStatus
    created_at: datetime
    feedback: FindingFeedbackRead | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def detection_method_label(self) -> str:
        """Readable name for the method, so the UI never renders a raw enum."""
        try:
            return DETECTION_METHOD_LABELS[DetectionMethod(self.detection_method)]
        except ValueError:
            return self.detection_method.replace("_", " ").capitalize()


class FindingUpdate(BaseModel):
    """Triage a finding. Every field is optional; at least one is required."""

    status: FindingStatus | None = None
    verdict: FeedbackVerdict | None = None
    note: Annotated[str | None, Field(max_length=2000)] = None

    def is_empty(self) -> bool:
        return self.status is None and self.verdict is None


class FindingSummary(BaseModel):
    """Roll-up for the dashboard."""

    analysis_id: str
    total: int
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    open_count: int = 0
    reviewed_count: int = 0
    ignored_count: int = 0
    false_positive_count: int = 0
