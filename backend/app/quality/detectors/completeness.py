"""Missing-value detectors.

Three distinct problems live here, and they are genuinely different:

* a column with *some* values missing — usually fixable
* a column with *no* values at all — carries no information
* a *row* with most of its fields missing — a broken record, invisible to any
  per-column check because each individual column may look fine
"""

from __future__ import annotations

from app.profiling.types import ColumnType
from app.quality.base import MAX_SAMPLE_ROWS, DetectionContext, QualityDetector
from app.quality.types import DetectionMethod, FindingDraft, FindingType, Severity

#: Missingness severity bands, as (threshold percentage, severity). Read
#: top-down: the first band whose threshold is met wins.
#:
#: The boundaries are not arbitrary:
#:   <5%   list-wise deletion costs little and most tools cope — not reported
#:   >=5%  low      joins and aggregates no longer cover every row
#:   >=15% medium   dropping incomplete rows now removes a meaningful share,
#:                  and imputing would visibly change the distribution
#:   >=40% high     statistics over the remainder describe a subset, and
#:                  imputation invents more than it recovers
#:   >=80% critical the column is effectively absent
MISSING_SEVERITY_BANDS: tuple[tuple[float, Severity], ...] = (
    (80.0, Severity.CRITICAL),
    (40.0, Severity.HIGH),
    (15.0, Severity.MEDIUM),
    (5.0, Severity.LOW),
)

#: Below this, a column with a handful of gaps is not reported at all. Every
#: real export has a few, and flagging them trains people to ignore findings.
MISSING_REPORTING_THRESHOLD = 5.0

#: A row missing more than this share of its fields is a broken record.
INCOMPLETE_ROW_THRESHOLD = 0.5


def severity_for_missing(percentage: float) -> Severity:
    for threshold, severity in MISSING_SEVERITY_BANDS:
        if percentage >= threshold:
            return severity
    return Severity.LOW


class MissingValueDetector(QualityDetector):
    name = "missing_values"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []

        for column in context.profile.columns:
            if column.inferred_type is ColumnType.EMPTY:
                findings.append(self._empty_column(column.name, context))
                continue

            if column.missing_percentage < MISSING_REPORTING_THRESHOLD:
                continue

            severity = severity_for_missing(column.missing_percentage)
            findings.append(
                FindingDraft(
                    type=FindingType.MISSING_VALUES,
                    severity=severity,
                    title=f"“{column.name}” is {column.missing_percentage:.1f}% empty",
                    description=(
                        f"{column.missing_count:,} of {context.row_count:,} rows have no value "
                        f"for “{column.name}”."
                    ),
                    impact=self._impact(severity, column.name),
                    recommendation=self._recommendation(severity, column.name),
                    detection_method=DetectionMethod.NULL_COUNT,
                    column=column.name,
                    affected_rows=column.missing_count,
                    affected_percentage=column.missing_percentage,
                    details={
                        "missing_count": column.missing_count,
                        "present_count": column.count,
                        "severity_bands": {
                            str(threshold): band.value for threshold, band in MISSING_SEVERITY_BANDS
                        },
                    },
                    sample_row_indices=self.sample_indices(context.frame[column.name].isna()),
                )
            )

        return findings

    @staticmethod
    def _empty_column(name: str, context: DetectionContext) -> FindingDraft:
        return FindingDraft(
            type=FindingType.EMPTY_COLUMN,
            severity=Severity.HIGH,
            title=f"“{name}” contains no values at all",
            description=(f"Every one of the {context.row_count:,} rows is empty for “{name}”."),
            impact=(
                "The column contributes nothing to any analysis, and its presence can make a "
                "dataset look richer than it is."
            ),
            recommendation=(
                "Check whether the export dropped this field. If it is genuinely unused, remove "
                "it from the extract."
            ),
            detection_method=DetectionMethod.NULL_COUNT,
            column=name,
            affected_rows=context.row_count,
            affected_percentage=100.0,
        )

    @staticmethod
    def _impact(severity: Severity, name: str) -> str:
        if severity is Severity.CRITICAL:
            return (
                f"Almost nothing is populated, so “{name}” cannot support any analysis. Grouping "
                "or filtering by it would silently drop nearly every row."
            )
        if severity is Severity.HIGH:
            return (
                f"More than half of “{name}” is absent. Statistics computed over the remaining "
                "rows describe a subset, not the dataset, and any model using it will be trained "
                "on a biased sample."
            )
        if severity is Severity.MEDIUM:
            return (
                f"Dropping incomplete rows would remove a meaningful share of the data, and "
                f"imputing “{name}” would change its distribution."
            )
        return (
            f"A small share of “{name}” is absent. Usually harmless, but joins and aggregations "
            "over this column will not cover every row."
        )

    @staticmethod
    def _recommendation(severity: Severity, name: str) -> str:
        if severity in {Severity.CRITICAL, Severity.HIGH}:
            return (
                f"Find out why “{name}” is not being populated upstream before using it. If the "
                "gap is expected, exclude the column rather than imputing it."
            )
        if severity is Severity.MEDIUM:
            return (
                "Decide explicitly between dropping the incomplete rows and imputing, and record "
                "which you chose — the two give different answers."
            )
        return (
            "Confirm the gaps are expected, then handle them consistently wherever the "
            "column is used."
        )


class IncompleteRowDetector(QualityDetector):
    """Rows that are mostly empty.

    Deliberately separate from the column check: a row missing 8 of its 11
    fields can sit in a dataset where no individual column looks bad.
    """

    name = "incomplete_rows"

    def detect(self, context: DetectionContext) -> list[FindingDraft]:
        if context.profile.column_count == 0 or context.row_count == 0:
            return []

        missing_share = context.frame.isna().mean(axis=1)
        broken = missing_share > INCOMPLETE_ROW_THRESHOLD
        count = int(broken.sum())
        if count == 0:
            return []

        percentage = context.percentage(count)
        severity = (
            Severity.HIGH
            if percentage >= 5
            else Severity.MEDIUM if percentage >= 1 else Severity.LOW
        )

        return [
            FindingDraft(
                type=FindingType.INCOMPLETE_ROWS,
                severity=severity,
                title=f"{count:,} rows are more than half empty",
                description=(
                    f"{count:,} of {context.row_count:,} rows ({percentage:.1f}%) have no value in "
                    f"more than {INCOMPLETE_ROW_THRESHOLD:.0%} of their columns."
                ),
                impact=(
                    "These records carry almost no information but still count towards row totals, "
                    "inflating volume metrics and diluting any average computed across the dataset."
                ),
                recommendation=(
                    "Inspect the sampled rows. A cluster of them usually points at a failed batch "
                    "or a partial export rather than at genuinely sparse records."
                ),
                detection_method=DetectionMethod.ROW_COMPLETENESS,
                affected_rows=count,
                affected_percentage=percentage,
                details={
                    "threshold": INCOMPLETE_ROW_THRESHOLD,
                    "worst_row_missing_share": round(float(missing_share.max()) * 100, 2),
                },
                sample_row_indices=self.sample_indices(broken, MAX_SAMPLE_ROWS),
            )
        ]
