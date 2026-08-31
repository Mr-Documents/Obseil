"""CSV reader.

Real CSV exports are messy: unknown encodings, semicolon or tab delimiters,
BOMs from Excel. Rather than demanding a well-formed file, the reader tries a
short, ordered list of possibilities and records which one worked so the UI can
tell the user what was assumed.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

from app.core.errors import DatasetError
from app.data.readers.base import DatasetReader, LoadResult, normalize_columns, validate_frame

logger = logging.getLogger(__name__)

#: Tried in order. utf-8-sig first because Excel writes a BOM, and cp1252 last
#: because it accepts almost any byte and would mask a better match.
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

DELIMITERS = (",", ";", "\t", "|")

#: Values pandas should read as missing, on top of its own defaults. These are
#: what real exports actually contain.
NA_VALUES = ["", "NA", "N/A", "n/a", "null", "NULL", "None", "NaN", "-", "--", "?"]

_SNIFF_BYTES = 64 * 1024


def _read_sample(path: Path) -> tuple[str, str]:
    """Return a decoded head of the file and the encoding that decoded it."""
    raw = path.read_bytes()[:_SNIFF_BYTES]
    if not raw.strip():
        raise DatasetError("The file is empty.", code="dataset_empty")

    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise DatasetError(
        "The file's text encoding could not be determined. Re-export it as UTF-8 CSV.",
        code="dataset_encoding",
    )


def sniff_delimiter(sample: str) -> str:
    """Guess the delimiter, falling back to whichever candidate appears most.

    ``csv.Sniffer`` is accurate when it works and raises when it does not, so a
    frequency count on the header line is the backstop.
    """
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS)).delimiter
    except csv.Error:
        header = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {delimiter: header.count(delimiter) for delimiter in DELIMITERS}
        best = max(counts, key=lambda key: counts[key])
        return best if counts[best] > 0 else ","


class CsvReader(DatasetReader):
    def load(self, path: Path, *, max_rows: int | None = None) -> LoadResult:
        sample, encoding = _read_sample(path)
        delimiter = sniff_delimiter(sample)

        try:
            frame = pd.read_csv(
                path,
                sep=delimiter,
                encoding=encoding,
                nrows=max_rows,
                na_values=NA_VALUES,
                keep_default_na=True,
                skip_blank_lines=True,
                # Never silently coerce mixed types; the quality engine wants to
                # see that a column contains both numbers and text.
                low_memory=False,
                on_bad_lines="warn",
            )
        except UnicodeDecodeError as exc:
            raise DatasetError(
                "The file could not be decoded. Re-export it as UTF-8 CSV.",
                code="dataset_encoding",
            ) from exc
        except pd.errors.EmptyDataError as exc:
            raise DatasetError("The file contains no data.", code="dataset_empty") from exc
        except pd.errors.ParserError as exc:
            raise DatasetError(
                "The file could not be parsed as CSV. Rows appear to have differing "
                "numbers of fields - check for unescaped quotes or stray separators.",
                code="dataset_parse_error",
            ) from exc
        except (ValueError, OSError) as exc:
            logger.exception("Unexpected failure reading CSV at %s", path)
            raise DatasetError("The CSV file could not be read.") from exc

        notes = normalize_columns(frame)
        validate_frame(frame, source="the CSV file")

        total_rows = len(frame) if max_rows is None else _count_data_rows(path, encoding)
        return LoadResult(
            frame=frame,
            total_rows=total_rows,
            sampled=max_rows is not None and total_rows > len(frame),
            encoding=encoding,
            delimiter=delimiter,
            notes=notes,
        )


def _count_data_rows(path: Path, encoding: str) -> int:
    """Count rows without materialising the file, minus the header."""
    try:
        with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
            lines = sum(1 for line in handle if line.strip())
    except OSError:
        return 0
    return max(lines - 1, 0)
