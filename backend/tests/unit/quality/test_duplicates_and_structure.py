"""Duplicate, constant, cardinality and type-mismatch detectors."""

from __future__ import annotations

import pandas as pd

from app.profiling import profile_dataset
from app.quality.base import DetectionContext, name_declares_identifier
from app.quality.detectors.duplicates import DuplicateIdentifierDetector, DuplicateRowDetector
from app.quality.detectors.structure import (
    ConstantColumnDetector,
    HighCardinalityDetector,
    NumbersAsTextDetector,
)
from app.quality.types import FindingType, Severity


def context(frame: pd.DataFrame) -> DetectionContext:
    return DetectionContext(frame=frame, profile=profile_dataset(frame))


class TestDuplicateRows:
    detector = DuplicateRowDetector()

    def test_reports_nothing_for_distinct_rows(self) -> None:
        frame = pd.DataFrame({"a": range(50), "b": range(50)})
        assert self.detector.detect(context(frame)) == []

    def test_counts_repeats_not_occurrences(self) -> None:
        """Three identical rows are two duplicates, not three."""
        rows = [{"a": 1, "b": "x"}] * 3 + [{"a": index, "b": "y"} for index in range(2, 50)]
        frame = pd.DataFrame(rows)

        finding = self.detector.detect(context(frame))[0]

        assert finding.type is FindingType.DUPLICATE_ROWS
        assert finding.affected_rows == 2
        # ...but every copy is sampled, so the reviewer can compare them.
        assert finding.details["rows_involved"] == 3

    def test_severity_scales_with_the_share_duplicated(self) -> None:
        # 29 duplicates in 100 rows -> 29%
        heavy = pd.DataFrame([{"a": 1}] * 30 + [{"a": index} for index in range(2, 72)])
        assert self.detector.detect(context(heavy))[0].severity is Severity.CRITICAL

        # 4 duplicates in 200 rows -> 2%
        medium = pd.DataFrame([{"a": 1}] * 5 + [{"a": index} for index in range(2, 197)])
        assert self.detector.detect(context(medium))[0].severity is Severity.MEDIUM

        # 1 duplicate in 200 rows -> 0.5%: real, but not worth alarm
        light = pd.DataFrame([{"a": 1}] * 2 + [{"a": index} for index in range(2, 200)])
        assert self.detector.detect(context(light))[0].severity is Severity.LOW


class TestIdentifierNaming:
    def test_recognises_conventional_identifier_names(self) -> None:
        for name in ("id", "transaction_id", "customer_key", "order_ref", "record_uuid", "PK"):
            assert name_declares_identifier(name), name

    def test_does_not_overmatch_ordinary_names(self) -> None:
        for name in ("amount", "loyalty_points", "channel", "valid", "identity_score"):
            assert not name_declares_identifier(name), name


class TestDuplicateIdentifier:
    detector = DuplicateIdentifierDetector()

    def test_flags_a_named_key_that_repeats(self) -> None:
        ids = [f"TXN-{index:04d}" for index in range(100)]
        ids[10] = ids[0]
        ids[20] = ids[0]
        frame = pd.DataFrame({"transaction_id": ids, "amount": range(100)})

        finding = self.detector.detect(context(frame))[0]

        assert finding.type is FindingType.DUPLICATE_IDENTIFIER
        assert finding.severity is Severity.HIGH
        assert finding.column == "transaction_id"
        assert finding.affected_rows == 3  # the original and both collisions

    def test_ignores_a_categorical_column_with_repeats(self) -> None:
        """Repeated values are what a category *is*."""
        frame = pd.DataFrame({"channel": ["online", "in_store", "mobile"] * 40})
        assert self.detector.detect(context(frame)) == []

    def test_ignores_a_continuous_measurement_however_distinct(self) -> None:
        """A float column is naturally almost all-distinct; calling it a broken
        key would put a false positive on every numeric dataset."""
        frame = pd.DataFrame({"amount": [round(value * 1.37, 2) for value in range(500)]})
        frame.loc[10, "amount"] = frame.loc[0, "amount"]

        assert self.detector.detect(context(frame)) == []

    def test_ignores_a_foreign_key_with_many_legitimate_repeats(self) -> None:
        frame = pd.DataFrame({"customer_id": [f"CUST-{index % 50}" for index in range(500)]})
        assert self.detector.detect(context(frame)) == []


class TestConstantColumn:
    detector = ConstantColumnDetector()

    def test_flags_a_single_valued_column(self) -> None:
        frame = pd.DataFrame({"batch": ["v3"] * 60, "value": range(60)})

        finding = self.detector.detect(context(frame))[0]

        assert finding.type is FindingType.CONSTANT_COLUMN
        assert finding.column == "batch"
        assert finding.details["constant_value"] == "v3"

    def test_is_low_severity_because_it_is_waste_not_corruption(self) -> None:
        frame = pd.DataFrame({"batch": ["v3"] * 60})
        assert self.detector.detect(context(frame))[0].severity is Severity.LOW

    def test_ignores_a_column_that_varies(self) -> None:
        frame = pd.DataFrame({"value": ["a", "b"] * 30})
        assert self.detector.detect(context(frame)) == []


class TestHighCardinality:
    detector = HighCardinalityDetector()

    def test_ignores_an_ordinary_foreign_key(self) -> None:
        """~50% distinct is what a customer id across transactions looks like."""
        frame = pd.DataFrame({"customer_id": [f"CUST-{index % 300}" for index in range(600)]})
        assert self.detector.detect(context(frame)) == []

    def test_flags_a_column_between_a_category_and_a_key(self) -> None:
        # 75% distinct: too many values to group by, not unique enough to join on.
        values = [f"city-{index}" for index in range(150)] + [
            f"city-{index % 50}" for index in range(50)
        ]
        frame = pd.DataFrame({"city": values})

        findings = self.detector.detect(context(frame))

        assert len(findings) == 1
        assert findings[0].type is FindingType.HIGH_CARDINALITY

    def test_ignores_an_identifier(self) -> None:
        frame = pd.DataFrame({"order_id": [f"ORD-{index}" for index in range(200)]})
        assert self.detector.detect(context(frame)) == []


class TestNumbersAsText:
    detector = NumbersAsTextDetector()

    def test_flags_a_text_column_of_numbers(self) -> None:
        frame = pd.DataFrame({"points": [f"{value}" for value in range(100)]})

        finding = self.detector.detect(context(frame))[0]

        assert finding.type is FindingType.NUMBERS_AS_TEXT
        assert finding.severity is Severity.LOW

    def test_escalates_when_some_values_will_not_convert(self) -> None:
        values = [f"{value}" for value in range(100)]
        values[5] = "unknown"
        values[9] = "n/a "
        frame = pd.DataFrame({"points": values})

        finding = self.detector.detect(context(frame))[0]

        assert finding.severity is Severity.MEDIUM
        assert finding.details["unparseable_count"] == 2
        assert "unknown" in finding.details["unparseable_examples"]

    def test_ignores_a_genuinely_numeric_column(self) -> None:
        frame = pd.DataFrame({"points": range(100)})
        assert self.detector.detect(context(frame)) == []
