"""Finding vocabulary shared by every detector.

A *finding* is one concrete, reviewable problem. Every finding answers five
questions, and the field that answers each is named here so no detector can
quietly skip one:

===================== ==========================================
What happened?        ``title`` + ``description``
Where?                ``column`` / ``affected_rows``
Why does it matter?   ``impact``
How was it detected?  ``detection_method`` + ``details``
What should I do?     ``recommendation``
===================== ==========================================
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """How much the finding should worry you.

    Ordering matters: it drives sorting, the dashboard roll-up and the score
    penalty weights, so the numeric rank is defined here rather than being
    re-derived at each call site.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]

    @classmethod
    def from_rank(cls, rank: int) -> Severity:
        return _RANK_TO_SEVERITY[max(0, min(rank, 3))]


_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}
_RANK_TO_SEVERITY = {rank: severity for severity, rank in _SEVERITY_RANK.items()}


class FindingCategory(StrEnum):
    """The two kinds of thing Obseil reports, kept visibly separate.

    A ``rule`` finding is a *fact* about the data, derived deterministically.
    An ``anomaly`` is a *candidate* surfaced by an unsupervised model, which
    may be perfectly legitimate. Conflating the two would overstate what the
    model knows - see ``docs/METHODOLOGY.md``.
    """

    RULE = "rule"
    ANOMALY = "anomaly"


class FindingType(StrEnum):
    """The catalogue of detectable problems.

    Adding a member here is how a new detector becomes visible to the UI's
    filters. Keep the values stable: they are persisted.
    """

    MISSING_VALUES = "missing_values"
    EMPTY_COLUMN = "empty_column"
    INCOMPLETE_ROWS = "incomplete_rows"
    DUPLICATE_ROWS = "duplicate_rows"
    DUPLICATE_IDENTIFIER = "duplicate_identifier"
    CONSTANT_COLUMN = "constant_column"
    HIGH_CARDINALITY = "high_cardinality"
    OUTLIERS = "outliers"
    NEGATIVE_VALUES = "negative_values"
    INVALID_DATES = "invalid_dates"
    EMPTY_STRINGS = "empty_strings"
    WHITESPACE_PADDING = "whitespace_padding"
    NUMBERS_AS_TEXT = "numbers_as_text"
    ML_ANOMALY = "ml_anomaly"


class DetectionMethod(StrEnum):
    """How a finding was arrived at. Shown verbatim in the UI.

    Naming the method is not decoration: "12 outliers" means nothing until you
    know whether the threshold was 1.5x the IQR or 3 standard deviations.
    """

    NULL_COUNT = "null_count"
    ROW_COMPLETENESS = "row_completeness"
    EXACT_ROW_MATCH = "exact_row_match"
    UNIQUENESS_CHECK = "uniqueness_check"
    DISTINCT_COUNT = "distinct_count"
    CARDINALITY_RATIO = "cardinality_ratio"
    IQR = "iqr"
    Z_SCORE = "z_score"
    SIGN_CHECK = "sign_check"
    DATE_PARSING = "date_parsing"
    STRING_INSPECTION = "string_inspection"
    TYPE_INFERENCE = "type_inference"
    ISOLATION_FOREST = "isolation_forest"


#: Human-readable labels. Kept beside the enum so the API can send both the
#: stable machine value and the phrasing the UI should show.
DETECTION_METHOD_LABELS: dict[DetectionMethod, str] = {
    DetectionMethod.NULL_COUNT: "Null-value count",
    DetectionMethod.ROW_COMPLETENESS: "Per-row completeness",
    DetectionMethod.EXACT_ROW_MATCH: "Exact row comparison",
    DetectionMethod.UNIQUENESS_CHECK: "Uniqueness check",
    DetectionMethod.DISTINCT_COUNT: "Distinct-value count",
    DetectionMethod.CARDINALITY_RATIO: "Cardinality ratio",
    DetectionMethod.IQR: "Interquartile range (Tukey's fences)",
    DetectionMethod.Z_SCORE: "Z-score",
    DetectionMethod.SIGN_CHECK: "Sign check against the column's distribution",
    DetectionMethod.DATE_PARSING: "Date parsing",
    DetectionMethod.STRING_INSPECTION: "String inspection",
    DetectionMethod.TYPE_INFERENCE: "Type inference",
    DetectionMethod.ISOLATION_FOREST: "Isolation Forest (unsupervised ML)",
}


class FindingDraft(BaseModel):
    """A finding as produced by a detector, before it is persisted."""

    type: FindingType
    category: FindingCategory = FindingCategory.RULE
    severity: Severity
    title: str = Field(max_length=200, description="One line: what happened.")
    description: str = Field(description="The observation, with the numbers behind it.")
    impact: str = Field(description="Why this matters for anything built on the data.")
    recommendation: str = Field(description="The concrete next step.")
    detection_method: DetectionMethod

    column: str | None = None
    #: Several columns for dataset-level findings; empty for whole-dataset ones.
    columns: list[str] = Field(default_factory=list)
    affected_rows: int | None = None
    affected_percentage: float | None = None

    #: Method-specific evidence: thresholds, bounds, example values. Rendered
    #: in the finding detail so a reviewer can check the work.
    details: dict[str, Any] = Field(default_factory=dict)

    #: Row indices for the worst offenders, capped. Lets the UI jump straight
    #: to the data instead of leaving the user to hunt for it.
    sample_row_indices: list[int] = Field(default_factory=list)

    @property
    def sort_key(self) -> tuple[int, float]:
        """Most severe first, then by how much of the dataset is affected."""
        return (-self.severity.rank, -(self.affected_percentage or 0.0))
