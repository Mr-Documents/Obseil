"""Runs every registered detector over a dataset."""

from __future__ import annotations

import logging

import pandas as pd

from app.profiling.types import DatasetProfile
from app.quality.base import DetectionContext, QualityDetector
from app.quality.registry import DETECTORS
from app.quality.types import FindingDraft, Severity

logger = logging.getLogger(__name__)


def run_detectors(
    frame: pd.DataFrame,
    profile: DatasetProfile,
    detectors: tuple[QualityDetector, ...] = DETECTORS,
) -> list[FindingDraft]:
    """Run every detector and return their findings, most severe first.

    A detector that raises is logged and skipped rather than failing the whole
    analysis: one broken check — very likely a contributed one — should not
    cost the user every other finding in their dataset.
    """
    context = DetectionContext(frame=frame, profile=profile)
    findings: list[FindingDraft] = []

    for detector in detectors:
        try:
            produced = detector.detect(context)
        except Exception:
            logger.exception("Detector %r failed; skipping it", detector.name)
            continue
        findings.extend(produced)

    findings.sort(key=lambda finding: finding.sort_key)
    logger.info(
        "Quality detection complete",
        extra={"detectors": len(detectors), "findings": len(findings)},
    )
    return findings


def severity_counts(findings: list[FindingDraft]) -> dict[Severity, int]:
    """Count findings per severity, including zeros for absent severities."""
    counts = dict.fromkeys(Severity, 0)
    for finding in findings:
        counts[finding.severity] += 1
    return counts
