"""Anomaly and quality-score endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.errors import NotFoundError
from app.models.anomaly import Anomaly
from app.models.dataset import AnalysisStatus, DatasetAnalysis
from app.quality.scoring import QualityScore
from app.schemas.anomaly import AnomalyOverview, AnomalyRead, QualityScoreRead
from app.schemas.common import Page
from app.services import dataset_service

router = APIRouter(tags=["anomalies"])


def _latest_completed(db: DbSession, dataset_id: str, user: CurrentUser) -> DatasetAnalysis:
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    dataset_service.require_ready(dataset)

    analysis = dataset_service.latest_analysis(db, dataset=dataset)
    if analysis is None or analysis.status != AnalysisStatus.COMPLETED:
        raise NotFoundError(
            "This dataset has not been analysed yet. Run an analysis first.",
            code="analysis_missing",
        )
    return analysis


@router.get(
    "/datasets/{dataset_id}/anomalies",
    response_model=Page[AnomalyRead],
    summary="Rows the ML model flagged as unusual, most unusual first",
)
def list_anomalies(
    dataset_id: str, db: DbSession, user: CurrentUser, page: Pagination
) -> Page[AnomalyRead]:
    analysis = _latest_completed(db, dataset_id, user)

    total = (
        db.scalar(
            select(func.count()).select_from(Anomaly).where(Anomaly.analysis_id == analysis.id)
        )
        or 0
    )
    rows = db.scalars(
        select(Anomaly)
        .where(Anomaly.analysis_id == analysis.id)
        .order_by(Anomaly.rank)
        .limit(page.limit)
        .offset(page.offset)
    ).all()

    return Page[AnomalyRead](
        items=[AnomalyRead.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/datasets/{dataset_id}/anomalies/overview",
    response_model=AnomalyOverview,
    summary="How anomaly detection was run, and what it found",
)
def anomalies_overview(dataset_id: str, db: DbSession, user: CurrentUser) -> AnomalyOverview:
    analysis = _latest_completed(db, dataset_id, user)

    return AnomalyOverview(
        analysis_id=analysis.id,
        ran=analysis.ml_skipped_reason is None and analysis.ml_algorithm is not None,
        skipped_reason=analysis.ml_skipped_reason,
        algorithm=analysis.ml_algorithm,
        features=list(analysis.ml_features or []),
        parameters=dict(analysis.ml_parameters or {}),
        rows_scored=analysis.row_count,
        anomaly_count=analysis.anomaly_count,
        anomaly_rate=analysis.anomaly_rate,
    )


@router.get(
    "/datasets/{dataset_id}/score",
    response_model=QualityScoreRead,
    summary="The quality score, with its full derivation",
)
def quality_score(dataset_id: str, db: DbSession, user: CurrentUser) -> QualityScoreRead:
    analysis = _latest_completed(db, dataset_id, user)

    if not analysis.score_breakdown:
        raise NotFoundError(
            "This analysis predates quality scoring. Re-run it to get a score.",
            code="score_missing",
        )

    breakdown = QualityScore.model_validate(analysis.score_breakdown)
    return QualityScoreRead(
        **breakdown.model_dump(),
        analysis_id=analysis.id,
        dataset_id=analysis.dataset_id,
        analysed_at=analysis.completed_at,
    )
