"""Dataset upload, retrieval, analysis and preview endpoints."""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession, OwnedProject, Pagination
from app.core.errors import NotFoundError, ValidationError
from app.models.dataset import AnalysisStatus, Dataset
from app.profiling.types import DatasetProfile
from app.schemas.common import Page
from app.schemas.dataset import (
    AnalysisRead,
    AnalysisSummary,
    DatasetDetail,
    DatasetPreview,
    DatasetPreviewRow,
    DatasetRead,
    DatasetStatistics,
)
from app.services import analysis_pipeline, dataset_service

router = APIRouter(tags=["datasets"])

MAX_PREVIEW_ROWS = 200


def _detail(db: DbSession, dataset: Dataset) -> DatasetDetail:
    latest = dataset_service.latest_analysis(db, dataset=dataset)
    return DatasetDetail(
        **DatasetRead.model_validate(dataset).model_dump(),
        latest_analysis=AnalysisSummary.model_validate(latest) if latest else None,
    )


# --- Project-scoped ---------------------------------------------------------
@router.get(
    "/projects/{project_id}/datasets",
    response_model=Page[DatasetDetail],
    summary="List the datasets in a project",
)
def list_datasets(project: OwnedProject, db: DbSession, page: Pagination) -> Page[DatasetDetail]:
    datasets = dataset_service.list_datasets(
        db, project=project, limit=page.limit, offset=page.offset
    )
    return Page[DatasetDetail](
        items=[_detail(db, dataset) for dataset in datasets],
        total=dataset_service.count_datasets(db, project=project),
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a dataset and analyse it",
    responses={
        413: {"description": "File exceeds the upload limit"},
        415: {"description": "Unsupported file type"},
        422: {"description": "The file could not be read"},
    },
)
def upload_dataset(
    project: OwnedProject,
    db: DbSession,
    file: UploadFile = File(..., description="CSV or XLSX file."),
    name: str | None = Form(None, description="Display name. Defaults to the filename."),
    analyze: bool = Form(True, description="Run the analysis immediately."),
) -> DatasetDetail:
    """Accept a file, store it, and (by default) analyse it in the same request.

    Analysis runs inline because it is a seconds-long, CPU-bound job and a
    background worker would add an operational dependency the MVP does not
    need. The ``analyze`` flag exists so a client can defer it, and the split
    between upload and analysis is already in the service layer, so moving to a
    queue later is a change of caller, not of design.
    """
    if not file.filename:
        raise ValidationError("The upload is missing a filename.")

    dataset = dataset_service.create_dataset(
        db, project=project, filename=file.filename, stream=file.file, name=name
    )

    if analyze:
        dataset_service.analyze_dataset(db, dataset=dataset)
        db.refresh(dataset)

    return _detail(db, dataset)


# --- Dataset-scoped ---------------------------------------------------------
@router.get("/datasets/{dataset_id}", response_model=DatasetDetail, summary="Get a dataset")
def get_dataset(dataset_id: str, db: DbSession, user: CurrentUser) -> DatasetDetail:
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    return _detail(db, dataset)


@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dataset and its analyses",
)
def delete_dataset(dataset_id: str, db: DbSession, user: CurrentUser) -> Response:
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    dataset_service.delete_dataset(db, dataset=dataset)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/datasets/{dataset_id}/analyze",
    response_model=AnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run a fresh analysis",
)
def analyze_dataset(dataset_id: str, db: DbSession, user: CurrentUser) -> AnalysisRead:
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    analysis = dataset_service.analyze_dataset(db, dataset=dataset)
    return AnalysisRead.model_validate(analysis)


@router.get(
    "/datasets/{dataset_id}/statistics",
    response_model=DatasetStatistics,
    summary="Profile statistics for the latest analysis",
)
def get_statistics(dataset_id: str, db: DbSession, user: CurrentUser) -> DatasetStatistics:
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    dataset_service.require_ready(dataset)

    analysis = dataset_service.latest_analysis(db, dataset=dataset)
    if analysis is None or analysis.status != AnalysisStatus.COMPLETED or not analysis.profile:
        raise NotFoundError(
            "This dataset has not been analysed yet. Run an analysis to see its statistics.",
            code="analysis_missing",
        )

    profile = DatasetProfile.model_validate(analysis.profile)
    return DatasetStatistics(
        dataset_id=dataset.id,
        analysis_id=analysis.id,
        analysed_at=analysis.completed_at,
        row_count=profile.row_count,
        column_count=profile.column_count,
        total_cells=profile.total_cells,
        missing_cells=profile.missing_cells,
        missing_percentage=profile.missing_percentage,
        duplicate_row_count=profile.duplicate_row_count,
        duplicate_row_percentage=profile.duplicate_row_percentage,
        memory_bytes=profile.memory_bytes,
        sampled=profile.sampled,
        source_rows=profile.source_rows,
        notes=profile.notes,
        columns=profile.columns,
    )


@router.get(
    "/datasets/{dataset_id}/preview",
    response_model=DatasetPreview,
    summary="A page of raw rows",
)
def preview_dataset(
    dataset_id: str,
    db: DbSession,
    user: CurrentUser,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PREVIEW_ROWS),
) -> DatasetPreview:
    """Return a bounded window of rows.

    The whole file is never sent: the explorer paginates, and ``limit`` is
    capped server-side so a client cannot ask for a million rows.
    """
    dataset = dataset_service.get_owned_dataset(db, dataset_id=dataset_id, user=user)
    dataset_service.require_ready(dataset)

    loaded = analysis_pipeline.load_dataset(dataset.storage_key, dataset.file_format)
    frame = loaded.frame
    window = frame.iloc[offset : offset + limit]

    return DatasetPreview(
        columns=[str(column) for column in frame.columns],
        rows=[
            DatasetPreviewRow(
                index=int(position),
                values={str(column): _cell(row[column]) for column in frame.columns},
            )
            for position, (_, row) in enumerate(window.iterrows(), start=offset)
        ],
        total_rows=len(frame),
        offset=offset,
        limit=limit,
    )


def _cell(value: object) -> str | None:
    """Render one cell for transport.

    Everything becomes a string (or null): the explorer displays values, it does
    not compute with them, and stringifying here means a column of mixed types
    cannot break JSON serialisation.

    Integral floats drop their ``.0``. pandas widens an integer column to
    float64 as soon as it contains one missing value, so without this an id of
    ``7`` would be shown to the user as ``7.0`` — a value that was never in
    their file.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return str(int(value))
    return str(value)
