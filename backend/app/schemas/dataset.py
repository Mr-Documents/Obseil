"""Dataset and analysis contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.profiling.types import ColumnProfile, DatasetProfile
from app.schemas.common import ORMModel


class DatasetRead(ORMModel):
    id: str
    project_id: str
    name: str
    original_filename: str
    file_format: str
    size_bytes: int
    checksum_sha256: str
    row_count: int | None
    column_count: int | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class AnalysisSummary(ORMModel):
    """An analysis without its (potentially large) profile document."""

    id: str
    dataset_id: str
    project_id: str
    status: str
    error_message: str | None
    row_count: int
    column_count: int
    missing_cell_count: int
    missing_percentage: float
    duplicate_row_count: int
    duplicate_row_percentage: float

    quality_score: float | None
    quality_grade: str | None

    finding_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int

    anomaly_count: int
    anomaly_rate: float
    ml_skipped_reason: str | None

    duration_ms: int | None
    completed_at: datetime | None
    created_at: datetime


class AnalysisRead(AnalysisSummary):
    """An analysis including the full profile."""

    profile: DatasetProfile | None = None


class DatasetDetail(DatasetRead):
    """A dataset plus its most recent analysis, which is what the UI needs."""

    latest_analysis: AnalysisSummary | None = None


class DatasetStatistics(BaseModel):
    """The ``/statistics`` payload: dataset-level figures plus every column."""

    dataset_id: str
    analysis_id: str
    analysed_at: datetime | None
    row_count: int
    column_count: int
    total_cells: int
    missing_cells: int
    missing_percentage: float
    duplicate_row_count: int
    duplicate_row_percentage: float
    memory_bytes: int
    sampled: bool = False
    source_rows: int | None = None
    notes: list[str] = Field(default_factory=list)
    columns: list[ColumnProfile] = Field(default_factory=list)


class DatasetPreviewRow(BaseModel):
    """One row of the data preview. Values are stringified for safe transport."""

    index: int
    values: dict[str, str | None]


class DatasetPreview(BaseModel):
    columns: list[str]
    rows: list[DatasetPreviewRow]
    total_rows: int
    offset: int
    limit: int
