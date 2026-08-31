"""Semantic type inference.

pandas gives us a storage dtype. What the quality engine needs is what the
column *means*: a column of ``"12.50"`` strings is numeric data that happens to
be stored as text, and a 3-value ``object`` column across 50,000 rows is a
category rather than free text.

Every threshold below is a deliberate, documented choice rather than a magic
number, and each is exported so tests and the documentation can reference it.
"""

from __future__ import annotations

import pandas as pd
from pandas.api import types as pdt

from app.profiling.types import ColumnType

#: A text column is treated as numeric-like when at least this share of its
#: non-missing values parse as numbers. Below this, a few stray numerals in a
#: free-text field would produce false positives.
NUMERIC_LIKE_THRESHOLD = 0.95

#: Likewise for dates. Date parsing is far more permissive than number parsing,
#: so the bar is set higher.
DATETIME_LIKE_THRESHOLD = 0.95

#: An object column is "categorical" when it has few distinct values relative
#: to its length. Both conditions must hold: 40 categories in 50 rows is not a
#: category, and 5,000 categories in 10,000 rows is not either.
CATEGORICAL_MAX_UNIQUE_RATIO = 0.5
CATEGORICAL_MAX_UNIQUE_ABSOLUTE = 50

#: Values accepted as booleans in a text column, lower-cased.
BOOLEAN_TOKENS: set[str] = {
    "true",
    "false",
    "yes",
    "no",
    "y",
    "n",
    "t",
    "f",
    "1",
    "0",
    "on",
    "off",
}

#: Sampling ceiling for the parse-based probes. Inference does not need to see
#: every row, and this keeps profiling a very wide file fast.
INFERENCE_SAMPLE_SIZE = 5_000


def _sample(series: pd.Series) -> pd.Series:
    """A deterministic, bounded sample of the non-missing values."""
    values = series.dropna()
    if len(values) > INFERENCE_SAMPLE_SIZE:
        return values.sample(INFERENCE_SAMPLE_SIZE, random_state=0)
    return values


def numeric_parse_ratio(series: pd.Series) -> float:
    """Share of non-missing values that parse as a number."""
    values = _sample(series)
    if values.empty:
        return 0.0
    parsed = pd.to_numeric(values.astype(str).str.strip(), errors="coerce")
    return float(parsed.notna().mean())


def datetime_parse_ratio(series: pd.Series) -> float:
    """Share of non-missing values that parse as a date/time."""
    values = _sample(series)
    if values.empty:
        return 0.0
    # format="mixed" lets pandas infer per value instead of forcing one layout,
    # which is what real exports look like.
    parsed = pd.to_datetime(values.astype(str).str.strip(), errors="coerce", format="mixed")
    return float(parsed.notna().mean())


def looks_boolean(series: pd.Series) -> bool:
    """True when every non-missing value is one of a small boolean vocabulary."""
    values = _sample(series)
    if values.empty:
        return False
    tokens = set(values.astype(str).str.strip().str.lower().unique())
    if not tokens or not tokens.issubset(BOOLEAN_TOKENS):
        return False
    # "0"/"1" alone is ambiguous - that is a numeric flag, and calling it
    # boolean would suppress genuinely useful numeric statistics.
    return not tokens.issubset({"0", "1"})


def infer_column_type(series: pd.Series) -> tuple[ColumnType, bool]:
    """Infer the semantic type of ``series``.

    Returns the type and whether it is a *text* column holding numbers, which
    the quality engine reports as a separate finding.
    """
    non_missing = series.dropna()
    if non_missing.empty:
        return ColumnType.EMPTY, False

    if pdt.is_bool_dtype(series):
        return ColumnType.BOOLEAN, False
    if pdt.is_datetime64_any_dtype(series):
        return ColumnType.DATETIME, False
    if pdt.is_numeric_dtype(series):
        # A float column of whole numbers is still integer-valued data; saying
        # so makes "negative count where a count is impossible" checks sharper.
        is_integral = pdt.is_integer_dtype(series) or bool((non_missing % 1 == 0).all())
        return (ColumnType.INTEGER if is_integral else ColumnType.NUMERIC), False

    if isinstance(series.dtype, pd.CategoricalDtype):
        return ColumnType.CATEGORICAL, False

    # Object dtype: probe what the strings actually contain.
    if looks_boolean(non_missing):
        return ColumnType.BOOLEAN, False

    if numeric_parse_ratio(non_missing) >= NUMERIC_LIKE_THRESHOLD:
        return ColumnType.NUMERIC, True

    if datetime_parse_ratio(non_missing) >= DATETIME_LIKE_THRESHOLD:
        return ColumnType.DATETIME, False

    unique_count = int(non_missing.nunique(dropna=True))
    ratio = unique_count / len(non_missing)
    if unique_count <= CATEGORICAL_MAX_UNIQUE_ABSOLUTE and ratio <= CATEGORICAL_MAX_UNIQUE_RATIO:
        return ColumnType.CATEGORICAL, False

    return ColumnType.TEXT, False


def coerce_numeric(series: pd.Series) -> pd.Series:
    """Best-effort numeric view of a column, for statistics and ML features."""
    if pdt.is_numeric_dtype(series) and not pdt.is_bool_dtype(series):
        return series
    return pd.to_numeric(series.astype(str).str.strip(), errors="coerce")


def coerce_datetime(series: pd.Series) -> pd.Series:
    """Best-effort datetime view of a column."""
    if pdt.is_datetime64_any_dtype(series):
        return series
    return pd.to_datetime(series.astype(str).str.strip(), errors="coerce", format="mixed")
