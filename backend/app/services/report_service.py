"""Assembles the data a report exporter needs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import DatasetError
from app.models.dataset import AnalysisStatus, Dataset, DatasetAnalysis
from app.models.finding import Finding
from app.profiling.types import DatasetProfile
from app.quality.scoring import QualityScore
from app.quality.types import Severity
from app.reports.base import RenderedReport, ReportData, ReportFinding
from app.reports.registry import get_exporter

logger = logging.getLogger(__name__)


def build_report_data(db: Session, *, analysis: DatasetAnalysis) -> ReportData:
    """Gather everything about one analysis into a render-ready structure."""
    if analysis.status != AnalysisStatus.COMPLETED:
        raise DatasetError(
            "This analysis did not complete, so there is nothing to report on.",
            code="analysis_incomplete",
        )

    dataset = db.get(Dataset, analysis.dataset_id)
    if dataset is None:  # pragma: no cover - guarded by the foreign key
        raise DatasetError("The dataset for this analysis no longer exists.")

    findings = db.scalars(
        select(Finding)
        .options(selectinload(Finding.feedback))
        .where(Finding.analysis_id == analysis.id)
        .order_by(Finding.severity_rank.desc(), Finding.id)
    ).all()

    return ReportData(
        dataset_name=dataset.name,
        dataset_filename=dataset.original_filename,
        dataset_format=dataset.file_format,
        dataset_size_bytes=dataset.size_bytes,
        project_name=dataset.project.name if dataset.project else "",
        analysis_id=analysis.id,
        analysed_at=analysis.completed_at,
        generated_at=datetime.now(UTC),
        profile=DatasetProfile.model_validate(analysis.profile) if analysis.profile else None,
        score=(
            QualityScore.model_validate(analysis.score_breakdown)
            if analysis.score_breakdown
            else None
        ),
        findings=[
            ReportFinding(
                type=finding.type,
                category=finding.category,
                severity=finding.severity,
                severity_rank=_rank(finding.severity),
                title=finding.title,
                description=finding.description,
                impact=finding.impact,
                recommendation=finding.recommendation,
                detection_method=finding.detection_method,
                column=finding.column_name,
                affected_rows=finding.affected_rows,
                affected_percentage=finding.affected_percentage,
                status=finding.status,
                verdict=finding.feedback.verdict if finding.feedback else None,
            )
            for finding in findings
        ],
        anomaly_count=analysis.anomaly_count,
        anomaly_rate=analysis.anomaly_rate,
        ml_algorithm=analysis.ml_algorithm,
        ml_features=list(analysis.ml_features or []),
        ml_skipped_reason=analysis.ml_skipped_reason,
        duration_ms=analysis.duration_ms,
    )


def _rank(severity: str) -> int:
    try:
        return Severity(severity).rank
    except ValueError:  # pragma: no cover - severities are written by us
        return 0


def export_analysis(db: Session, *, analysis: DatasetAnalysis, format_name: str) -> RenderedReport:
    """Render one analysis in the requested format."""
    exporter = get_exporter(format_name)
    report = exporter.export(build_report_data(db, analysis=analysis))
    logger.info(
        "Exported report",
        extra={
            "analysis_id": analysis.id,
            "format": format_name,
            "bytes": len(report.content),
        },
    )
    return report
