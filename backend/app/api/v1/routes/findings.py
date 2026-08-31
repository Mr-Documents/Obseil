"""Finding listing, detail and triage endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.errors import NotFoundError, ValidationError
from app.models.dataset import AnalysisStatus, DatasetAnalysis
from app.models.finding import Finding, FindingFeedback, FindingStatus
from app.schemas.common import Page
from app.schemas.finding import FindingRead, FindingSummary, FindingUpdate
from app.services import dataset_service, finding_service

router = APIRouter(tags=["findings"])

#: Filters accept repeated query parameters, e.g. ?severity=high&severity=critical
SeverityFilter = Annotated[list[str] | None, Query(alias="severity")]
TypeFilter = Annotated[list[str] | None, Query(alias="type")]
StatusFilter = Annotated[list[str] | None, Query(alias="status")]
CategoryFilter = Annotated[list[str] | None, Query(alias="category")]


def _require_completed_analysis(
    db: DbSession, dataset_id: str, user: CurrentUser
) -> DatasetAnalysis:
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    dataset_service.require_ready(dataset)

    analysis = dataset_service.latest_analysis(db, dataset=dataset)
    if analysis is None or analysis.status != AnalysisStatus.COMPLETED:
        raise NotFoundError(
            "This dataset has not been analysed yet. Run an analysis to see its findings.",
            code="analysis_missing",
        )
    return analysis


@router.get(
    "/datasets/{dataset_id}/findings",
    response_model=Page[FindingRead],
    summary="Findings from a dataset's latest analysis",
)
def list_findings(
    dataset_id: str,
    db: DbSession,
    user: CurrentUser,
    page: Pagination,
    severity: SeverityFilter = None,
    # Shadows the builtin deliberately: the public query parameter is `type`.
    type: TypeFilter = None,
    status: StatusFilter = None,
    category: CategoryFilter = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[FindingRead]:
    analysis = _require_completed_analysis(db, dataset_id, user)

    findings, total = finding_service.list_findings(
        db,
        analysis=analysis,
        limit=page.limit,
        offset=page.offset,
        severities=severity,
        types=type,
        statuses=status,
        categories=category,
        search=search,
    )
    return Page[FindingRead](
        items=[FindingRead.model_validate(finding) for finding in findings],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/datasets/{dataset_id}/findings/summary",
    response_model=FindingSummary,
    summary="Finding counts for the dashboard",
)
def findings_summary(dataset_id: str, db: DbSession, user: CurrentUser) -> FindingSummary:
    analysis = _require_completed_analysis(db, dataset_id, user)

    status_rows = db.execute(
        select(Finding.status, func.count(Finding.id))
        .where(Finding.analysis_id == analysis.id)
        .group_by(Finding.status)
    ).all()
    by_status = {str(status): int(count) for status, count in status_rows}

    false_positives = (
        db.scalar(
            select(func.count())
            .select_from(FindingFeedback)
            .join(Finding, Finding.id == FindingFeedback.finding_id)
            .where(
                Finding.analysis_id == analysis.id,
                FindingFeedback.verdict == "false_positive",
            )
        )
        or 0
    )

    return FindingSummary(
        analysis_id=analysis.id,
        total=analysis.finding_count,
        by_severity=finding_service.severity_breakdown(db, analysis=analysis),
        by_type=finding_service.type_breakdown(db, analysis=analysis),
        open_count=by_status.get(FindingStatus.OPEN.value, 0),
        reviewed_count=by_status.get(FindingStatus.REVIEWED.value, 0),
        ignored_count=by_status.get(FindingStatus.IGNORED.value, 0),
        false_positive_count=false_positives,
    )


@router.get("/findings/{finding_id}", response_model=FindingRead, summary="Get a finding")
def get_finding(finding_id: str, db: DbSession, user: CurrentUser) -> FindingRead:
    return FindingRead.model_validate(
        finding_service.get_owned_finding(db, finding_id=finding_id, user=user)
    )


@router.patch(
    "/findings/{finding_id}",
    response_model=FindingRead,
    summary="Triage a finding",
    description=(
        "Mark a finding reviewed or ignored, and/or record whether the detector was "
        "right. A verdict of `false_positive` also moves the finding to `ignored` "
        "unless an explicit status is supplied."
    ),
)
def update_finding(
    finding_id: str, payload: FindingUpdate, db: DbSession, user: CurrentUser
) -> FindingRead:
    if payload.is_empty():
        raise ValidationError("Provide a status, a verdict, or both.")

    finding = finding_service.get_owned_finding(db, finding_id=finding_id, user=user)
    updated = finding_service.update_finding(
        db,
        finding=finding,
        user=user,
        status=payload.status,
        verdict=payload.verdict,
        note=payload.note,
    )
    return FindingRead.model_validate(updated)
