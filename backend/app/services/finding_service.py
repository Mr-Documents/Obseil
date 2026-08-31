"""Finding persistence, triage and feedback."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.models.dataset import Dataset, DatasetAnalysis
from app.models.finding import FeedbackVerdict, Finding, FindingFeedback, FindingStatus
from app.models.project import Project
from app.models.user import User
from app.quality.types import FindingDraft, Severity

logger = logging.getLogger(__name__)


def persist_findings(
    db: Session, *, analysis: DatasetAnalysis, drafts: Sequence[FindingDraft]
) -> list[Finding]:
    """Write a run's findings and update the analysis roll-up counts.

    Findings are always created fresh for the analysis that produced them.
    Carrying a previous run's findings forward would make the history claim
    that a run saw something it did not.
    """
    findings = [
        Finding(
            analysis_id=analysis.id,
            dataset_id=analysis.dataset_id,
            project_id=analysis.project_id,
            type=draft.type.value,
            category=draft.category.value,
            severity=draft.severity.value,
            severity_rank=draft.severity.rank,
            title=draft.title,
            description=draft.description,
            impact=draft.impact,
            recommendation=draft.recommendation,
            detection_method=draft.detection_method.value,
            column_name=draft.column,
            columns=draft.columns or None,
            affected_rows=draft.affected_rows,
            affected_percentage=draft.affected_percentage,
            details=draft.details or None,
            sample_row_indices=draft.sample_row_indices or None,
            status=FindingStatus.OPEN,
        )
        for draft in drafts
    ]
    db.add_all(findings)

    counts = dict.fromkeys(Severity, 0)
    for draft in drafts:
        counts[draft.severity] += 1

    analysis.finding_count = len(drafts)
    analysis.critical_count = counts[Severity.CRITICAL]
    analysis.high_count = counts[Severity.HIGH]
    analysis.medium_count = counts[Severity.MEDIUM]
    analysis.low_count = counts[Severity.LOW]

    logger.info(
        "Persisted findings",
        extra={"analysis_id": analysis.id, "count": len(findings)},
    )
    return findings


def get_owned_finding(db: Session, *, finding_id: str, user: User) -> Finding:
    """Fetch a finding the user owns, via its project."""
    finding = db.scalar(
        select(Finding)
        .options(selectinload(Finding.feedback))
        .join(Project, Project.id == Finding.project_id)
        .where(Finding.id == finding_id, Project.owner_id == user.id)
    )
    if finding is None:
        raise NotFoundError("That finding does not exist, or you do not have access to it.")
    return finding


def _base_query(analysis_id: str) -> Select[tuple[Finding]]:
    return select(Finding).where(Finding.analysis_id == analysis_id)


def _apply_filters(
    statement: Select[tuple[Finding]],
    *,
    severities: Sequence[str] | None,
    types: Sequence[str] | None,
    statuses: Sequence[str] | None,
    categories: Sequence[str] | None,
    search: str | None,
) -> Select[tuple[Finding]]:
    if severities:
        statement = statement.where(Finding.severity.in_(severities))
    if types:
        statement = statement.where(Finding.type.in_(types))
    if statuses:
        statement = statement.where(Finding.status.in_(statuses))
    if categories:
        statement = statement.where(Finding.category.in_(categories))
    if search:
        # Case-insensitive substring across the fields a person would search:
        # the headline, the narrative, and the column it concerns.
        pattern = f"%{search.strip().lower()}%"
        statement = statement.where(
            func.lower(Finding.title).like(pattern)
            | func.lower(Finding.description).like(pattern)
            | func.lower(func.coalesce(Finding.column_name, "")).like(pattern)
        )
    return statement


def list_findings(
    db: Session,
    *,
    analysis: DatasetAnalysis,
    limit: int,
    offset: int,
    severities: Sequence[str] | None = None,
    types: Sequence[str] | None = None,
    statuses: Sequence[str] | None = None,
    categories: Sequence[str] | None = None,
    search: str | None = None,
) -> tuple[list[Finding], int]:
    """Filtered, paginated findings for one analysis, most severe first."""
    statement = _apply_filters(
        _base_query(analysis.id),
        severities=severities,
        types=types,
        statuses=statuses,
        categories=categories,
        search=search,
    )

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.options(selectinload(Finding.feedback))
        .order_by(
            Finding.severity_rank.desc(),
            Finding.affected_percentage.desc().nullslast(),
            Finding.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def severity_breakdown(db: Session, *, analysis: DatasetAnalysis) -> dict[str, int]:
    """Counts per severity for one analysis, including zeros."""
    rows = db.execute(
        select(Finding.severity, func.count(Finding.id))
        .where(Finding.analysis_id == analysis.id)
        .group_by(Finding.severity)
    ).all()
    counts = {severity.value: 0 for severity in Severity}
    for severity, count in rows:
        counts[str(severity)] = int(count)
    return counts


def type_breakdown(db: Session, *, analysis: DatasetAnalysis) -> dict[str, int]:
    rows = db.execute(
        select(Finding.type, func.count(Finding.id))
        .where(Finding.analysis_id == analysis.id)
        .group_by(Finding.type)
        .order_by(func.count(Finding.id).desc())
    ).all()
    return {str(finding_type): int(count) for finding_type, count in rows}


def update_finding(
    db: Session,
    *,
    finding: Finding,
    user: User,
    status: FindingStatus | None = None,
    verdict: FeedbackVerdict | None = None,
    note: str | None = None,
) -> Finding:
    """Triage a finding: change its status, record a verdict, or both.

    A verdict of *false positive* also moves the finding to ``ignored`` unless
    the caller asked for something else. Saying "this detector was wrong" and
    then leaving the finding open in the queue would be a pointless second step.
    """
    if verdict is not None:
        existing = finding.feedback
        if existing is None:
            db.add(
                FindingFeedback(
                    finding_id=finding.id,
                    user_id=user.id,
                    verdict=verdict,
                    note=note,
                )
            )
        else:
            existing.verdict = verdict
            if note is not None:
                existing.note = note

        if status is None:
            status = (
                FindingStatus.IGNORED
                if verdict is FeedbackVerdict.FALSE_POSITIVE
                else FindingStatus.REVIEWED
            )

    if status is not None:
        finding.status = status

    db.commit()
    db.refresh(finding)
    logger.info(
        "Finding triaged",
        extra={"finding_id": finding.id, "status": finding.status, "verdict": verdict},
    )
    return finding


def open_finding_count(db: Session, *, dataset: Dataset) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Finding)
            .where(Finding.dataset_id == dataset.id, Finding.status == FindingStatus.OPEN)
        )
        or 0
    )
