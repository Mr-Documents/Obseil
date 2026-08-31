"""The Obseil quality score.

A single 0-100 number that you can argue with.

The score is **not** a model output and not a magic constant. It is a
transparent penalty sum: every finding costs points, the cost is
``severity weight x how much of the dataset it affects``, and each quality
dimension has a ceiling so no one category can dominate. Every term is returned
alongside the number, so the UI can show precisely why a dataset scored what it
scored - and so a user who disagrees can point at the specific line they
disagree with.

    score = 100 - sum over dimensions of min(dimension penalty, dimension cap)

Design decisions worth stating:

* **Severity dominates, coverage modulates.** A critical finding affecting 5%
  of rows should outrank a low finding affecting all of them. The coverage
  multiplier therefore spans only 0.5x to 1.5x - enough to distinguish "one bad
  row" from "the whole column", not enough to let a trivial issue outweigh a
  serious one.
* **Dimensions are capped.** A file with forty partially-empty columns is bad,
  but it is not forty times worse than one with four, and without a ceiling the
  score would saturate at zero and stop discriminating between bad and awful.
* **Caps sum to 120, not 100.** A dataset that is genuinely broken in every
  dimension can reach zero. If the caps summed to 100, nothing ever could.
* **ML anomalies are weighted lightest.** They are candidates for review, not
  established defects, and the score should not punish a dataset for having
  rows a model found interesting.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.quality.types import FindingDraft, FindingType, Severity

# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

#: Points a finding costs at full coverage, before the dimension cap.
SEVERITY_WEIGHTS: dict[Severity, float] = {
    Severity.CRITICAL: 30.0,
    Severity.HIGH: 18.0,
    Severity.MEDIUM: 8.0,
    Severity.LOW: 2.0,
}

#: Coverage multiplier bounds. A finding with no meaningful row count (a
#: constant column, say) is treated as mid-range.
MIN_COVERAGE_MULTIPLIER = 0.5
MAX_COVERAGE_MULTIPLIER = 1.5
DEFAULT_COVERAGE_MULTIPLIER = 1.0


class QualityDimension(StrEnum):
    """The axes a dataset is judged on."""

    COMPLETENESS = "completeness"
    UNIQUENESS = "uniqueness"
    VALIDITY = "validity"
    CONSISTENCY = "consistency"
    DISTRIBUTION = "distribution"
    ANOMALY = "anomaly"


#: Maximum points any single dimension can remove.
DIMENSION_CAPS: dict[QualityDimension, float] = {
    QualityDimension.COMPLETENESS: 35.0,
    QualityDimension.UNIQUENESS: 25.0,
    QualityDimension.VALIDITY: 25.0,
    QualityDimension.CONSISTENCY: 10.0,
    QualityDimension.DISTRIBUTION: 15.0,
    QualityDimension.ANOMALY: 10.0,
}

DIMENSION_LABELS: dict[QualityDimension, str] = {
    QualityDimension.COMPLETENESS: "Completeness",
    QualityDimension.UNIQUENESS: "Uniqueness",
    QualityDimension.VALIDITY: "Validity",
    QualityDimension.CONSISTENCY: "Consistency",
    QualityDimension.DISTRIBUTION: "Distribution",
    QualityDimension.ANOMALY: "Anomalies",
}

FINDING_DIMENSIONS: dict[FindingType, QualityDimension] = {
    FindingType.MISSING_VALUES: QualityDimension.COMPLETENESS,
    FindingType.EMPTY_COLUMN: QualityDimension.COMPLETENESS,
    FindingType.INCOMPLETE_ROWS: QualityDimension.COMPLETENESS,
    FindingType.DUPLICATE_ROWS: QualityDimension.UNIQUENESS,
    FindingType.DUPLICATE_IDENTIFIER: QualityDimension.UNIQUENESS,
    FindingType.NEGATIVE_VALUES: QualityDimension.VALIDITY,
    FindingType.INVALID_DATES: QualityDimension.VALIDITY,
    FindingType.EMPTY_STRINGS: QualityDimension.VALIDITY,
    FindingType.CONSTANT_COLUMN: QualityDimension.CONSISTENCY,
    FindingType.HIGH_CARDINALITY: QualityDimension.CONSISTENCY,
    FindingType.NUMBERS_AS_TEXT: QualityDimension.CONSISTENCY,
    FindingType.WHITESPACE_PADDING: QualityDimension.CONSISTENCY,
    FindingType.OUTLIERS: QualityDimension.DISTRIBUTION,
    FindingType.ML_ANOMALY: QualityDimension.ANOMALY,
}


class QualityGrade(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    NEEDS_ATTENTION = "needs_attention"
    POOR = "poor"
    CRITICAL = "critical"


#: Lower bound of each grade, highest first.
GRADE_BANDS: tuple[tuple[float, QualityGrade], ...] = (
    (95.0, QualityGrade.EXCELLENT),
    (80.0, QualityGrade.GOOD),
    (60.0, QualityGrade.NEEDS_ATTENTION),
    (40.0, QualityGrade.POOR),
    (0.0, QualityGrade.CRITICAL),
)

GRADE_LABELS: dict[QualityGrade, str] = {
    QualityGrade.EXCELLENT: "Excellent",
    QualityGrade.GOOD: "Good",
    QualityGrade.NEEDS_ATTENTION: "Needs attention",
    QualityGrade.POOR: "Poor",
    QualityGrade.CRITICAL: "Critical",
}

GRADE_SUMMARIES: dict[QualityGrade, str] = {
    QualityGrade.EXCELLENT: "No material problems were found. This dataset is safe to build on.",
    QualityGrade.GOOD: (
        "A few issues worth knowing about, none of which should change your conclusions."
    ),
    QualityGrade.NEEDS_ATTENTION: (
        "Real problems that will affect analysis. Review the findings before relying on this data."
    ),
    QualityGrade.POOR: (
        "Serious, widespread problems. Results built on this dataset are likely to be wrong."
    ),
    QualityGrade.CRITICAL: (
        "This dataset is not usable as it stands. Fix the source before analysing it."
    ),
}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
class DimensionScore(BaseModel):
    """One dimension's contribution to the score."""

    dimension: QualityDimension
    label: str
    #: Points actually removed, after the cap.
    penalty: float
    #: Points the findings would have removed without the cap.
    raw_penalty: float
    cap: float
    capped: bool
    finding_count: int


