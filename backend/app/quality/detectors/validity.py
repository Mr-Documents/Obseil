"""Validity detectors: values that are the wrong *kind* of thing.

Distinct from the outlier detector, which finds values that are merely far from
the rest. A negative item count is not unusual — it is impossible.

The hard part is doing this **without inventing domain rules**. Obseil does not
know what your columns mean, so it never asserts a business rule it cannot
justify from the data in front of it. Each detector below states the evidence
it used, and the finding can be marked a false positive — which is exactly what
the feedback store is for.
"""

from __future__ import annotations

import pandas as pd

from app.profiling.inference import coerce_numeric
from app.profiling.types import ColumnType
from app.quality.base import DetectionContext, QualityDetector
from app.quality.types import DetectionMethod, FindingDraft, FindingType, Severity

#: Column names that unambiguously denote a non-negative quantity. This is a
#: *supporting* signal only: it is never sufficient on its own, and it is
#: deliberately short. Words like "balance", "change" or "score" are excluded
#: because negatives are perfectly normal for them.
NON_NEGATIVE_NAME_HINTS = (
    "amount",
    "total",
    "price",
    "cost",
    "quantity",
    "qty",
    "count",
    "age",
    "weight",
    "height",
    "length",
    "duration",
    "distance",
    "volume",
    "units",
    "items",
)

#: A column must be at least this non-negative before a handful of negatives
#: reads as an error rather than as the column's normal range.
NEGATIVE_MAX_SHARE = 5.0

#: Unparseable values above this share mean the column is not a date column at
#: all, so reporting "invalid dates" would be the wrong diagnosis.
MAX_UNPARSEABLE_DATE_SHARE = 30.0


def _name_suggests_non_negative(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in NON_NEGATIVE_NAME_HINTS)


class NegativeValueDetector(QualityDetector):
    """Negative values in a column that is otherwise non-negative.

    Two independent pieces of evidence are required, and the finding says which
    ones applied:

    1. Negatives are a *small minority* (< 5%). A column that is 40% negative
       has a legitimate negative range.
    2. Either the column name denotes a quantity that cannot be negative, or
       the column is integer-valued — counts far more often than measurements.

    Requiring both keeps a profit-and-loss column from being flagged just
    because it is mostly positive.
    """

    name = "negative_values"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        if not context.has_enough_rows_for_distribution_rules:
            return []

        findings: list[FindingDraft] = []

        for column in context.numeric_columns:
            if column.numeric is None or column.numeric.negative_count == 0 or column.count == 0:
                continue

            negative_share = column.numeric.negative_count / column.count * 100
            if negative_share >= NEGATIVE_MAX_SHARE:
                continue

            name_hint = _name_suggests_non_negative(column.name)
            integer_hint = column.inferred_type is ColumnType.INTEGER
            if not (name_hint or integer_hint):
                continue

            values = coerce_numeric(context.frame[column.name])
            negatives = values.notna() & (values < 0)
            count = int(negatives.sum())
            percentage = context.percentage(count)

            evidence = []
            if name_hint:
                evidence.append("the column name denotes a quantity that cannot be negative")
            if integer_hint:
                evidence.append("the column holds whole numbers, which usually means a count")

            findings.append(
                FindingDraft(
                    type=FindingType.NEGATIVE_VALUES,
                    severity=Severity.HIGH if negative_share < 1 else Severity.MEDIUM,
                    title=f"{count:,} negative values in “{column.name}”",
                    description=(
                        f"{count:,} of {column.count:,} populated values in “{column.name}” are "
                        f"negative ({negative_share:.2f}%), ranging down to "
                        f"{float(values[negatives].min()):,.4g}."
                    ),
                    impact=(
                        "If these should be non-negative, every sum and average over the column "
                        "is understated, and any filter assuming positive values silently drops "
                        "or mis-sorts them."
                    ),
                    recommendation=(
                        "Inspect the sampled rows. Negatives in an otherwise non-negative column "
                        "are usually reversals, refunds or sign errors that belong in a separate "
                        "field. If they are expected here, mark this finding as a false positive."
                    ),
                    detection_method=DetectionMethod.SIGN_CHECK,
                    column=column.name,
                    affected_rows=count,
                    affected_percentage=percentage,
                    details={
                        "negative_count": count,
                        "negative_share_of_column": round(negative_share, 4),
                        "minimum_value": round(float(values[negatives].min()), 6),
                        "evidence": evidence,
                        "max_share_threshold": NEGATIVE_MAX_SHARE,
                    },
                    sample_row_indices=self.sample_indices(negatives),
                )
            )

        return findings


