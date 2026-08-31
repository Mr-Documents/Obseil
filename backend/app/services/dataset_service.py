"""Dataset and analysis business logic."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import IO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AnalysisError, DatasetError, NotFoundError, ObseilError
from app.models.anomaly import Anomaly
from app.models.dataset import AnalysisStatus, Dataset, DatasetAnalysis, DatasetStatus
from app.models.project import Project
from app.models.user import User
from app.services import analysis_pipeline, finding_service
from app.services.upload import store_upload
from app.storage import get_storage

logger = logging.getLogger(__name__)


# --- Access -----------------------------------------------------------------
def get_owned_dataset(db: Session, *, dataset_id: str, user: User) -> Dataset:
    """Fetch a dataset the user owns, via its project.

    Like ``get_owned_project``, a dataset belonging to someone else is a 404 -
    the caller learns nothing about ids they have no right to.
    """
    dataset = db.scalar(
        select(Dataset)
        .join(Project, Project.id == Dataset.project_id)
        .where(Dataset.id == dataset_id, Project.owner_id == user.id)
    )
    if dataset is None:
        raise NotFoundError("That dataset does not exist, or you do not have access to it.")
    return dataset


def get_owned_analysis(db: Session, *, analysis_id: str, user: User) -> DatasetAnalysis:
    analysis = db.scalar(
        select(DatasetAnalysis)
        .join(Project, Project.id == DatasetAnalysis.project_id)
        .where(DatasetAnalysis.id == analysis_id, Project.owner_id == user.id)
    )
    if analysis is None:
        raise NotFoundError("That analysis does not exist, or you do not have access to it.")
    return analysis


# --- Listing ----------------------------------------------------------------
def list_datasets(db: Session, *, project: Project, limit: int, offset: int) -> list[Dataset]:
    return list(
        db.scalars(
            select(Dataset)
            .where(Dataset.project_id == project.id)
            .order_by(Dataset.created_at.desc(), Dataset.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )


def count_datasets(db: Session, *, project: Project) -> int:
    return (
        db.scalar(select(func.count()).select_from(Dataset).where(Dataset.project_id == project.id))
        or 0
    )


def latest_analysis(db: Session, *, dataset: Dataset) -> DatasetAnalysis | None:
    """The most recent completed run, or the most recent run of any status."""
    completed = db.scalar(
        select(DatasetAnalysis)
        .where(
            DatasetAnalysis.dataset_id == dataset.id,
            DatasetAnalysis.status == AnalysisStatus.COMPLETED,
        )
        .order_by(DatasetAnalysis.created_at.desc())
        .limit(1)
    )
    if completed is not None:
        return completed
    return db.scalar(
        select(DatasetAnalysis)
        .where(DatasetAnalysis.dataset_id == dataset.id)
        .order_by(DatasetAnalysis.created_at.desc())
        .limit(1)
    )


# --- Upload -----------------------------------------------------------------
def create_dataset(
    db: Session,
    *,
    project: Project,
    filename: str,
    stream: IO[bytes],
    name: str | None = None,
) -> Dataset:
    """Store an uploaded file and record it against the project.

    Analysis is a separate step so a slow or failing analysis never loses the
    upload the user just waited for.
    """
    stored = store_upload(project_id=project.id, filename=filename, stream=stream)

    dataset = Dataset(
        project_id=project.id,
        name=(name or stored.display_name).strip()[:160],
        original_filename=stored.original_filename,
        file_format=stored.file_format.value,
        storage_key=stored.storage_key,
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,
        status=DatasetStatus.UPLOADED,
    )
    db.add(dataset)
    try:
        db.commit()
    except Exception:
        # Never leave an orphaned blob behind if the row could not be written.
        db.rollback()
        get_storage().delete(stored.storage_key)
        raise
    db.refresh(dataset)

    logger.info("Dataset created", extra={"dataset_id": dataset.id, "project_id": project.id})
    return dataset


def delete_dataset(db: Session, *, dataset: Dataset) -> None:
    """Delete the row and its stored bytes.

    The row goes first: an orphaned file wastes disk, whereas a row pointing at
    a file that no longer exists is a broken dataset the user can see.
    """
    storage_key = dataset.storage_key
    db.delete(dataset)
    db.commit()
    get_storage().delete(storage_key)
    logger.info("Dataset deleted", extra={"storage_key": storage_key})


# --- Analysis ---------------------------------------------------------------
def analyze_dataset(db: Session, *, dataset: Dataset) -> DatasetAnalysis:
    """Run the pipeline over ``dataset`` and persist the result.

    A failed run is still recorded, with its reason, so the history shows what
    happened rather than silently skipping it.
    """
    analysis = DatasetAnalysis(
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        status=AnalysisStatus.RUNNING,
    )
    db.add(analysis)
    dataset.status = DatasetStatus.ANALYZING
    db.commit()

    try:
        result = analysis_pipeline.run_analysis(dataset.storage_key, dataset.file_format)
    except ObseilError as exc:
        _record_failure(db, dataset=dataset, analysis=analysis, message=exc.message)
        raise
    except Exception as exc:  # an unexpected failure must still be recorded
        logger.exception("Analysis crashed for dataset %s", dataset.id)
        _record_failure(
            db,
            dataset=dataset,
            analysis=analysis,
            message="The analysis failed unexpectedly.",
        )
        raise AnalysisError() from exc

    profile = result.profile
    analysis.status = AnalysisStatus.COMPLETED
    analysis.profile = profile.model_dump(mode="json")
    analysis.row_count = profile.row_count
    analysis.column_count = profile.column_count
    analysis.missing_cell_count = profile.missing_cells
    analysis.missing_percentage = profile.missing_percentage
    analysis.duplicate_row_count = profile.duplicate_row_count
    analysis.duplicate_row_percentage = profile.duplicate_row_percentage
    finding_service.persist_findings(db, analysis=analysis, drafts=result.findings)
    _persist_anomalies(db, analysis=analysis, result=result)

    analysis.quality_score = result.score.score
    analysis.quality_grade = result.score.grade.value
    analysis.score_breakdown = result.score.model_dump(mode="json")

    analysis.duration_ms = result.duration_ms
    analysis.completed_at = datetime.now(UTC)

    dataset.status = DatasetStatus.READY
    dataset.error_message = None
    dataset.row_count = profile.source_rows or profile.row_count
    dataset.column_count = profile.column_count

    db.commit()
    db.refresh(analysis)
    return analysis


def _persist_anomalies(
    db: Session, *, analysis: DatasetAnalysis, result: analysis_pipeline.AnalysisResult
) -> None:
    """Store the anomalous rows and the run's ML metadata."""
    anomalies = result.anomalies
    analysis.anomaly_count = anomalies.anomaly_count
    analysis.anomaly_rate = anomalies.anomaly_rate
    analysis.ml_algorithm = anomalies.algorithm if anomalies.ran else None
    analysis.ml_features = anomalies.features or None
    analysis.ml_parameters = anomalies.parameters or None
    # A skip is a normal outcome with a reason, not an error.
    analysis.ml_skipped_reason = None if anomalies.ran else anomalies.reason

    db.add_all(
        Anomaly(
            analysis_id=analysis.id,
            dataset_id=analysis.dataset_id,
            row_index=row.row_index,
            rank=rank,
            raw_score=row.raw_score,
            anomaly_score=row.anomaly_score,
            feature_values=row.feature_values or None,
            top_contributors=row.top_contributors or None,
        )
        for rank, row in enumerate(anomalies.anomalies)
    )


