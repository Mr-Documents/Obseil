"""Univariate outlier detection.

Two classical methods, and the one that was used is always reported — "12
outliers" means nothing until you know where the line was drawn.

**IQR (Tukey's fences)** — the primary method. Values outside
``[Q1 - k·IQR, Q3 + k·IQR]``. Quartiles are rank statistics, so the fences are
not themselves dragged outwards by the extreme values they exist to find. That
robustness is why this is the default.

**Z-score** — reported alongside as a cross-check, never as the decision. It
assumes roughly normal data, and its mean and standard deviation are *not*
robust: a handful of extreme values inflates the standard deviation and hides
the very points being looked for. It is included because it is the method most
people expect to see, and showing both makes the difference visible.

**Skew correction.** Tukey's fences assume a roughly symmetric distribution.
Applied directly to a right-skewed column — transaction amounts, durations,
counts, almost anything money-shaped — they flag several percent of perfectly
ordinary values, because the upper fence sits inside a long, legitimate tail.
For a strongly skewed, non-negative column the fences are therefore computed on
``log1p(x)`` and mapped back with ``expm1``. This is the standard remedy, it is
recorded in the finding's details, and it is the difference between a detector
people trust and one they learn to ignore.

Neither method claims a value is *wrong*. An outlier is a value far from the
rest of its column, and may be entirely legitimate — the finding says so.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.profiling.inference import coerce_numeric
from app.quality.base import DetectionContext, QualityDetector
from app.quality.types import DetectionMethod, FindingDraft, FindingType, Severity

#: Tukey's multiplier. 1.5 is the conventional "mild outlier" fence; 3.0 marks
#: "far out" points. Both are reported so a reviewer can see which band a
#: column's outliers fall into.
IQR_MULTIPLIER = 1.5
IQR_EXTREME_MULTIPLIER = 3.0

#: Conventional z-score cut-off, kept only as a cross-check.
Z_SCORE_THRESHOLD = 3.0

#: Above this absolute skewness, the raw fences stop being trustworthy and the
#: log-scale fences are used instead. 1.0 is the usual "strongly skewed" line.
SKEW_CORRECTION_THRESHOLD = 1.0

#: Below this share, outliers are not worth a finding: in any real-world
#: distribution a few points sit outside Tukey's fences by construction.
MIN_OUTLIER_PERCENTAGE = 0.5

#: Above this share the "outliers" *are* the distribution — a heavy tail, not a
#: defect — and reporting them as a problem would be misleading.
MAX_OUTLIER_PERCENTAGE = 25.0

#: Fewer values than this and quartiles are too unstable to fence with.
MIN_VALUES_FOR_FENCES = 20


def iqr_bounds(values: pd.Series, multiplier: float = IQR_MULTIPLIER) -> tuple[float, float]:
    """Lower and upper Tukey fences for ``values``."""
    q1 = float(values.quantile(0.25))
    q3 = float(values.quantile(0.75))
    spread = q3 - q1
    return q1 - multiplier * spread, q3 + multiplier * spread


def should_use_log_scale(values: pd.Series) -> bool:
    """True when the column is strongly right-skewed and non-negative.

    Both conditions are required: ``log1p`` is undefined below -1, and a
    symmetric column gains nothing from the transform.
    """
    if len(values) < 3 or float(values.min()) < 0:
        return False
    skew = float(values.skew())
    return np.isfinite(skew) and skew > SKEW_CORRECTION_THRESHOLD


def fences_for(values: pd.Series, multiplier: float, *, log_scale: bool) -> tuple[float, float]:
    """Tukey fences on the raw or log scale, always returned in raw units."""
    if not log_scale:
        return iqr_bounds(values, multiplier)
    lower, upper = iqr_bounds(np.log1p(values), multiplier)
    return float(np.expm1(lower)), float(np.expm1(upper))


def z_score_outlier_count(values: pd.Series, threshold: float = Z_SCORE_THRESHOLD) -> int:
    """How many values sit more than ``threshold`` standard deviations from the mean."""
    std = float(values.std(ddof=1))
    if not np.isfinite(std) or std == 0:
        return 0
    return int((((values - float(values.mean())) / std).abs() > threshold).sum())


class OutlierDetector(QualityDetector):
    name = "outliers"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        if not context.has_enough_rows_for_distribution_rules:
            return []

        findings: list[FindingDraft] = []

        for column in context.numeric_columns:
            if column.is_constant or context.is_key_like(column):
                continue

            values = coerce_numeric(context.frame[column.name]).replace([np.inf, -np.inf], np.nan)
            clean = values.dropna()
            if len(clean) < MIN_VALUES_FOR_FENCES:
                continue

            log_scale = should_use_log_scale(clean)
            lower, upper = fences_for(clean, IQR_MULTIPLIER, log_scale=log_scale)
            if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
                # A zero IQR means at least half the values are identical;
                # the fences collapse and would flag everything else.
                continue

            outlier_mask = values.notna() & ((values < lower) | (values > upper))
            count = int(outlier_mask.sum())
            if count == 0:
                continue

            percentage = context.percentage(count)
            if percentage < MIN_OUTLIER_PERCENTAGE or percentage > MAX_OUTLIER_PERCENTAGE:
                continue

            extreme_lower, extreme_upper = fences_for(
                clean, IQR_EXTREME_MULTIPLIER, log_scale=log_scale
            )
            extreme_count = int(
                (values.notna() & ((values < extreme_lower) | (values > extreme_upper))).sum()
            )

            severity = (
                Severity.HIGH
                if extreme_count and percentage >= 2
                else Severity.MEDIUM if extreme_count or percentage >= 5 else Severity.LOW
            )

            outlier_values = values[outlier_mask].dropna()
            scale_note = (
                " The column is strongly right-skewed, so the fences were computed on a "
                "log scale — on the raw scale a long but legitimate tail would be flagged."
                if log_scale
                else ""
            )

            findings.append(
                FindingDraft(
                    type=FindingType.OUTLIERS,
                    severity=severity,
                    title=f"{count:,} outlying values in “{column.name}”",
                    description=(
                        f"{count:,} of {context.row_count:,} values ({percentage:.1f}%) fall "
                        f"outside the interquartile fences [{lower:,.4g}, {upper:,.4g}]"
                        + (
                            f", of which {extreme_count:,} are beyond the far-out fence "
                            f"({IQR_EXTREME_MULTIPLIER}x IQR)."
                            if extreme_count
                            else "."
                        )
                        + scale_note
                    ),
                    impact=(
                        "Means, standard deviations and any model fitted on this column are "
                        "pulled towards the extremes. If the values are data-entry errors or "
                        "unit mix-ups, every aggregate over this column is wrong; if they are "
                        "genuine, they still need handling deliberately rather than by accident."
                    ),
                    recommendation=(
                        "Look at the sampled rows and decide whether these are errors or real "
                        "extremes. If they are real, prefer robust statistics (median, IQR) or "
                        "an explicit cap over silently dropping them."
                    ),
                    detection_method=DetectionMethod.IQR,
                    column=column.name,
                    affected_rows=count,
                    affected_percentage=percentage,
                    details={
                        "method": "Tukey's fences",
                        "multiplier": IQR_MULTIPLIER,
                        "scale": "log1p" if log_scale else "raw",
                        "skewness": round(float(clean.skew()), 4),
                        "lower_bound": round(lower, 6),
                        "upper_bound": round(upper, 6),
                        "extreme_multiplier": IQR_EXTREME_MULTIPLIER,
                        "extreme_count": extreme_count,
                        "min_outlier_value": round(float(outlier_values.min()), 6),
                        "max_outlier_value": round(float(outlier_values.max()), 6),
                        "median": round(float(clean.median()), 6),
                        # The cross-check: a large gap between the two counts is
                        # itself informative about the shape of the column.
                        "z_score_threshold": Z_SCORE_THRESHOLD,
                        "z_score_outlier_count": z_score_outlier_count(clean),
                    },
                    sample_row_indices=self.sample_indices(outlier_mask),
                )
            )

        return findings
