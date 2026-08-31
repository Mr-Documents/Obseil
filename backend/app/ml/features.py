"""Feature preparation for anomaly detection.

This is where most of the actual data science lives. Every decision below is
made once, here, so that any detector added later is compared on identical
inputs.

**On scaling.** Obseil deliberately does *not* standardise features before
fitting the Isolation Forest. The algorithm splits one feature at a time at a
threshold drawn uniformly from that feature's observed range, so it is
invariant to per-feature affine rescaling: standardising would add a step that
changes nothing while implying it matters. This is not true of distance-based
detectors — a Local Outlier Factor or DBSCAN detector added later **must**
scale, and :func:`scale_features` is provided for exactly that.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.profiling.profiler import numeric_feature_frame
from app.profiling.types import DatasetProfile

logger = logging.getLogger(__name__)

#: Multivariate anomaly detection needs at least two dimensions. With one
#: feature the model can only rediscover what the IQR rule already reports, so
#: running it would produce duplicate findings dressed up as machine learning.
MIN_FEATURES = 2

#: Below this many rows the forest has too little to isolate against, and
#: "unusual" stops meaning anything.
MIN_ROWS = 50

#: A feature missing more than this share is dropped rather than imputed:
#: filling in most of a column invents the very structure the model then finds.
MAX_FEATURE_MISSING_SHARE = 0.5


@dataclass(slots=True)
class FeatureMatrix:
    """Prepared features, plus a record of what preparation did."""

    frame: pd.DataFrame
    #: Positional indices into the original frame, one per prepared row.
    row_positions: np.ndarray
    dropped_columns: dict[str, str] = field(default_factory=dict)
    imputed_columns: dict[str, float] = field(default_factory=dict)
    #: Set when the data cannot support anomaly detection at all.
    skip_reason: str | None = None

    @property
    def usable(self) -> bool:
        return self.skip_reason is None

    @property
    def feature_names(self) -> list[str]:
        return [str(column) for column in self.frame.columns]


def prepare_features(frame: pd.DataFrame, profile: DatasetProfile) -> FeatureMatrix:
    """Turn a dataset into a numeric matrix suitable for anomaly detection.

    Steps, in order:

    1. Select numeric features — including text columns that hold numbers —
       while excluding constants (no signal) and integer surrogate keys (a row
       is not anomalous for having a high id).
    2. Drop features that are mostly missing.
    3. Impute the remaining gaps with the column **median**. The median is used
       rather than the mean because the mean is dragged by the very outliers
       the model is looking for, which would move imputed rows towards them.
    4. Refuse to run when the result is too small or too narrow to mean
       anything, recording why.
    """
    numeric = numeric_feature_frame(frame, profile)

    dropped: dict[str, str] = {}
    kept: dict[str, pd.Series] = {}
    for name in numeric.columns:
        column = numeric[name]
        missing_share = float(column.isna().mean())
        if missing_share > MAX_FEATURE_MISSING_SHARE:
            dropped[str(name)] = f"{missing_share:.0%} missing"
            continue
        kept[str(name)] = column

    if len(kept) < MIN_FEATURES:
        return FeatureMatrix(
            frame=pd.DataFrame(),
            row_positions=np.array([], dtype=int),
            dropped_columns=dropped,
            skip_reason=(
                f"Only {len(kept)} usable numeric column"
                f"{'' if len(kept) == 1 else 's'} — multivariate anomaly detection needs at "
                f"least {MIN_FEATURES}. Single-column outliers are already covered by the "
                "interquartile-range check."
            ),
        )

    prepared = pd.DataFrame(kept)

    imputed: dict[str, float] = {}
    for name in prepared.columns:
        if not prepared[name].isna().any():
            continue
        median = float(prepared[name].median())
        if not np.isfinite(median):
            median = 0.0
        prepared[name] = prepared[name].fillna(median)
        imputed[str(name)] = round(median, 6)

    # Any column that is constant *after* imputation carries no signal either.
    constant = [name for name in prepared.columns if prepared[name].nunique(dropna=False) <= 1]
    for name in constant:
        dropped[str(name)] = "constant after imputation"
    prepared = prepared.drop(columns=constant)

    if prepared.shape[1] < MIN_FEATURES:
        return FeatureMatrix(
            frame=pd.DataFrame(),
            row_positions=np.array([], dtype=int),
            dropped_columns=dropped,
            imputed_columns=imputed,
            skip_reason=(
                "Too few varying numeric columns remained after preparation for multivariate "
                "anomaly detection."
            ),
        )

    if len(prepared) < MIN_ROWS:
        return FeatureMatrix(
            frame=pd.DataFrame(),
            row_positions=np.array([], dtype=int),
            dropped_columns=dropped,
            imputed_columns=imputed,
            skip_reason=(
                f"Only {len(prepared):,} rows — anomaly detection needs at least {MIN_ROWS} "
                "before 'unusual' means anything."
            ),
        )

    logger.info(
        "Prepared anomaly features",
        extra={
            "features": prepared.shape[1],
            "rows": prepared.shape[0],
            "dropped": len(dropped),
            "imputed": len(imputed),
        },
    )
    return FeatureMatrix(
        frame=prepared.reset_index(drop=True),
        row_positions=np.arange(len(prepared)),
        dropped_columns=dropped,
        imputed_columns=imputed,
    )


def scale_features(features: pd.DataFrame) -> pd.DataFrame:
    """Robustly scale features to a comparable range.

    Not used by the Isolation Forest — see this module's docstring — but
    required by any distance-based detector added later. Median and IQR are
    used rather than mean and standard deviation because the latter are pulled
    by the outliers the detector exists to find.
    """
    median = features.median()
    spread = features.quantile(0.75) - features.quantile(0.25)
    # A zero IQR would divide by zero; fall back to a unit scale for that column.
    spread = spread.replace(0, np.nan).fillna(1.0)
    return (features - median) / spread


def robust_deviations(features: pd.DataFrame, *, subset: np.ndarray | None = None) -> pd.DataFrame:
    """How far each value sits from its column's centre, in IQR units.

    Used to say *which values stood out* for an anomalous row. This is a
    descriptive statement about the data, not an attribution of the model's
    decision - the Isolation Forest does not expose one, and pretending
    otherwise would be a false claim about what the model knows.

    ``subset`` restricts the rows returned while still centring and scaling
    against the **whole** column, so the numbers are identical to computing it
    for every row - just without doing so for the 98% nobody will look at.
    """
    median = features.median()
    spread = (features.quantile(0.75) - features.quantile(0.25)).replace(0, np.nan).fillna(1.0)
    rows = features if subset is None else features.iloc[subset]
    return ((rows - median) / spread).abs()