class ScoreContribution(BaseModel):
    """The cost of one individual finding, for the "why this score" view."""

    finding_type: str
    severity: Severity
    column: str | None
    penalty: float
    affected_percentage: float | None


class QualityScore(BaseModel):
    """The score plus every term that produced it."""

    score: float = Field(ge=0, le=100)
    grade: QualityGrade
    grade_label: str
    summary: str
    total_penalty: float
    dimensions: list[DimensionScore] = Field(default_factory=list)
    #: Individual findings, most expensive first, so the UI can show the top
    #: reasons without recomputing anything.
    top_contributors: list[ScoreContribution] = Field(default_factory=list)
    methodology: str = (
        "Every dataset starts at 100. Each finding removes "
        "severity weight x coverage, and each quality dimension has a ceiling so that no "
        "single category can dominate the result."
    )


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------
def coverage_multiplier(affected_percentage: float | None) -> float:
    """Scale a finding's cost by how much of the dataset it touches."""
    if affected_percentage is None:
        return DEFAULT_COVERAGE_MULTIPLIER
    share = max(0.0, min(affected_percentage, 100.0)) / 100.0
    return MIN_COVERAGE_MULTIPLIER + share * (MAX_COVERAGE_MULTIPLIER - MIN_COVERAGE_MULTIPLIER)


def finding_penalty(finding: FindingDraft) -> float:
    """Points one finding removes, before its dimension's cap is applied."""
    weight = SEVERITY_WEIGHTS[finding.severity]
    return round(weight * coverage_multiplier(finding.affected_percentage), 4)


def grade_for(score: float) -> QualityGrade:
    for threshold, grade in GRADE_BANDS:
        if score >= threshold:
            return grade
    return QualityGrade.CRITICAL


def calculate_quality_score(findings: list[FindingDraft]) -> QualityScore:
    """Compute the score for a set of findings, with its full derivation."""
    raw_penalties = dict.fromkeys(QualityDimension, 0.0)
    counts = dict.fromkeys(QualityDimension, 0)
    contributions: list[ScoreContribution] = []

    for finding in findings:
        dimension = FINDING_DIMENSIONS.get(finding.type, QualityDimension.VALIDITY)
        penalty = finding_penalty(finding)
        raw_penalties[dimension] += penalty
        counts[dimension] += 1
        contributions.append(
            ScoreContribution(
                finding_type=finding.type.value,
                severity=finding.severity,
                column=finding.column,
                penalty=penalty,
                affected_percentage=finding.affected_percentage,
            )
        )

    dimensions: list[DimensionScore] = []
    total_penalty = 0.0
    for dimension in QualityDimension:
        raw = round(raw_penalties[dimension], 4)
        cap = DIMENSION_CAPS[dimension]
        applied = min(raw, cap)
        total_penalty += applied
        dimensions.append(
            DimensionScore(
                dimension=dimension,
                label=DIMENSION_LABELS[dimension],
                penalty=round(applied, 2),
                raw_penalty=raw,
                cap=cap,
                capped=raw > cap,
                finding_count=counts[dimension],
            )
        )

    score = round(max(0.0, min(100.0, 100.0 - total_penalty)), 1)
    grade = grade_for(score)

    contributions.sort(key=lambda item: -item.penalty)

    return QualityScore(
        score=score,
        grade=grade,
        grade_label=GRADE_LABELS[grade],
        summary=GRADE_SUMMARIES[grade],
        total_penalty=round(total_penalty, 2),
        dimensions=dimensions,
        top_contributors=contributions[:8],
    )
