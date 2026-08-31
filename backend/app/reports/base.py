"""Report format interface and the data every exporter receives.

An exporter turns one analysis into one file. It is handed a fully assembled
:class:`ReportData` — it never queries the database, so a new format is a pure
rendering problem and can be unit-tested against a fixture.

Adding a format: subclass :class:`ReportExporter`, register it in
``app.reports.registry``. See CONTRIBUTING.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.profiling.types import DatasetProfile
from app.quality.scoring import QualityScore


@dataclass(slots=True)
class ReportFinding:
    """A finding flattened for rendering, with its five answers intact."""

    type: str
    category: str
    severity: str
    severity_rank: int
    title: str
    description: str
    impact: str
    recommendation: str
    detection_method: str
    column: str | None
    affected_rows: int | None
    affected_percentage: float | None
    status: str
    verdict: str | None


@dataclass(slots=True)
class ReportData:
    """Everything any exporter could need about one analysis."""

    dataset_name: str
    dataset_filename: str
    dataset_format: str
    dataset_size_bytes: int
    project_name: str
    analysis_id: str
    analysed_at: datetime | None
    generated_at: datetime

    profile: DatasetProfile | None
    score: QualityScore | None
    findings: list[ReportFinding] = field(default_factory=list)

    anomaly_count: int = 0
    anomaly_rate: float = 0.0
    ml_algorithm: str | None = None
    ml_features: list[str] = field(default_factory=list)
    ml_skipped_reason: str | None = None

    duration_ms: int | None = None

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    @property
    def rule_findings(self) -> list[ReportFinding]:
        return [finding for finding in self.findings if finding.category == "rule"]

    @property
    def anomaly_findings(self) -> list[ReportFinding]:
        return [finding for finding in self.findings if finding.category == "anomaly"]

    def recommendations(self, limit: int = 8) -> list[tuple[str, str]]:
        """The most severe findings' recommendations, de-duplicated.

        Two columns with the same problem produce the same advice; repeating it
        eight times makes a report look thorough while telling the reader
        nothing new.
        """
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for finding in sorted(self.findings, key=lambda item: -item.severity_rank):
            if finding.recommendation in seen:
                continue
            seen.add(finding.recommendation)
            result.append((finding.title, finding.recommendation))
            if len(result) >= limit:
                break
        return result


@dataclass(slots=True)
class RenderedReport:
    content: bytes
    media_type: str
    filename: str


class ReportExporter(ABC):
    """Renders a :class:`ReportData` into a downloadable file."""

    #: Stable identifier used as the `format` query parameter.
    format: str = "report"
    extension: str = "bin"
    media_type: str = "application/octet-stream"
    label: str = "Report"

    @abstractmethod
    def render(self, data: ReportData, **options: Any) -> bytes:
        """Produce the file's bytes."""

    def filename_for(self, data: ReportData) -> str:
        """A safe, informative download name."""
        stem = "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in data.dataset_name
        ).strip("-")
        stamp = (data.analysed_at or data.generated_at).strftime("%Y%m%d")
        return f"obseil-{stem or 'dataset'}-{stamp}.{self.extension}"

    def export(self, data: ReportData, **options: Any) -> RenderedReport:
        return RenderedReport(
            content=self.render(data, **options),
            media_type=self.media_type,
            filename=self.filename_for(data),
        )
