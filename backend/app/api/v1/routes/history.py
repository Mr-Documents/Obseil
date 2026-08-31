"""Analysis history and comparison endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, OwnedProject, Pagination
from app.core.errors import NotFoundError
from app.models.dataset import AnalysisStatus, Dataset, DatasetAnalysis
from app.schemas.common import Page
from app.schemas.dataset import AnalysisSummary
from app.schemas.history import AnalysisComparison, HistoryEntry
from app.services import dataset_service, history_service

router = APIRouter(tags=["history"])


def _to_entries(db: DbSession, analyses: list[DatasetAnalysis]) -> list[HistoryEntry]:
    """Attach the dataset name and a per-project version number to each run.

    The version is computed with one grouped query rather than one query per
    row: a project with two hundred analyses should not cost two hundred
    round trips to render its history.
    """
    if not analyses:
        return []

    dataset_ids = {analysis.dataset_id for analysis in analyses}
    datasets = {
        dataset.id: dataset
        for dataset in db.scalars(select(Dataset).where(Dataset.id.in_(dataset_ids))).all()
    }

    project_ids = {analysis.project_id for analysis in analyses}
    ordered = db.execute(
        select(DatasetAnalysis.id, DatasetAnalysis.project_id, DatasetAnalysis.created_at)
        .where(
            DatasetAnalysis.project_id.in_(project_ids),
            DatasetAnalysis.status == AnalysisStatus.COMPLETED,
        )
        .order_by(DatasetAnalysis.project_id, DatasetAnalysis.created_at, DatasetAnalysis.id)
    ).all()

    versions: dict[str, int] = {}
    counters: dict[str, int] = {}
    for analysis_id, project_id, _ in ordered:
        counters[project_id] = counters.get(project_id, 0) + 1
        versions[str(analysis_id)] = counters[project_id]

    return [
        HistoryEntry(
            **AnalysisSummary.model_validate(analysis).model_dump(),
            dataset_name=(
                datasets[analysis.dataset_id].name
                if analysis.dataset_id in datasets
                else "(deleted)"
            ),
            dataset_row_count=(
                datasets[analysis.dataset_id].row_count if analysis.dataset_id in datasets else None
            ),
            version=versions.get(analysis.id, 0),
        )
        for analysis in analyses
    ]


@router.get(
    "/projects/{project_id}/history",
    response_model=Page[HistoryEntry],
    summary="Completed analyses across a project, newest first",
)
def project_history(project: OwnedProject, db: DbSession, page: Pagination) -> Page[HistoryEntry]:
    analyses, total = history_service.list_project_history(
        db, project=project, limit=page.limit, offset=page.offset
    )
    return Page[HistoryEntry](
        items=_to_entries(db, analyses), total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    "/datasets/{dataset_id}/history",
    response_model=Page[HistoryEntry],
    summary="Every run for one dataset, newest first",
)
def dataset_history(
    dataset_id: str, db: DbSession, user: CurrentUser, page: Pagination
) -> Page[HistoryEntry]:
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    analyses, total = history_service.list_dataset_history(
        db, dataset=dataset, limit=page.limit, offset=page.offset
    )
    return Page[HistoryEntry](
        items=_to_entries(db, analyses), total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    "/analyses/{analysis_id}/compare",
    response_model=AnalysisComparison,
    summary="Compare an analysis with another, or with the one before it",
    description=(
        "Without `baseline`, the analysis is compared with the previous completed run in "
        "the same project. The older of the two is always the baseline, whichever order "
        "they are given in."
    ),
)
def compare(
    analysis_id: str,
    db: DbSession,
    user: CurrentUser,
    baseline: Annotated[str | None, Query(description="Analysis id to compare against.")] = None,
) -> AnalysisComparison:
    current = history_service.get_owned_analysis(db, analysis_id=analysis_id, user=user)

    if baseline:
        other: DatasetAnalysis | None = history_service.get_owned_analysis(
            db, analysis_id=baseline, user=user
        )
    else:
        other = history_service.previous_analysis(db, analysis=current)

    if other is None:
        raise NotFoundError(
            "There is no earlier analysis in this project to compare against.",
            code="no_baseline",
        )

    return history_service.compare_analyses(db, first=other, second=current)


@router.get(
    "/projects/{project_id}/history/trend",
    response_model=list[dict],
    summary="Quality score over time, oldest first",
)
def score_trend(project: OwnedProject, db: DbSession) -> list[dict]:
    """A compact series for the trend chart.

    Deliberately not the full history payload: a sparkline needs a date and a
    number, and sending eleven other fields per point would be wasteful.
    """
    rows = db.execute(
        select(
            DatasetAnalysis.id,
            DatasetAnalysis.quality_score,
            DatasetAnalysis.completed_at,
            DatasetAnalysis.finding_count,
            Dataset.name,
        )
        .join(Dataset, Dataset.id == DatasetAnalysis.dataset_id)
        .where(
            DatasetAnalysis.project_id == project.id,
            DatasetAnalysis.status == AnalysisStatus.COMPLETED,
            DatasetAnalysis.quality_score.is_not(None),
        )
        .order_by(func.coalesce(DatasetAnalysis.completed_at, DatasetAnalysis.created_at))
    ).all()

    return [
        {
            "analysis_id": analysis_id,
            "score": float(score) if score is not None else None,
            "at": completed_at.isoformat() if completed_at else None,
            "finding_count": finding_count,
            "dataset_name": dataset_name,
        }
        for analysis_id, score, completed_at, finding_count, dataset_name in rows
    ]
