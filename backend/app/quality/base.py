"""Detector interface and the context every detector receives.

A detector is a small, pure class: given the loaded frame and its profile, it
returns zero or more :class:`FindingDraft` objects. It never touches the
database, the request, or another detector's output — which is what makes each
one testable with a five-row DataFrame.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import cached_property

import pandas as pd

from app.profiling.types import ColumnProfile, ColumnType, DatasetProfile
from app.quality.types import FindingDraft

#: Below this many rows, distribution-based rules (outliers, sign checks) are
#: not run at all: on twelve rows, "three standard deviations" is noise, and a
#: confident-looking finding derived from it would be worse than silence.
MIN_ROWS_FOR_DISTRIBUTION_RULES = 20

#: How many example row indices a finding carries.
MAX_SAMPLE_ROWS = 20

#: --- Identifying identifier columns ------------------------------------------
#:
#: Getting this wrong in either direction is costly: treat a measurement as a
#: key and every continuous column is reported as a "broken key"; miss a real
#: key and duplicate identifiers go unreported. Uniqueness alone cannot
#: separate them — a float measurement is naturally ~95% distinct, while a
#: genuinely broken key may be only 85% distinct.
#:
#: Two signals are therefore combined:
#:
#: 1. **Type.** Continuous floats are excluded outright. Keys are text or whole
#:    numbers; a key with a decimal point is not a thing.
#: 2. **Either near-perfect uniqueness, or a name that declares intent.**
#:    Without a name to go on, the bar is the profiler's ``is_unique`` (>=99%
#:    distinct): a 0-5000 integer measurement across 500 rows is ~95% distinct
#:    purely by the birthday problem, so anything lower would misread ordinary
#:    measurements as keys. A column *named* ``transaction_id``, though, is
#:    asserting that it identifies a transaction — for those, a much lower bar
#:    applies, because the gap below 100% is exactly the defect worth reporting.
#:
#: The accepted trade-off: a badly broken key with an unconventional name and
#: only ~90% distinct values is missed. That is far better than reporting every
#: continuous column in every dataset as a broken key.
NAMED_KEY_MIN_UNIQUENESS = 70.0

#: Suffixes and names that conventionally declare an identifier.
IDENTIFIER_NAME_PATTERNS = (
    "_id",
    "id_",
    "_key",
    "_code",
    "_ref",
    "_no",
    "_number",
    "uuid",
    "guid",
)
IDENTIFIER_EXACT_NAMES = {"id", "key", "code", "ref", "uuid", "guid", "pk"}


def name_declares_identifier(name: str) -> bool:
    """True when a column's name conventionally denotes an identifier."""
    lowered = name.strip().lower()
    if lowered in IDENTIFIER_EXACT_NAMES:
        return True
    return any(pattern in lowered for pattern in IDENTIFIER_NAME_PATTERNS)


@dataclass
class DetectionContext:
    # No `slots=True`: the cached properties below need an instance __dict__.
    """Everything a detector is allowed to look at."""

    frame: pd.DataFrame
    profile: DatasetProfile
    #: Extra state detectors may share, e.g. precomputed numeric features.
    scratch: dict[str, object] = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return self.profile.row_count

    @property
    def has_enough_rows_for_distribution_rules(self) -> bool:
        return self.row_count >= MIN_ROWS_FOR_DISTRIBUTION_RULES

    def columns_of_type(self, *types: ColumnType) -> list[ColumnProfile]:
        wanted = set(types)
        return [column for column in self.profile.columns if column.inferred_type in wanted]

    @cached_property
    def numeric_columns(self) -> list[ColumnProfile]:
        return [column for column in self.profile.columns if column.inferred_type.is_numeric]

    @staticmethod
    def is_key_like(column: ColumnProfile) -> bool:
        """True when a column is doing the job of an identifier.

        See the notes on ``KEY_LIKE_UNIQUENESS`` for why type and name are
        both consulted rather than uniqueness alone.
        """
        if column.count <= 1:
            return False
        # A continuous measurement is never a key, however distinct it is.
        if column.inferred_type is ColumnType.NUMERIC:
            return False
        if column.inferred_type not in {
            ColumnType.TEXT,
            ColumnType.CATEGORICAL,
            ColumnType.INTEGER,
        }:
            return False

        # `is_unique` is the profiler's >=99%-distinct flag: one definition of
        # "essentially a key", shared rather than re-derived here.
        if column.is_unique:
            return True
        return (
            name_declares_identifier(column.name)
            and column.unique_percentage >= NAMED_KEY_MIN_UNIQUENESS
        )

    def percentage(self, part: int) -> float:
        return round(part / self.row_count * 100, 4) if self.row_count else 0.0


class QualityDetector(ABC):
    """Base class for every deterministic quality check.

    Subclasses set ``name`` and implement :meth:`detect`. Register the class in
    ``app.quality.registry`` and it runs automatically — see CONTRIBUTING.md.
    """

    #: Stable identifier used in logs and error messages.
    name: str = "detector"

    @abstractmethod
    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        """Return every finding this detector can make about ``context``."""

    @staticmethod
    def sample_indices(mask: pd.Series, limit: int = MAX_SAMPLE_ROWS) -> list[int]:
        """Positional indices of the first ``limit`` rows matching ``mask``.

        Positional, not label-based: the UI's row preview is paginated by
        position, so a label index would point at the wrong row.
        """
        if mask is None or not mask.any():
            return []
        positions = mask.to_numpy().nonzero()[0]
        return [int(position) for position in positions[:limit]]
