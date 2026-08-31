"""Anomaly detector interface.

An anomaly detector answers a different question from a quality rule. A rule
says *this is wrong*. A detector says *this row is unusual; look at it*. The
type system keeps the two apart, and so does the documentation the UI shows.

Adding an algorithm means subclassing :class:`AnomalyDetector` and registering
it in ``app.ml.registry`` — see CONTRIBUTING.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class AnomalousRow:
    """One row the model considers unusual."""

    #: Positional index into the analysed frame, matching the row explorer.
    row_index: int
    #: Model-native score. Interpretation is algorithm-specific.
    raw_score: float
    #: 0-100, rescaled within this dataset. Higher is more unusual.
    #: Explicitly *not* a probability and *not* comparable across datasets.
    anomaly_score: float
    #: The feature values for this row, so the UI can show the actual data.
    feature_values: dict[str, float | None] = field(default_factory=dict)
    #: Features whose values deviate most from the column's centre, with the
    #: size of that deviation. This is "what stood out", never "what caused it".
    top_contributors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AnomalyResult:
    """The outcome of one anomaly-detection run."""

    #: False when detection was deliberately skipped; ``reason`` says why.
    ran: bool
    algorithm: str
    reason: str | None = None
    features: list[str] = field(default_factory=list)
    rows_scored: int = 0
    anomalies: list[AnomalousRow] = field(default_factory=list)
    #: Parameters actually used, for reproducibility and for the UI to show.
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def anomaly_count(self) -> int:
        return len(self.anomalies)

    @property
    def anomaly_rate(self) -> float:
        return round(self.anomaly_count / self.rows_scored * 100, 4) if self.rows_scored else 0.0


class AnomalyDetector(ABC):
    """Base class for unsupervised multivariate anomaly detection."""

    #: Stable identifier, persisted with each anomaly.
    algorithm: str = "anomaly_detector"

    @abstractmethod
    def detect(self, features: pd.DataFrame) -> AnomalyResult:
        """Score ``features`` and return the rows that stand out.

        ``features`` is already numeric, imputed and free of infinities — see
        ``app.ml.features``. Detectors do not do their own preparation, so that
        every algorithm is compared on identical inputs.
        """
