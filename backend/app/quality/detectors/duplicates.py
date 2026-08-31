"""Duplicate detectors.

Two different failures, deliberately reported separately:

* **Duplicate rows** — the same record appears more than once. Every count,
  sum and average over the dataset is inflated.
* **Duplicate identifiers** — a column that is otherwise a key repeats a value.
  Row counts are fine; joins are not.
"""

from __future__ import annotations

from app.quality.base import DetectionContext, QualityDetector
from app.quality.types import DetectionMethod, FindingDraft, FindingType, Severity

#: Duplicate-row severity bands, as (percentage threshold, severity).
DUPLICATE_SEVERITY_BANDS: tuple[tuple[float, Severity], ...] = (
    (20.0, Severity.CRITICAL),
    (5.0, Severity.HIGH),
    (1.0, Severity.MEDIUM),
    (0.0, Severity.LOW),
)


def severity_for_duplicates(percentage: float) -> Severity:
    """First band whose threshold is exceeded wins.

    Any duplicate at all is at least low severity.
    """
    for threshold, severity in DUPLICATE_SEVERITY_BANDS:
        if percentage > threshold:
            return severity
    return Severity.LOW


class DuplicateRowDetector(QualityDetector):
    name = "duplicate_rows"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        count = context.profile.duplicate_row_count
        if count == 0:
            return []

        percentage = context.profile.duplicate_row_percentage
        severity = severity_for_duplicates(percentage)
        # `keep=False` marks every copy, including the first, which is what a
        # reviewer wants to look at — showing only the later copies hides the
        # original they need to compare against.
        all_copies = context.frame.duplicated(keep=False)

        return [
            FindingDraft(
                type=FindingType.DUPLICATE_ROWS,
                severity=severity,
                title=f"{count:,} duplicated rows",
                description=(
                    f"{count:,} of {context.row_count:,} rows ({percentage:.1f}%) are "
                    "byte-for-byte repeats of an earlier row across every column."
                ),
                impact=(
                    "Counts, sums and averages are all inflated by the repeats. A revenue total "
                    "computed from this dataset would be overstated."
                ),
                recommendation=(
                    "Confirm whether the duplication comes from the export (a re-run appended "
                    "instead of replacing) or is genuine. If it is an artefact, de-duplicate at "
                    "the source rather than in every downstream query."
                ),
                detection_method=DetectionMethod.EXACT_ROW_MATCH,
                affected_rows=count,
                affected_percentage=percentage,
                details={
                    "unique_rows": context.row_count - count,
                    "rows_involved": int(all_copies.sum()),
                },
                sample_row_indices=self.sample_indices(all_copies),
            )
        ]


class DuplicateIdentifierDetector(QualityDetector):
    """Repeated values in a column that is otherwise a key.

    Only key-like columns are considered — see ``DetectionContext.is_key_like``.
    Without that gate, every low-cardinality categorical column would be
    reported as having "duplicates", which is simply what a category is.
    """

    name = "duplicate_identifier"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []

        for column in context.profile.columns:
            if column.count == 0 or not context.is_key_like(column):
                continue

            duplicated_values = column.count - column.unique_count
            if duplicated_values <= 0:
                continue

            series = context.frame[column.name]
            repeated = series.duplicated(keep=False) & series.notna()
            affected = int(repeated.sum())
            percentage = context.percentage(affected)
            repeated_examples = series[repeated].value_counts().head(5).index.astype(str).tolist()

            findings.append(
                FindingDraft(
                    type=FindingType.DUPLICATE_IDENTIFIER,
                    severity=Severity.HIGH,
                    title=f"“{column.name}” looks like an identifier but repeats values",
                    description=(
                        f"“{column.name}” is {column.unique_percentage:.1f}% distinct, so it reads "
                        f"as a key — but {affected:,} rows share a value with another row."
                    ),
                    impact=(
                        "Any join on this column will fan out, silently multiplying rows. "
                        "Deduplication that assumes the column is unique will drop real records."
                    ),
                    recommendation=(
                        f"Check whether “{column.name}” is meant to be unique. If it is, the "
                        "repeats indicate a broken upstream key; if it is not, do not use it to "
                        "join or de-duplicate."
                    ),
                    detection_method=DetectionMethod.UNIQUENESS_CHECK,
                    column=column.name,
                    affected_rows=affected,
                    affected_percentage=percentage,
                    details={
                        "distinct_values": column.unique_count,
                        "non_missing_values": column.count,
                        "repeated_examples": repeated_examples,
                    },
                    sample_row_indices=self.sample_indices(repeated),
                )
            )

        return findings