def _record_failure(
    db: Session, *, dataset: Dataset, analysis: DatasetAnalysis, message: str
) -> None:
    db.rollback()
    # Re-attach after the rollback: these rows may have been expired.
    analysis = db.merge(analysis)
    dataset = db.merge(dataset)
    analysis.status = AnalysisStatus.FAILED
    analysis.error_message = message
    analysis.completed_at = datetime.now(UTC)
    dataset.status = DatasetStatus.FAILED
    dataset.error_message = message
    db.commit()


def ensure_analysis(db: Session, *, dataset: Dataset) -> DatasetAnalysis:
    """Return the dataset's latest completed analysis, running one if needed."""
    existing = latest_analysis(db, dataset=dataset)
    if existing is not None and existing.status == AnalysisStatus.COMPLETED:
        return existing
    return analyze_dataset(db, dataset=dataset)


# --- Project roll-ups -------------------------------------------------------
def project_dataset_counts(db: Session, *, owner: User) -> dict[str, int]:
    """Dataset count per project for the owner, in one query."""
    rows = db.execute(
        select(Dataset.project_id, func.count(Dataset.id))
        .join(Project, Project.id == Dataset.project_id)
        .where(Project.owner_id == owner.id)
        .group_by(Dataset.project_id)
    ).all()
    return dict(rows)  # type: ignore[arg-type]


def project_analysis_counts(db: Session, *, owner: User) -> dict[str, int]:
    rows = db.execute(
        select(DatasetAnalysis.project_id, func.count(DatasetAnalysis.id))
        .join(Project, Project.id == DatasetAnalysis.project_id)
        .where(
            Project.owner_id == owner.id,
            DatasetAnalysis.status == AnalysisStatus.COMPLETED,
        )
        .group_by(DatasetAnalysis.project_id)
    ).all()
    return dict(rows)  # type: ignore[arg-type]


def project_latest_scores(db: Session, *, owner: User) -> dict[str, tuple[float, datetime]]:
    """Most recent completed score per project, in one query.

    ``DISTINCT ON`` would be neater but is PostgreSQL-only; a grouped max on
    the timestamp keeps the same query working under SQLite in the test suite.
    """
    latest = (
        select(
            DatasetAnalysis.project_id.label("project_id"),
            func.max(DatasetAnalysis.completed_at).label("completed_at"),
        )
        .join(Project, Project.id == DatasetAnalysis.project_id)
        .where(
            Project.owner_id == owner.id,
            DatasetAnalysis.status == AnalysisStatus.COMPLETED,
            DatasetAnalysis.quality_score.is_not(None),
        )
        .group_by(DatasetAnalysis.project_id)
        .subquery()
    )

    rows = db.execute(
        select(
            DatasetAnalysis.project_id,
            DatasetAnalysis.quality_score,
            DatasetAnalysis.completed_at,
        ).join(
            latest,
            (DatasetAnalysis.project_id == latest.c.project_id)
            & (DatasetAnalysis.completed_at == latest.c.completed_at),
        )
    ).all()

    return {
        str(project_id): (float(score), completed_at)
        for project_id, score, completed_at in rows
        if score is not None
    }


def require_ready(dataset: Dataset) -> None:
    """Guard for endpoints that need a completed analysis."""
    if dataset.status == DatasetStatus.FAILED:
        raise DatasetError(
            dataset.error_message or "This dataset could not be analysed.",
            code="dataset_failed",
        )
