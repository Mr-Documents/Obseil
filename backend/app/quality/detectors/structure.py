"""Structural detectors: columns that carry no signal, or too much of it."""

from __future__ import annotations

from app.profiling.types import ColumnType
from app.quality.base import DetectionContext, QualityDetector
from app.quality.types import DetectionMethod, FindingDraft, FindingType, Severity

#: This detector targets a narrow, specific problem: a column that is neither a
#: usable category nor a usable key. Both conditions must hold, and columns at
#: or above ``KEY_LIKE_UNIQUENESS`` are excluded because they are identifiers,
#: reported by the duplicate-identifier detector instead.
#:
#: The window matters. 311 distinct customers across 600 transactions (52%) is
#: an ordinary foreign key and is *not* flagged - flagging it would put a
#: finding on every clean dataset and teach people to ignore findings. A column
#: that is 75% distinct with hundreds of values, though, is usually
#: free-text entry masquerading as a category ("London", "london", "London ").
HIGH_CARDINALITY_MIN_DISTINCT = 50
HIGH_CARDINALITY_MIN_RATIO = 70.0


class ConstantColumnDetector(QualityDetector):
    name = "constant_column"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []

        for column in context.profile.columns:
            if not column.is_constant:
                continue

            value = column.top_values[0].value if column.top_values else "the same value"
            findings.append(
                FindingDraft(
                    type=FindingType.CONSTANT_COLUMN,
                    # Low, not high: a constant column is a waste, not a hazard.
                    # Scoring it harshly would drown out findings that corrupt
                    # actual results.
                    severity=Severity.LOW,
                    title=f"“{column.name}” never changes",
                    description=(
                        f"Every populated row of “{column.name}” holds the same value ({value})."
                    ),
                    impact=(
                        "A column with one distinct value carries no information. It cannot "
                        "explain anything in a model, and it can mask a filter or join condition "
                        "that is quietly doing nothing."
                    ),
                    recommendation=(
                        "Check whether the export was filtered to a single value by accident. If "
                        "the constant is genuine, drop the column from the extract."
                    ),
                    detection_method=DetectionMethod.DISTINCT_COUNT,
                    column=column.name,
                    affected_rows=column.count,
                    affected_percentage=context.percentage(column.count),
                    details={"constant_value": value, "distinct_values": 1},
                )
            )

        return findings


class HighCardinalityDetector(QualityDetector):
    """Categorical columns with an unusual number of distinct values."""

    name = "high_cardinality"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []

        for column in context.columns_of_type(ColumnType.CATEGORICAL, ColumnType.TEXT):
            # An identifier being all-distinct is its job, not a defect.
            if column.count == 0 or context.is_key_like(column):
                continue
            if (
                column.unique_count < HIGH_CARDINALITY_MIN_DISTINCT
                or column.unique_percentage < HIGH_CARDINALITY_MIN_RATIO
            ):
                continue

            findings.append(
                FindingDraft(
                    type=FindingType.HIGH_CARDINALITY,
                    severity=Severity.LOW,
                    title=f"“{column.name}” has {column.unique_count:,} distinct values",
                    description=(
                        f"“{column.name}” holds {column.unique_count:,} distinct values across "
                        f"{column.count:,} populated rows ({column.unique_percentage:.1f}% "
                        "distinct), which is high for a categorical column."
                    ),
                    impact=(
                        "Grouping by this column produces almost as many groups as rows, and "
                        "one-hot encoding it would add thousands of near-empty features. High "
                        "cardinality also often signals inconsistent free-text entry - "
                        "“London”, “london” and “London ” counted as three categories."
                    ),
                    recommendation=(
                        "Check for casing and spacing variants of the same value. If the values "
                        "are genuinely distinct, treat the column as an identifier or as free "
                        "text rather than as a category."
                    ),
                    detection_method=DetectionMethod.CARDINALITY_RATIO,
                    column=column.name,
                    affected_rows=column.count,
                    affected_percentage=column.unique_percentage,
                    details={
                        "distinct_values": column.unique_count,
                        "distinct_percentage": column.unique_percentage,
                        "min_distinct_threshold": HIGH_CARDINALITY_MIN_DISTINCT,
                        "min_ratio_threshold": HIGH_CARDINALITY_MIN_RATIO,
                        "most_common": [
                            {"value": entry.value, "count": entry.count}
                            for entry in column.top_values[:5]
                        ],
                    },
                )
            )

        return findings


class NumbersAsTextDetector(QualityDetector):
    """Numeric data stored as text.

    Reported as a *type* problem rather than a value problem: nothing is wrong
    with the numbers, but everything downstream will sort them alphabetically
    and refuse to sum them.
    """

    name = "numbers_as_text"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []

        for column in context.profile.columns:
            if not column.is_numeric_like:
                continue

            series = context.frame[column.name]
            from app.profiling.inference import coerce_numeric

            unparseable = series.notna() & coerce_numeric(series).isna()
            stragglers = int(unparseable.sum())

            findings.append(
                FindingDraft(
                    type=FindingType.NUMBERS_AS_TEXT,
                    severity=Severity.MEDIUM if stragglers else Severity.LOW,
                    title=f"“{column.name}” holds numbers stored as text",
                    description=(
                        f"“{column.name}” is stored as text, but its values parse as numbers"
                        + (f" - apart from {stragglers:,} that do not." if stragglers else ".")
                    ),
                    impact=(
                        "Text-typed numbers sort as strings (“10” before “9”), cannot be summed "
                        "or averaged without conversion, and are excluded from statistical "
                        "checks and models until they are cast."
                        + (
                            " The values that fail to parse will become nulls when the column is "
                            "converted, silently losing rows."
                            if stragglers
                            else ""
                        )
                    ),
                    recommendation=(
                        f"Cast “{column.name}” to a numeric type at the source."
                        + (
                            " Inspect the values that fail to parse first - they are usually "
                            "placeholder text such as “unknown” or “n/a”."
                            if stragglers
                            else ""
                        )
                    ),
                    detection_method=DetectionMethod.TYPE_INFERENCE,
                    column=column.name,
                    affected_rows=stragglers or column.count,
                    affected_percentage=context.percentage(stragglers or column.count),
                    details={
                        "storage_dtype": column.dtype,
                        "unparseable_count": stragglers,
                        "unparseable_examples": series[unparseable]
                        .astype(str)
                        .unique()[:5]
                        .tolist(),
                    },
                    sample_row_indices=self.sample_indices(unparseable),
                )
            )

        return findings
