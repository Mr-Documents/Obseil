"""The detection engine, and what it produces for each sample dataset.

These are the tests that keep the detectors honest as a *suite*. A detector
that fires on everything passes its own unit tests perfectly well; only running
the whole engine against a known-clean dataset catches it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.profiling import profile_dataset
from app.quality.base import DetectionContext, QualityDetector
from app.quality.engine import run_detectors, severity_counts
from app.quality.registry import DETECTORS
from app.quality.types import FindingDraft, FindingType, Severity
from tests.fixtures import load_sample


def findings_for(name: str) -> list[FindingDraft]:
    frame = load_sample(name)
    return run_detectors(frame, profile_dataset(frame))


def types_in(findings: list[FindingDraft]) -> set[FindingType]:
    return {finding.type for finding in findings}


class TestEngine:
    def test_sorts_most_severe_first(self) -> None:
        findings = findings_for("invalid_values.csv")
        ranks = [finding.severity.rank for finding in findings]
        assert ranks == sorted(ranks, reverse=True)

    def test_a_failing_detector_does_not_lose_the_others(self) -> None:
        """A broken check - very likely a contributed one - must not cost the
        user every other finding in their dataset."""

        class Exploding(QualityDetector):
            name = "exploding"

            def detect(self, context: DetectionContext) -> list[FindingDraft]:
                raise RuntimeError("boom")

        frame = load_sample("missing_values.csv")
        findings = run_detectors(frame, profile_dataset(frame), detectors=(Exploding(), *DETECTORS))

        assert findings, "the surviving detectors still reported"

    def test_severity_counts_include_zeros(self) -> None:
        counts = severity_counts([])
        assert counts == dict.fromkeys(Severity, 0)

    def test_handles_a_single_row_dataset_without_raising(self) -> None:
        frame = pd.DataFrame({"a": [1], "b": ["x"]})
        assert run_detectors(frame, profile_dataset(frame)) is not None

    def test_handles_an_all_null_dataset(self) -> None:
        frame = pd.DataFrame({"a": [None] * 50, "b": [None] * 50})
        findings = run_detectors(frame, profile_dataset(frame))
        assert FindingType.EMPTY_COLUMN in types_in(findings)


class TestAgainstTheSampleDatasets:
    """Each fixture must produce what its README says it is designed to produce.

    Both directions matter: the right detector fires, *and* the others stay
    quiet. See ``data/samples/README.md``.
    """

    def test_the_clean_dataset_produces_no_findings_at_all(self) -> None:
        assert findings_for("clean_transactions.csv") == []

    def test_the_missing_values_dataset_hits_every_severity_band(self) -> None:
        findings = findings_for("missing_values.csv")
        by_column = {
            finding.column: finding
            for finding in findings
            if finding.type is FindingType.MISSING_VALUES
        }

        assert by_column["promo_code"].severity is Severity.CRITICAL
        assert by_column["loyalty_points"].severity is Severity.HIGH
        assert by_column["customer_age"].severity is Severity.MEDIUM
        assert by_column["country"].severity is Severity.LOW

    def test_the_missing_values_dataset_finds_the_broken_rows(self) -> None:
        findings = findings_for("missing_values.csv")
        incomplete = next(f for f in findings if f.type is FindingType.INCOMPLETE_ROWS)
        assert incomplete.affected_rows == 12

    def test_the_duplicate_dataset_reports_both_kinds_of_duplication(self) -> None:
        findings = findings_for("duplicate_records.csv")

        rows = next(f for f in findings if f.type is FindingType.DUPLICATE_ROWS)
        assert rows.affected_rows == 40

        key = next(f for f in findings if f.type is FindingType.DUPLICATE_IDENTIFIER)
        assert key.column == "transaction_id"

    def test_the_outlier_dataset_finds_exactly_the_injected_extremes(self) -> None:
        findings = findings_for("outliers.csv")
        by_column = {f.column: f for f in findings if f.type is FindingType.OUTLIERS}

        assert by_column["amount"].affected_rows == 15
        assert by_column["customer_age"].affected_rows == 8

    def test_the_invalid_values_dataset_reports_each_defect(self) -> None:
        findings = findings_for("invalid_values.csv")
        found = types_in(findings)

        assert FindingType.NEGATIVE_VALUES in found
        assert FindingType.INVALID_DATES in found
        assert FindingType.EMPTY_STRINGS in found
        assert FindingType.WHITESPACE_PADDING in found
        assert FindingType.NUMBERS_AS_TEXT in found
        assert FindingType.CONSTANT_COLUMN in found

    def test_the_invalid_values_dataset_finds_both_negative_columns(self) -> None:
        findings = findings_for("invalid_values.csv")
        negatives = {
            f.column: f.affected_rows for f in findings if f.type is FindingType.NEGATIVE_VALUES
        }
        assert negatives == {"amount": 18, "items": 9}

    def test_the_anomaly_dataset_produces_no_rule_findings(self) -> None:
        """This is the whole argument for having an ML component: twelve rows
        are implausible in combination, and no per-column rule can see them."""
        assert findings_for("anomalous_transactions.csv") == []


@pytest.mark.parametrize(
    "name",
    [
        "clean_transactions.csv",
        "missing_values.csv",
        "duplicate_records.csv",
        "outliers.csv",
        "invalid_values.csv",
        "anomalous_transactions.csv",
    ],
)
def test_every_finding_answers_all_five_questions(name: str) -> None:
    for finding in findings_for(name):
        assert finding.title, f"{name}: missing title"
        assert finding.description, f"{name}: missing description"
        assert finding.impact, f"{name}: missing impact"
        assert finding.recommendation, f"{name}: missing recommendation"
        assert finding.detection_method, f"{name}: missing detection method"
