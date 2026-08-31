"""Anomaly detector registry.

The MVP ships one algorithm. The registry exists so that adding a second -
Local Outlier Factor, DBSCAN - is a two-line change plus a module, rather than
a refactor of the pipeline. Note that a distance-based detector must scale its
features first; see ``app.ml.features``.
"""

from __future__ import annotations

from app.ml.base import AnomalyDetector
from app.ml.detectors.isolation_forest import IsolationForestDetector

DETECTORS: dict[str, type[AnomalyDetector]] = {
    IsolationForestDetector.algorithm: IsolationForestDetector,
}

DEFAULT_ALGORITHM = IsolationForestDetector.algorithm

__all__ = ["DEFAULT_ALGORITHM", "DETECTORS", "get_detector"]


def get_detector(algorithm: str = DEFAULT_ALGORITHM) -> AnomalyDetector:
    detector_class = DETECTORS.get(algorithm)
    if detector_class is None:
        raise ValueError(f"No anomaly detector registered under {algorithm!r}")
    return detector_class()
