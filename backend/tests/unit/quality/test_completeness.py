"""Missing-value and incomplete-row detectors."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.profiling import profile_dataset
from app.quality.base import DetectionContext
from app.quality.detectors.completeness import (
    MISSING_REPORTING_THRESHOLD,
    IncompleteRowDetector,
    MissingValueDetector,
    severity_for_missing,
)
from app.quality.types import FindingType, Severity


def context(frame: pd.DataFrame) -> DetectionContext:
    return DetectionContext(frame=frame, profile=profile_dataset(frame))


def frame_with_missing(rows: int, missing: int, column: str = "value") -> pd.DataFrame:
    values: list[float | None] = [1.0] * rows
    for index in range(missing):
        values[index] = None
    return pd.DataFrame({"id": range(rows), column: values})


class TestSeverityBands:
    @pytest.mark.parametrize(
        ("percentage", "expected"),
        [
            (5.0, Severity.LOW),
            (14.9, Severity.LOW),
            (15.0, Severity.MEDIUM),
            (39.9, Severity.MEDIUM),
            (40.0, Severity.HIGH),
            (79.9, Severity.HIGH),
            (80.0, Severity.CRITICAL),
            (100.0, Severity.CRITICAL),
        ],
    )
    def test_bands_are_exactly_as_documented(self, percentage: float, expected: Severity) -> None:
        assert severity_for_missing(percentage) is expected


class TestMissingValueDetector:
    detector = MissingValueDetector()

    def test_reports_nothing_for_a_complete_column(self) -> None:
        assert self.detector.detect(context(frame_with_missing(100, 0))) == []

    def test_stays_quiet_below_the_reporting_threshold(self) -> None:
        """Every real export has a few gaps; flagging them trains people to
        ignore findings."""
        findings = self.detector.detect(context(frame_with_missing(100, 4)))
        assert findings == []
        assert MISSING_REPORTING_THRESHOLD == 5.0

    def test_reports_a_column_at_the_threshold(self) -> None:
        findings = self.detector.detect(context(frame_with_missing(100, 5)))

        assert len(findings) == 1
        finding = findings[0]
        assert finding.type is FindingType.MISSING_VALUES
        assert finding.severity is Severity.LOW
        assert finding.column == "value"
        assert finding.affected_rows == 5
        assert finding.affected_percentage == pytest.approx(5.0)

    def test_escalates_severity_with_the_share_missing(self) -> None:
        assert self.detector.detect(context(frame_with_missing(100, 20)))[0].severity is (
            Severity.MEDIUM
        )
        assert self.detector.detect(context(frame_with_missing(100, 50)))[0].severity is (
            Severity.HIGH
        )
        assert self.detector.detect(context(frame_with_missing(100, 90)))[0].severity is (
            Severity.CRITICAL
        )

    def test_reports_an_entirely_empty_column_separately(self) -> None:
        frame = pd.DataFrame({"id": range(50), "blank": [np.nan] * 50})

        findings = self.detector.detect(context(frame))

        assert len(findings) == 1
        assert findings[0].type is FindingType.EMPTY_COLUMN
        assert findings[0].severity is Severity.HIGH

    def test_carries_sample_rows_so_the_user_can_jump_to_them(self) -> None:
        finding = self.detector.detect(context(frame_with_missing(100, 10)))[0]

        assert finding.sample_row_indices[:3] == [0, 1, 2]
        assert len(finding.sample_row_indices) <= 20

    def test_answers_all_five_questions(self) -> None:
        finding = self.detector.detect(context(frame_with_missing(100, 30)))[0]

        assert finding.title  # what happened
        assert finding.column  # where
        assert finding.impact  # why it matters
        assert finding.detection_method  # how
        assert finding.recommendation  # what to do


class TestIncompleteRowDetector:
    detector = IncompleteRowDetector()

    def test_reports_nothing_when_every_row_is_populated(self) -> None:
        frame = pd.DataFrame({"a": range(50), "b": range(50), "c": range(50)})
        assert self.detector.detect(context(frame)) == []

    def test_finds_rows_that_are_mostly_empty(self) -> None:
        frame = pd.DataFrame({"a": [1.0] * 50, "b": [1.0] * 50, "c": [1.0] * 50, "d": [1.0] * 50})
        frame.loc[:4, ["a", "b", "c"]] = np.nan  # 5 rows, 75% empty each

        findings = self.detector.detect(context(frame))

        assert len(findings) == 1
        assert findings[0].type is FindingType.INCOMPLETE_ROWS
        assert findings[0].affected_rows == 5
        assert findings[0].sample_row_indices[:2] == [0, 1]

    def test_ignores_rows_that_are_merely_half_empty(self) -> None:
        """The rule is *more than* half, so an evenly split row is not broken."""
        frame = pd.DataFrame({"a": [1.0] * 50, "b": [1.0] * 50})
        frame.loc[:9, "a"] = np.nan

        assert self.detector.detect(context(frame)) == []

    def test_severity_scales_with_how_many_rows_are_broken(self) -> None:
        frame = pd.DataFrame({name: [1.0] * 200 for name in "abcd"})
        frame.loc[:19, ["a", "b", "c"]] = np.nan  # 20 of 200 = 10%

        assert self.detector.detect(context(frame))[0].severity is Severity.HIGH
