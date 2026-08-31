"""Analysis history and comparison.

Comparison is where the product stops describing one file and starts telling
you whether things are getting better. The rules are deliberately explicit:

* The **baseline is always the older** of the two analyses, whichever order the
  caller passes them in. "Improved by 9" must never mean "got worse by 9"
  because of an argument order.
* Every metric declares **which direction is good**. Fewer missing values is an
  improvement; more rows is neither good nor bad, and saying so is more honest
  than colouring it green.
* Finding types are compared as **sets**, so the answer to "what did we
  actually fix?" is a list of names, not a smaller number.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.dataset import AnalysisStatus, Dataset, DatasetAnalysis
from app.models.finding import Finding
from app.models.project import Project
from app.models.user import User
from app.schemas.history import (
    AnalysisComparison,
    ComparisonDirection,
    FindingTypeChange,
    MetricComparison,
    MetricPolarity,
)

logger = logging.getLogger(__name__)


def list_project_history(
    db: Session, *, project: Project, limit: int, offset: int
) -> tuple[list[DatasetAnalysis], int]:
    """Completed analyses across a project, newest first."""
    condition = (
        DatasetAnalysis.project_id == project.id,
        DatasetAnalysis.status == AnalysisStatus.COMPLETED,
    )
    total = db.scalar(select(func.count()).select_from(DatasetAnalysis).where(*condition)) or 0
    rows = db.scalars(
        select(DatasetAnalysis)
        .where(*condition)
        .order_by(DatasetAnalysis.created_at.desc(), DatasetAnalysis.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def list_dataset_history(
    db: Session, *, dataset: Dataset, limit: int, offset: int
) -> tuple[list[DatasetAnalysis], int]:
    """Every run for one dataset, newest first, including failures.

    Failures are included on purpose: a history that silently omits them would
    misrepresent what happened.
    """
    total = (
        db.scalar(
            select(func.count())
            .select_from(DatasetAnalysis)
            .where(DatasetAnalysis.dataset_id == dataset.id)
        )
        or 0
    )
    rows = db.scalars(
        select(DatasetAnalysis)
        .where(DatasetAnalysis.dataset_id == dataset.id)
        .order_by(DatasetAnalysis.created_at.desc(), DatasetAnalysis.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_owned_analysis(db: Session, *, analysis_id: str, user: User) -> DatasetAnalysis:
    analysis = db.scalar(
        select(DatasetAnalysis)
        .join(Project, Project.id == DatasetAnalysis.project_id)
        .where(DatasetAnalysis.id == analysis_id, Project.owner_id == user.id)
    )
    if analysis is None:
        raise NotFoundError("That analysis does not exist, or you do not have access to it.")
    return analysis


def previous_analysis(db: Session, *, analysis: DatasetAnalysis) -> DatasetAnalysis | None:
    """The completed run immediately before ``analysis`` in the same project.

    Project-scoped rather than dataset-scoped: the interesting comparison is
    usually "this month's export against last month's", and those are two
    different datasets.
    """
    return db.scalar(
        select(DatasetAnalysis)
        .where(
            DatasetAnalysis.project_id == analysis.project_id,
            DatasetAnalysis.status == AnalysisStatus.COMPLETED,
            DatasetAnalysis.id != analysis.id,
            DatasetAnalysis.created_at <= analysis.created_at,
        )
        .order_by(DatasetAnalysis.created_at.desc(), DatasetAnalysis.id.desc())
        .limit(1)
    )


def finding_types(db: Session, analysis_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Finding.type, func.count(Finding.id))
        .where(Finding.analysis_id == analysis_id)
        .group_by(Finding.type)
    ).all()
    return {str(finding_type): int(count) for finding_type, count in rows}


def _metric(
    label: str,
    key: str,
    baseline: float | None,
    current: float | None,
    polarity: MetricPolarity,
    unit: str | None = None,
) -> MetricComparison:
    """Build one comparison row, resolving what the change *means*."""
    delta: float | None = None
    if baseline is not None and current is not None:
        delta = round(current - baseline, 4)

    if delta is None or abs(delta) < 1e-9:
        direction = ComparisonDirection.UNCHANGED
    elif polarity is MetricPolarity.NEUTRAL:
        direction = ComparisonDirection.CHANGED
    elif (delta > 0) is (polarity is MetricPolarity.HIGHER_IS_BETTER):
        direction = ComparisonDirection.IMPROVED
    else:
        direction = ComparisonDirection.REGRESSED

    return MetricComparison(
        key=key,
        label=label,
        baseline=baseline,
        current=current,
        delta=delta,
        direction=direction,
        polarity=polarity,
        unit=unit,
    )


def compare_analyses(
    db: Session, *, first: DatasetAnalysis, second: DatasetAnalysis
) -> AnalysisComparison:
    """Compare two analyses, oldest as the baseline regardless of argument order."""
    if first.id == second.id:
        raise ValidationError("Pick two different analyses to compare.")
    if first.project_id != second.project_id:
        raise ValidationError("Analyses can only be compared within the same project.")

    baseline, current = (
        (first, second) if first.created_at <= second.created_at else (second, first)
    )

    metrics = [
        _metric(
            "Quality score",
            "quality_score",
            baseline.quality_score,
            current.quality_score,
            MetricPolarity.HIGHER_IS_BETTER,
            unit="/100",
        ),
        _metric(
            "Total findings",
            "finding_count",
            baseline.finding_count,
            current.finding_count,
            MetricPolarity.LOWER_IS_BETTER,
        ),
        _metric(
            "Critical findings",
            "critical_count",
            baseline.critical_count,
            current.critical_count,
            MetricPolarity.LOWER_IS_BETTER,
        ),
        _metric(
            "High findings",
            "high_count",
            baseline.high_count,
            current.high_count,
            MetricPolarity.LOWER_IS_BETTER,
        ),
        _metric(
            "Medium findings",
            "medium_count",
            baseline.medium_count,
            current.medium_count,
            MetricPolarity.LOWER_IS_BETTER,
        ),
        _metric(
            "Low findings",
            "low_count",
            baseline.low_count,
            current.low_count,
            MetricPolarity.LOWER_IS_BETTER,
        ),
        _metric(
            "Missing values",
            "missing_percentage",
            baseline.missing_percentage,
            current.missing_percentage,
            MetricPolarity.LOWER_IS_BETTER,
            unit="%",
        ),
        _metric(
            "Duplicate rows",
            "duplicate_row_percentage",
            baseline.duplicate_row_percentage,
            current.duplicate_row_percentage,
            MetricPolarity.LOWER_IS_BETTER,
            unit="%",
        ),
        _metric(
            "Anomalous rows",
            "anomaly_count",
            baseline.anomaly_count,
            current.anomaly_count,
            MetricPolarity.LOWER_IS_BETTER,
        ),
        # Shape changes are information, not progress: more rows is neither
        # good nor bad, and colouring it green would be a lie.
        _metric("Rows", "row_count", baseline.row_count, current.row_count, MetricPolarity.NEUTRAL),
        _metric(
            "Columns",
            "column_count",
            baseline.column_count,
            current.column_count,
            MetricPolarity.NEUTRAL,
        ),
    ]

    before = finding_types(db, baseline.id)
    after = finding_types(db, current.id)
    changes = [
        FindingTypeChange(
            type=finding_type,
            baseline_count=before.get(finding_type, 0),
            current_count=after.get(finding_type, 0),
            status=(
                "resolved"
                if finding_type not in after
                else "new" if finding_type not in before else "persisting"
            ),
        )
        for finding_type in sorted(set(before) | set(after))
    ]

    score_delta = None
    if baseline.quality_score is not None and current.quality_score is not None:
        score_delta = round(current.quality_score - baseline.quality_score, 1)

    logger.info(
        "Compared analyses",
        extra={"baseline": baseline.id, "current": current.id, "score_delta": score_delta},
    )
    return AnalysisComparison(
        baseline_id=baseline.id,
        current_id=current.id,
        baseline_at=baseline.completed_at or baseline.created_at,
        current_at=current.completed_at or current.created_at,
        baseline_score=baseline.quality_score,
        current_score=current.quality_score,
        score_delta=score_delta,
        headline=_headline(score_delta),
        metrics=metrics,
        dimensions=_dimension_deltas(baseline, current),
        finding_types=changes,
        resolved_types=[change.type for change in changes if change.status == "resolved"],
        new_types=[change.type for change in changes if change.status == "new"],
    )


def _headline(score_delta: float | None) -> str:
    if score_delta is None:
        return "One of these analyses has no quality score, so they cannot be compared directly."
    if score_delta > 0:
        return f"Quality improved by {score_delta:+.1f} points."
    if score_delta < 0:
        return f"Quality fell by {abs(score_delta):.1f} points."
    return "The quality score is unchanged."


def _dimension_deltas(
    baseline: DatasetAnalysis, current: DatasetAnalysis
) -> list[MetricComparison]:
    """Per-dimension penalty change, read out of each run's stored breakdown."""

    def penalties(analysis: DatasetAnalysis) -> dict[str, tuple[str, float]]:
        breakdown: dict[str, Any] = analysis.score_breakdown or {}
        dimensions: list[dict[str, Any]] = breakdown.get("dimensions", [])
        return {
            str(entry.get("dimension")): (
                str(entry.get("label") or entry.get("dimension")),
                float(entry.get("penalty") or 0.0),
            )
            for entry in dimensions
        }

    before, after = penalties(baseline), penalties(current)
    return [
        _metric(
            after.get(key, before.get(key, (key, 0.0)))[0],
            key,
            before.get(key, ("", 0.0))[1] if key in before else None,
            after.get(key, ("", 0.0))[1] if key in after else None,
            # A penalty going down is an improvement.
            MetricPolarity.LOWER_IS_BETTER,
            unit="pts",
        )
        for key in sorted(set(before) | set(after))
    ]
