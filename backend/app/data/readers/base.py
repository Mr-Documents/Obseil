"""Reader interface and the shared post-load normalisation.

A reader turns bytes on disk into a ``pandas.DataFrame`` plus a small
:class:`LoadResult` describing what had to be assumed along the way (encoding,
delimiter, sheet, whether the data was sampled). Those assumptions are surfaced
in the UI so nobody has to guess why a column looks odd.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.core.errors import DatasetError

logger = logging.getLogger(__name__)

#: Column labels pandas invents for blank headers.
_UNNAMED = "Unnamed:"

#: pandas silently disambiguates repeated headers by appending ``.1``, ``.2``.
#: We rewrite those to ``_1`` for consistency with our own suffixing, and — more
#: importantly — surface them, because a user whose export has two "amount"
#: columns needs to be told rather than left to wonder which one they are
#: reading. Only rewritten when the base name is genuinely present, so a real
#: column called "v1.2" is left alone.
_PANDAS_MANGLED = re.compile(r"^(?P<base>.+)\.(?P<index>\d+)$")


@dataclass(slots=True)
class LoadResult:
    """A loaded dataset plus the decisions the reader had to make."""

    frame: pd.DataFrame
    #: Rows in the source file, which may exceed ``len(frame)`` when sampled.
    total_rows: int
    sampled: bool = False
    encoding: str | None = None
    delimiter: str | None = None
    sheet_name: str | None = None
    #: Human-readable notes, e.g. "3 duplicate column names were renamed".
    notes: list[str] = field(default_factory=list)


class DatasetReader(ABC):
    """Loads one file format into a DataFrame."""

    #: Rows read for a quick schema peek without loading the whole file.
    PREVIEW_ROWS = 100

    @abstractmethod
    def load(self, path: Path, *, max_rows: int | None = None) -> LoadResult:
        """Read the file at ``path``, optionally stopping after ``max_rows``."""


def normalize_columns(frame: pd.DataFrame) -> list[str]:
    """Make column labels usable, and report what had to change.

    Three real-world problems are handled:
      * blank headers, which pandas names ``Unnamed: 3``
      * surrounding whitespace, which makes ``"amount "`` and ``"amount"`` look
        like different columns to anyone reading the report
      * duplicate names, which would make column-level findings ambiguous
    """
    notes: list[str] = []
    original = list(frame.columns)

    renamed_blank = 0
    trimmed = 0
    cleaned: list[str] = []
    for index, label in enumerate(original):
        text = "" if label is None else str(label)
        if text.startswith(_UNNAMED) or not text.strip():
            cleaned.append(f"column_{index + 1}")
            renamed_blank += 1
            continue
        stripped = text.strip()
        if stripped != text:
            trimmed += 1
        cleaned.append(stripped)

    present = set(cleaned)
    unmangled: list[str] = []
    duplicates = 0
    for label in cleaned:
        match = _PANDAS_MANGLED.match(label)
        if match and match.group("base") in present:
            unmangled.append(f"{match.group('base')}_{match.group('index')}")
            duplicates += 1
        else:
            unmangled.append(label)

    seen: dict[str, int] = {}
    deduplicated: list[str] = []
    for label in unmangled:
        if label in seen:
            seen[label] += 1
            duplicates += 1
            deduplicated.append(f"{label}_{seen[label]}")
        else:
            seen[label] = 0
            deduplicated.append(label)

    if renamed_blank:
        notes.append(
            f"{renamed_blank} column{'s' if renamed_blank > 1 else ''} had no header "
            "and were named by position."
        )
    if trimmed:
        notes.append(f"Whitespace was trimmed from {trimmed} column name(s).")
    if duplicates:
        notes.append(
            f"{duplicates} duplicate column name(s) were made unique by appending a suffix."
        )

    frame.columns = pd.Index(deduplicated)
    return notes


def validate_frame(frame: pd.DataFrame, *, source: str) -> None:
    """Reject frames that cannot meaningfully be analysed."""
    if frame.shape[1] == 0:
        raise DatasetError(
            f"No columns were found in {source}. Check that the file has a header row.",
            code="dataset_no_columns",
        )
    if frame.shape[0] == 0:
        raise DatasetError(
            f"{source} has a header but no data rows. Upload a file with at least one record.",
            code="dataset_empty",
        )
