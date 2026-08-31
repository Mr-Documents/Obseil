"""The dataset profiling engine.

Pure functions over a ``pandas.DataFrame``. Nothing here knows about HTTP, the
ORM or storage, which is what makes the whole engine directly unit-testable.

Design rule: never compute a statistic that does not mean anything for the
column's type. A mean over a categorical column is noise dressed up as insight,
so numeric statistics are attached only to numeric columns, datetime ranges
only to datetime columns, and so on.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from app.profiling.inference import coerce_datetime, coerce_numeric, infer_column_type
from app.profiling.types import (
    ColumnProfile,
    ColumnType,
    DatasetProfile,
    DatetimeStatistics,
    NumericStatistics,
    TextStatistics,
    ValueCount,
)

logger = logging.getLogger(__name__)

#: How many of the most frequent values to keep per column.
TOP_VALUE_COUNT = 10

#: A column is a candidate identifier when essentially every value is distinct.
#: Not 100%: a single duplicated id in a million-row export should still be
#: recognised as an id column (and separately flagged as a duplicate).
IDENTIFIER_UNIQUENESS_THRESHOLD = 0.99


def _finite(value: Any) -> float | None:
    """Convert a numpy/pandas scalar to a JSON-safe float, or ``None``.

    NaN and infinity are not representable in JSON. Returning ``None`` makes the
    absence explicit instead of emitting an invalid document.
    """
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _percentage(part: int, whole: int) -> float:
    return round(part / whole * 100, 4) if whole else 0.0


def _top_values(series: pd.Series, non_missing: int) -> list[ValueCount]:
    """The most frequent values, as strings, with their share of the column."""
    if non_missing == 0:
        return []
    counts = series.value_counts(dropna=True).head(TOP_VALUE_COUNT)
    return [
        ValueCount(
            value=str(value)[:200],
            count=int(count),
            percentage=_percentage(int(count), non_missing),
        )
        for value, count in counts.items()
    ]


def _numeric_statistics(values: pd.Series) -> NumericStatistics:
    """Descriptive statistics for a numeric column.

    Quartiles are computed alongside the mean because the quality engine's IQR
    outlier rule needs them, and computing them once here avoids a second pass
    over the column.
    """
    clean = values.dropna()
    if clean.empty:
        return NumericStatistics()

    q1 = _finite(clean.quantile(0.25))
    q3 = _finite(clean.quantile(0.75))
    return NumericStatistics(
        mean=_finite(clean.mean()),
        median=_finite(clean.median()),
        # ddof=1 (sample standard deviation): a dataset is a sample of a
        # process, not the entire population.
        std=_finite(clean.std(ddof=1)) if len(clean) > 1 else 0.0,
        minimum=_finite(clean.min()),
        maximum=_finite(clean.max()),
        q1=q1,
        q3=q3,
        iqr=None if q1 is None or q3 is None else round(q3 - q1, 6),
        skewness=_finite(clean.skew()) if len(clean) > 2 else None,
        zero_count=int((clean == 0).sum()),
        negative_count=int((clean < 0).sum()),
    )


def _datetime_statistics(values: pd.Series) -> DatetimeStatistics:
    clean = values.dropna()
    if clean.empty:
        return DatetimeStatistics()

    earliest, latest = clean.min(), clean.max()
    span = latest - earliest
    return DatetimeStatistics(
        earliest=earliest.isoformat() if pd.notna(earliest) else None,
        latest=latest.isoformat() if pd.notna(latest) else None,
        range_days=_finite(span.total_seconds() / 86400) if pd.notna(span) else None,
    )


def _text_statistics(series: pd.Series) -> TextStatistics:
    """Length distribution plus the two string defects worth counting.

    Empty strings and whitespace padding are recorded here because they are
    *not* missing values as far as pandas is concerned - which is exactly why
    they hide in datasets that otherwise look complete.
    """
    text = series.dropna().astype(str)
    if text.empty:
        return TextStatistics()

    # Stripped once and reused: both counts need it, and it is a full pass.
    stripped = text.str.strip()
    lengths = text.str.len()
    return TextStatistics(
        min_length=int(lengths.min()),
        max_length=int(lengths.max()),
        mean_length=_finite(lengths.mean()),
        empty_string_count=int((stripped == "").sum()),
        whitespace_padded_count=int((text != stripped).sum()),
    )


def profile_column(
    series: pd.Series, position: int, *, memory_bytes: int | None = None
) -> ColumnProfile:
    """Profile a single column.

    ``memory_bytes`` lets the caller supply a figure it has already computed.
    ``memory_usage(deep=True)`` walks every object in the column, so computing
    it per column *and* again for the frame doubled the cost of profiling a
    wide text-heavy dataset for no benefit.
    """
    row_count = len(series)
    missing_count = int(series.isna().sum())
    non_missing = row_count - missing_count
    unique_count = int(series.nunique(dropna=True))

    inferred_type, is_numeric_like = infer_column_type(series)

    profile = ColumnProfile(
        name=str(series.name),
        position=position,
        dtype=str(series.dtype),
        inferred_type=inferred_type,
        count=non_missing,
        missing_count=missing_count,
        missing_percentage=_percentage(missing_count, row_count),
        unique_count=unique_count,
        unique_percentage=_percentage(unique_count, non_missing),
        is_constant=unique_count == 1 and non_missing > 0,
        is_unique=(
            non_missing > 1 and unique_count / non_missing >= IDENTIFIER_UNIQUENESS_THRESHOLD
        ),
        is_numeric_like=is_numeric_like,
        memory_bytes=(
            int(memory_bytes) if memory_bytes is not None else int(series.memory_usage(deep=True))
        ),
        top_values=_top_values(series, non_missing),
    )

    if inferred_type.is_numeric:
        profile.numeric = _numeric_statistics(coerce_numeric(series))
    elif inferred_type is ColumnType.DATETIME:
        profile.datetime = _datetime_statistics(coerce_datetime(series))

    # Length statistics apply to anything stored as text, including a numeric-like
    # column - "0012" and "12" are the same number but different strings, and
    # that difference is a quality signal.
    if series.dtype == object or inferred_type in {ColumnType.TEXT, ColumnType.CATEGORICAL}:
        profile.text = _text_statistics(series)

    return profile


def profile_dataset(
    frame: pd.DataFrame,
    *,
    source_rows: int | None = None,
    sampled: bool = False,
    notes: list[str] | None = None,
) -> DatasetProfile:
    """Profile a whole dataset.

    ``source_rows`` is the row count of the original file, which differs from
    ``len(frame)`` when a very large file was sampled. Both are reported so
    percentages are never quietly computed against the wrong denominator.
    """
    row_count, column_count = frame.shape
    total_cells = row_count * column_count
    missing_cells = int(frame.isna().to_numpy().sum())

    duplicate_row_count = int(frame.duplicated(keep="first").sum())

    # One deep memory pass for the whole frame, shared with every column.
    column_memory = frame.memory_usage(deep=True)

    columns = [
        profile_column(frame[name], position, memory_bytes=int(column_memory.get(name, 0)))
        for position, name in enumerate(frame.columns)
    ]

    by_type: dict[ColumnType, list[str]] = {column_type: [] for column_type in ColumnType}
    for column in columns:
        by_type[column.inferred_type].append(column.name)

    profile = DatasetProfile(
        row_count=row_count,
        column_count=column_count,
        total_cells=total_cells,
        missing_cells=missing_cells,
        missing_percentage=_percentage(missing_cells, total_cells),
        duplicate_row_count=duplicate_row_count,
        duplicate_row_percentage=_percentage(duplicate_row_count, row_count),
        memory_bytes=int(column_memory.sum()),
        numeric_columns=by_type[ColumnType.NUMERIC] + by_type[ColumnType.INTEGER],
        categorical_columns=by_type[ColumnType.CATEGORICAL],
        datetime_columns=by_type[ColumnType.DATETIME],
        boolean_columns=by_type[ColumnType.BOOLEAN],
        text_columns=by_type[ColumnType.TEXT],
        empty_columns=by_type[ColumnType.EMPTY],
        columns=columns,
        sampled=sampled,
        sampled_rows=row_count if sampled else None,
        source_rows=source_rows if source_rows is not None else row_count,
        notes=list(notes or []),
    )
    logger.info(
        "Profiled dataset",
        extra={
            "rows": row_count,
            "columns": column_count,
            "missing_percentage": profile.missing_percentage,
        },
    )
    return profile


def numeric_feature_frame(frame: pd.DataFrame, profile: DatasetProfile) -> pd.DataFrame:
    """The numeric view of a dataset, for statistical tests and the ML model.

    Text columns that hold numbers are coerced so they participate; identifier
    columns are excluded, because a row is not anomalous for having a high
    primary key and including one would dominate any distance-based model.
    """
    selected: dict[str, pd.Series] = {}
    for column in profile.columns:
        if not column.inferred_type.is_numeric or column.is_constant:
            continue
        if is_identifier_like(column):
            continue
        values = coerce_numeric(frame[column.name])
        # Infinities are not usable by scikit-learn and are not real magnitudes.
        selected[column.name] = values.replace([np.inf, -np.inf], np.nan)

    return pd.DataFrame(selected, index=frame.index)


def is_identifier_like(column: ColumnProfile) -> bool:
    """True when a numeric column is a surrogate key rather than a measurement.

    The test is *integer* **and** near-perfectly unique. Uniqueness alone is the
    wrong test: a continuous float column such as a transaction amount is
    naturally almost all-distinct, and excluding it would throw away the single
    most informative feature in the dataset. A fully distinct integer column, by
    contrast, is nearly always a row id - and including one lets a model rank
    rows by how late they were inserted, which is meaningless.

    The trade-off is accepted knowingly: an integer measurement that happens to
    be perfectly unique is excluded. That is far less damaging than the reverse.
    """
    return column.is_unique and column.inferred_type is ColumnType.INTEGER
