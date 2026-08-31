"""Runs anomaly detection and turns the result into a finding."""

from __future__ import annotations

import logging

import pandas as pd

from app.ml.base import AnomalyResult
from app.ml.features import prepare_features
from app.ml.registry import DEFAULT_ALGORITHM, get_detector
from app.profiling.types import DatasetProfile
from app.quality.types import (
    DetectionMethod,
    FindingCategory,
    FindingDraft,
    FindingType,
    Severity,
)

logger = logging.getLogger(__name__)

#: Severity bands for the anomaly finding, by share of rows flagged.
#: Capped at medium: an anomaly is a *candidate for review*, not a defect, and
#: letting the model raise a critical finding would overstate what it knows.
ANOMALY_HIGH_SHARE = 5.0
ANOMALY_MEDIUM_SHARE = 1.0

#: Row indices carried on the finding so the UI can jump to the worst offenders.
MAX_SAMPLE_ROWS = 20


def detect_anomalies(
    frame: pd.DataFrame, profile: DatasetProfile, algorithm: str = DEFAULT_ALGORITHM
) -> AnomalyResult:
    """Prepare features and run the configured detector.

    Skipping is a normal outcome, not a failure: a two-column dataset has no
    multivariate structure to find, and saying so is more useful than returning
    a confident-looking empty result.
    """
    features = prepare_features(frame, profile)

    if not features.usable:
        logger.info("Anomaly detection skipped", extra={"reason": features.skip_reason})
        return AnomalyResult(
            ran=False,
            algorithm=algorithm,
            reason=features.skip_reason,
            parameters={
                "dropped_columns": features.dropped_columns,
                "imputed_columns": features.imputed_columns,
            },
        )

    result = get_detector(algorithm).detect(features.frame)
    result.parameters["dropped_columns"] = features.dropped_columns
    result.parameters["imputed_columns"] = features.imputed_columns
    return result


def anomaly_finding(result: AnomalyResult, row_count: int) -> FindingDraft | None:
    """Summarise an anomaly run as a single finding, or ``None`` if it found nothing.

    One finding, not one per row: a hundred separate "this row is unusual"
    entries would bury the deterministic findings that state actual facts. The
    individual rows are stored separately and shown in the anomalies view.
    """
    if not result.ran or result.anomaly_count == 0:
        return None

    share = result.anomaly_rate
    severity = (
        Severity.HIGH
        if share >= ANOMALY_HIGH_SHARE
        else Severity.MEDIUM if share >= ANOMALY_MEDIUM_SHARE else Severity.LOW
    )

    feature_list = ", ".join(result.features[:6]) + (
        f" and {len(result.features) - 6} more" if len(result.features) > 6 else ""
    )

    return FindingDraft(
        type=FindingType.ML_ANOMALY,
        category=FindingCategory.ANOMALY,
        severity=severity,
        title=f"{result.anomaly_count:,} rows look unusual across several columns",
        description=(
            f"An Isolation Forest trained on {len(result.features)} numeric columns "
            f"({feature_list}) flagged {result.anomaly_count:,} of {result.rows_scored:,} rows "
            f"({share:.1f}%) as unusual. These rows are not necessarily wrong: each of their "
            "individual values may sit well inside its own column's normal range. What makes "
            "them stand out is the combination."
        ),
        impact=(
            "Combinations that no single-column rule can see are where silent data problems "
            "hide - a mis-mapped field, a partially failed load, a test record in production "
            "data. They are equally often genuine edge cases, which is why they are reported "
            "for review rather than as defects."
        ),
        recommendation=(
            "Open the Anomalies view and look at the highest-scoring rows first. Each row shows "
            "the values the model saw and which of them sit furthest from their column's centre. "
            "If they are legitimate, mark this finding as a false positive."
        ),
        detection_method=DetectionMethod.ISOLATION_FOREST,
        columns=result.features,
        affected_rows=result.anomaly_count,
        affected_percentage=share,
        details={
            "algorithm": result.algorithm,
            "features_used": result.features,
            "rows_scored": result.rows_scored,
            **{
                key: value
                for key, value in result.parameters.items()
                if key in {"n_estimators", "contamination", "random_state", "scaled"}
            },
            "note": (
                "The model reports that a row is unusual. It does not know why, and Obseil "
                "does not claim otherwise."
            ),
        },
        sample_row_indices=[anomaly.row_index for anomaly in result.anomalies[:MAX_SAMPLE_ROWS]],
    )
