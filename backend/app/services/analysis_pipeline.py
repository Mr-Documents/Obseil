"""The analysis pipeline.

    load -> profile -> quality checks -> anomaly detection -> findings -> score

Each stage is a separate module; this file is the conductor. It is the only
place that knows the order of the stages, so adding one is a local change.

Loading is deliberately not cached across stages: the frame is read once and
handed to every stage, because re-reading a 50 MB CSV four times would dominate
the runtime.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.core.errors import AnalysisError, DatasetError, StorageError
from app.data.formats import FileFormat
from app.data.readers import get_reader
from app.data.readers.base import LoadResult
from app.ml import AnomalyResult, anomaly_finding, detect_anomalies
from app.profiling import DatasetProfile, profile_dataset
from app.quality import FindingDraft, run_detectors
from app.quality.scoring import QualityScore, calculate_quality_score
from app.storage import get_storage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AnalysisResult:
    """Everything one pipeline run produced."""

    profile: DatasetProfile
    findings: list[FindingDraft]
    anomalies: AnomalyResult
    score: QualityScore
    frame: pd.DataFrame
    duration_ms: int


def load_dataset(storage_key: str, file_format: str) -> LoadResult:
    """Read a stored dataset into a DataFrame, sampling if it is very large.

    Two ceilings apply, both configurable:

    * ``max_analysis_rows`` - beyond this the dataset is refused outright,
      because a partial answer presented as a whole-file answer is worse than
      no answer.
    * ``profile_sample_rows`` - below the hard ceiling but above this, the
      analysis runs on a deterministic head sample. The profile records that it
      was sampled and the UI says so.
    """
    storage = get_storage()
    path: Path | None = storage.local_path(storage_key)
    if path is None or not path.is_file():
        raise StorageError(
            "The stored dataset file is missing. It may have been removed from disk."
        )

    reader = get_reader(FileFormat(file_format))
    result = reader.load(path, max_rows=settings.profile_sample_rows)

    if result.total_rows > settings.max_analysis_rows:
        raise DatasetError(
            f"This dataset has {result.total_rows:,} rows, above the "
            f"{settings.max_analysis_rows:,} row limit for a single analysis.",
            code="dataset_too_large",
            details={"row_count": result.total_rows, "max_rows": settings.max_analysis_rows},
        )

    if result.sampled:
        result.notes.append(
            f"The file has {result.total_rows:,} rows; the analysis used the first "
            f"{len(result.frame):,} of them."
        )

    return result


def run_analysis(storage_key: str, file_format: str) -> AnalysisResult:
    """Run the full pipeline over a stored dataset.

    Raises ``DatasetError`` when the file itself is the problem (the user can
    fix that) and ``AnalysisError`` when our own code failed (they cannot).
    Keeping the two apart is what lets the API return an actionable 422 instead
    of an opaque 500.
    """
    started = time.perf_counter()

    loaded = load_dataset(storage_key, file_format)

    try:
        profile = profile_dataset(
            loaded.frame,
            source_rows=loaded.total_rows,
            sampled=loaded.sampled,
            notes=_reader_notes(loaded),
        )
    except DatasetError:
        raise
    except Exception as exc:  # the profiler must never leak a raw error
        logger.exception("Profiling failed for %s", storage_key)
        raise AnalysisError("The dataset could not be profiled.") from exc

    # Individual detectors already fail soft inside `run_detectors`; this guard
    # is for a failure in the engine itself.
    try:
        findings = run_detectors(loaded.frame, profile)
    except Exception as exc:
        logger.exception("Quality detection failed for %s", storage_key)
        raise AnalysisError("The quality checks could not be completed.") from exc

    # A failure in the ML stage must not lose the deterministic findings the
    # user already has: anomaly detection is additive, so it degrades to "not
    # run" with the reason recorded, exactly like a deliberate skip.
    try:
        anomalies = detect_anomalies(loaded.frame, profile)
    except Exception:
        logger.exception("Anomaly detection failed for %s", storage_key)
        anomalies = AnomalyResult(
            ran=False,
            algorithm="isolation_forest",
            reason="Anomaly detection failed; the deterministic checks above still ran.",
        )

    ml_finding = anomaly_finding(anomalies, profile.row_count)
    if ml_finding is not None:
        findings.append(ml_finding)
        findings.sort(key=lambda finding: finding.sort_key)

    score = calculate_quality_score(findings)

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "Analysis complete",
        extra={
            "storage_key": storage_key,
            "rows": profile.row_count,
            "columns": profile.column_count,
            "findings": len(findings),
            "anomalies": anomalies.anomaly_count,
            "quality_score": score.score,
            "duration_ms": duration_ms,
        },
    )
    return AnalysisResult(
        profile=profile,
        findings=findings,
        anomalies=anomalies,
        score=score,
        frame=loaded.frame,
        duration_ms=duration_ms,
    )


def _reader_notes(loaded: LoadResult) -> list[str]:
    """Surface the reader's assumptions so the user can sanity-check them."""
    notes = list(loaded.notes)
    if loaded.delimiter and loaded.delimiter != ",":
        label = {"\t": "tab", ";": "semicolon", "|": "pipe"}.get(loaded.delimiter, loaded.delimiter)
        notes.append(f"The file was read using a {label} delimiter.")
    if loaded.encoding and loaded.encoding not in {"utf-8", "utf-8-sig"}:
        notes.append(f"The file was decoded as {loaded.encoding}.")
    if loaded.sheet_name:
        notes.append(f"Worksheet “{loaded.sheet_name}” was analysed.")
    return notes