class InvalidDateDetector(QualityDetector):
    """Values in a date column that are not dates.

    Only runs on columns the profiler already inferred to be dates, which
    requires 95% of values to parse. That gate is what makes the leftovers
    meaningful: they are the exceptions in a column that is otherwise clearly a
    date, not evidence that the column was never a date at all.
    """

    name = "invalid_dates"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []

        for column in context.columns_of_type(ColumnType.DATETIME):
            series = context.frame[column.name]
            # A native datetime column cannot contain an unparseable value.
            if pd.api.types.is_datetime64_any_dtype(series):
                continue

            parsed = pd.to_datetime(series.astype(str).str.strip(), errors="coerce", format="mixed")
            invalid = series.notna() & parsed.isna()
            count = int(invalid.sum())
            if count == 0:
                continue

            share_of_column = count / max(column.count, 1) * 100
            if share_of_column > MAX_UNPARSEABLE_DATE_SHARE:
                continue

            examples = series[invalid].astype(str).str.strip().unique()[:5].tolist()
            findings.append(
                FindingDraft(
                    type=FindingType.INVALID_DATES,
                    severity=Severity.MEDIUM if share_of_column < 5 else Severity.HIGH,
                    title=f"{count:,} unparseable dates in “{column.name}”",
                    description=(
                        f"“{column.name}” reads as a date column, but {count:,} values "
                        f"({share_of_column:.2f}% of those present) cannot be parsed as one. "
                        f"Examples: {', '.join(repr(value) for value in examples)}."
                    ),
                    impact=(
                        "These values become nulls the moment the column is converted to a date "
                        "type, so the rows drop out of any time filter, trend or join without "
                        "warning."
                    ),
                    recommendation=(
                        "Fix the malformed values at the source, or standardise on ISO-8601 "
                        "(YYYY-MM-DD) in the export. Note that impossible dates such as "
                        "“2026-13-45” and ambiguous ones such as “31/02/2026” both land here."
                    ),
                    detection_method=DetectionMethod.DATE_PARSING,
                    column=column.name,
                    affected_rows=count,
                    affected_percentage=context.percentage(count),
                    details={
                        "unparseable_count": count,
                        "share_of_populated_values": round(share_of_column, 4),
                        "examples": examples,
                    },
                    sample_row_indices=self.sample_indices(invalid),
                )
            )

        return findings


class StringHygieneDetector(QualityDetector):
    """Empty strings and whitespace padding.

    Both matter precisely because pandas does *not* treat them as missing: a
    column can be reported as 100% complete while a tenth of its values are
    `""` or `"  "`.
    """

    name = "string_hygiene"

    #: Below this share these are typos, not a systemic problem.
    MIN_SHARE = 1.0

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []

        for column in context.profile.columns:
            if column.text is None:
                continue

            series = context.frame[column.name]
            text = series.dropna().astype(str)
            if text.empty:
                continue

            findings.extend(
                self._empty_strings(context, column.name, series, column.text.empty_string_count)
            )
            findings.extend(
                self._padding(context, column.name, series, column.text.whitespace_padded_count)
            )

        return findings

    def _empty_strings(
        self, context: DetectionContext, name: str, series: pd.Series, count: int
    ) -> list[FindingDraft]:
        if count == 0:
            return []
        percentage = context.percentage(count)
        if percentage < self.MIN_SHARE:
            return []

        mask = series.notna() & (series.astype(str).str.strip() == "")
        return [
            FindingDraft(
                type=FindingType.EMPTY_STRINGS,
                severity=Severity.MEDIUM,
                title=f"{count:,} blank values in “{name}” are not recorded as missing",
                description=(
                    f"{count:,} rows ({percentage:.1f}%) hold an empty or whitespace-only string "
                    f"in “{name}”. These are not counted as nulls, so the column reports as more "
                    "complete than it is."
                ),
                impact=(
                    "Completeness metrics, null checks and imputation all skip these values. A "
                    "blank string also groups as its own category, splitting counts that should "
                    "sit under “unknown”."
                ),
                recommendation=(
                    "Convert empty and whitespace-only strings to genuine nulls at ingest, so "
                    "there is one representation of “no value”."
                ),
                detection_method=DetectionMethod.STRING_INSPECTION,
                column=name,
                affected_rows=count,
                affected_percentage=percentage,
                details={"empty_string_count": count},
                sample_row_indices=self.sample_indices(mask),
            )
        ]

    def _padding(
        self, context: DetectionContext, name: str, series: pd.Series, count: int
    ) -> list[FindingDraft]:
        if count == 0:
            return []
        percentage = context.percentage(count)
        if percentage < self.MIN_SHARE:
            return []

        as_text = series.dropna().astype(str)
        mask = series.notna() & (series.astype(str) != series.astype(str).str.strip())
        examples = as_text[as_text != as_text.str.strip()].unique()[:5].tolist()

        return [
            FindingDraft(
                type=FindingType.WHITESPACE_PADDING,
                severity=Severity.LOW,
                title=f"{count:,} values in “{name}” have leading or trailing spaces",
                description=(
                    f"{count:,} rows ({percentage:.1f}%) in “{name}” are padded with whitespace. "
                    f"Examples: {', '.join(repr(value) for value in examples)}."
                ),
                impact=(
                    "“London ” and “London” are different values to every join, group-by and "
                    "equality filter, so counts split across variants that look identical on "
                    "screen."
                ),
                recommendation=(
                    "Trim whitespace at ingest, before the values are used as keys or "
                    "categories."
                ),
                detection_method=DetectionMethod.STRING_INSPECTION,
                column=name,
                affected_rows=count,
                affected_percentage=percentage,
                details={"padded_count": count, "examples": examples},
                sample_row_indices=self.sample_indices(mask),
            )
        ]
