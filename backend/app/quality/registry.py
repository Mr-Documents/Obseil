"""Detector registry.

Adding a detector is two lines: import it and add it to ``DETECTORS``. The
engine iterates this list, so nothing else needs to know the new check exists.

Order is presentational only — findings are sorted by severity before they are
returned — but keeping related checks adjacent makes the list readable.
"""

from __future__ import annotations

from app.quality.base import QualityDetector
from app.quality.detectors.completeness import IncompleteRowDetector, MissingValueDetector
from app.quality.detectors.duplicates import DuplicateIdentifierDetector, DuplicateRowDetector
from app.quality.detectors.outliers import OutlierDetector
from app.quality.detectors.structure import (
    ConstantColumnDetector,
    HighCardinalityDetector,
    NumbersAsTextDetector,
)
from app.quality.detectors.validity import (
    InvalidDateDetector,
    NegativeValueDetector,
    StringHygieneDetector,
)

DETECTORS: tuple[QualityDetector, ...] = (
    # Completeness
    MissingValueDetector(),
    IncompleteRowDetector(),
    # Uniqueness
    DuplicateRowDetector(),
    DuplicateIdentifierDetector(),
    # Structure
    ConstantColumnDetector(),
    HighCardinalityDetector(),
    NumbersAsTextDetector(),
    # Validity
    NegativeValueDetector(),
    InvalidDateDetector(),
    StringHygieneDetector(),
    # Distribution
    OutlierDetector(),
)

__all__ = ["DETECTORS"]
