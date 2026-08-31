"""Outlier and validity detectors."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.profiling import profile_dataset
from app.quality.base import DetectionContext
from app.quality.detectors.outliers import (
    OutlierDetector,
    iqr_bounds,
    should_use_log_scale,
    z_score_outlier_count,
)
from app.quality.detectors.validity import (
    InvalidDateDetector,
    NegativeValueDetector,
    StringHygieneDetector,
)
from app.quality.types import DetectionMethod, FindingType, Severity


def context(frame: pd.DataFrame) -> DetectionContext:
    return DetectionContext(frame=frame, profile=profile_dataset(frame))


class TestIqrMaths:
    def test_bounds_match_the_textbook_definition(self) -> None:
        values = pd.Series(range(1, 101))
        lower, upper = iqr_bounds(values)

        q1, q3 = float(values.quantile(0.25)), float(values.quantile(0.75))
        assert lower == pytest.approx(q1 - 1.5 * (q3 - q1))
        assert upper == pytest.approx(q3 + 1.5 * (q3 - q1))

    def test_z_score_count_is_zero_for_a_constant_column(self) -> None:
        assert z_score_outlier_count(pd.Series([5.0] * 50)) == 0

    def test_log_scale_is_used_only_for_skewed_non_negative_columns(self) -> None:
        rng = np.random.default_rng(0)
        assert should_use_log_scale(pd.Series(rng.lognormal(3, 0.9, 500))) is True
        assert should_use_log_scale(pd.Series(rng.normal(100, 10, 500))) is False
        # log1p is undefined below -1, so a signed column never takes this path.
        assert should_use_log_scale(pd.Series(rng.normal(0, 50, 500))) is False


class TestOutlierDetector:
    detector = OutlierDetector()

    def test_stays_silent_on_a_small_dataset(self) -> None:
        """Quartiles over a dozen rows are noise; a confident finding derived
        from them would be worse than silence."""
        frame = pd.DataFrame({"value": [1, 2, 3, 4, 5, 900]})
        assert self.detector.detect(context(frame)) == []

    def test_finds_injected_extremes_in_a_symmetric_column(self) -> None:
        rng = np.random.default_rng(7)
        values = list(rng.normal(100, 10, 300))
        values[5] = 900.0
        values[9] = -700.0
        frame = pd.DataFrame({"value": values})

        finding = self.detector.detect(context(frame))[0]

        assert finding.type is FindingType.OUTLIERS
        assert finding.detection_method is DetectionMethod.IQR
        assert 5 in finding.sample_row_indices
        assert 9 in finding.sample_row_indices

    def test_does_not_flag_the_tail_of_a_skewed_column_as_a_defect(self) -> None:
        """Raw Tukey fences flag several percent of any log-normal column. That
        is the distribution, not a problem, and reporting it would make the
        detector useless on real money data."""
        rng = np.random.default_rng(11)
        frame = pd.DataFrame({"amount": np.round(rng.lognormal(3.1, 0.75, 800), 2)})

        assert self.detector.detect(context(frame)) == []

    def test_still_finds_genuine_extremes_in_a_skewed_column(self) -> None:
        rng = np.random.default_rng(11)
        amounts = np.round(rng.lognormal(3.1, 0.75, 800), 2)
        amounts[:10] = 90_000.0
        frame = pd.DataFrame({"amount": amounts})

        finding = self.detector.detect(context(frame))[0]

        assert finding.details["scale"] == "log1p"
        # The ten injected values, plus whatever genuine tail sits beyond the
        # log-scale fence — the point is that all ten are caught.
        assert set(range(10)).issubset(finding.sample_row_indices)
        assert finding.affected_rows >= 10

    def test_reports_the_method_and_the_bounds_it_used(self) -> None:
        rng = np.random.default_rng(3)
        values = list(rng.normal(50, 5, 300))
        values[0] = 500.0
        frame = pd.DataFrame({"value": values})

        details = self.detector.detect(context(frame))[0].details

        assert details["method"] == "Tukey's fences"
        assert details["multiplier"] == 1.5
        assert "lower_bound" in details and "upper_bound" in details
        # The z-score cross-check is reported but is not the decision.
        assert "z_score_outlier_count" in details

    def test_skips_a_column_where_half_the_values_are_identical(self) -> None:
        """A zero IQR collapses the fences and would flag everything else."""
        frame = pd.DataFrame({"value": [0] * 200 + list(range(1, 51))})
        findings = [f for f in self.detector.detect(context(frame)) if f.column == "value"]
        assert findings == []

    def test_ignores_the_distribution_when_a_quarter_of_it_is_outside(self) -> None:
        """At that point the 'outliers' are the distribution."""
        # 100 of 300 values sit far from the rest: a third of the column.
        frame = pd.DataFrame({"value": [1] * 100 + [1000] * 100 + [2] * 100})
        assert self.detector.detect(context(frame)) == []


class TestNegativeValues:
    detector = NegativeValueDetector()

    def test_flags_negatives_in_a_named_quantity_column(self) -> None:
        values = [10.0] * 200
        values[3] = -5.0
        frame = pd.DataFrame({"amount": values})

        finding = self.detector.detect(context(frame))[0]

        assert finding.type is FindingType.NEGATIVE_VALUES
        assert finding.affected_rows == 1
        assert any("name" in reason for reason in finding.details["evidence"])

    def test_flags_negatives_in_an_integer_count_column(self) -> None:
        values = list(range(1, 201))
        values[7] = -1
        frame = pd.DataFrame({"widgets": values})

        findings = self.detector.detect(context(frame))

        assert len(findings) == 1
        assert any("whole numbers" in reason for reason in findings[0].details["evidence"])

    def test_does_not_flag_a_column_with_a_legitimate_negative_range(self) -> None:
        """A profit-and-loss column is mostly positive but genuinely signed;
        flagging it would be an unjustified domain assumption."""
        rng = np.random.default_rng(5)
        frame = pd.DataFrame({"amount": rng.normal(100, 200, 500)})

        assert self.detector.detect(context(frame)) == []

    def test_does_not_flag_an_unnamed_continuous_column(self) -> None:
        values = [1.5] * 200
        values[0] = -1.5
        frame = pd.DataFrame({"reading": values})

        assert self.detector.detect(context(frame)) == []


class TestInvalidDates:
    detector = InvalidDateDetector()

    def test_flags_unparseable_values_in_a_date_column(self) -> None:
        dates = [f"2026-01-{day:02d}" for day in range(1, 29)] * 4
        dates[3] = "not-a-date"
        dates[10] = "2026-13-45"
        frame = pd.DataFrame({"transaction_date": dates})

        finding = self.detector.detect(context(frame))[0]

        assert finding.type is FindingType.INVALID_DATES
        assert finding.affected_rows == 2
        assert "not-a-date" in finding.details["examples"]

    def test_reports_nothing_when_every_date_parses(self) -> None:
        frame = pd.DataFrame({"day": [f"2026-01-{day:02d}" for day in range(1, 29)]})
        assert self.detector.detect(context(frame)) == []

    def test_ignores_a_native_datetime_column(self) -> None:
        """A parsed datetime column cannot contain an unparseable value."""
        frame = pd.DataFrame({"day": pd.date_range("2026-01-01", periods=60)})
        assert self.detector.detect(context(frame)) == []


class TestStringHygiene:
    detector = StringHygieneDetector()

    def test_flags_blank_strings_that_are_not_counted_as_missing(self) -> None:
        values = ["alpha"] * 100
        for index in range(5):
            values[index] = "   "
        frame = pd.DataFrame({"category": values})

        findings = [
            finding
            for finding in self.detector.detect(context(frame))
            if finding.type is FindingType.EMPTY_STRINGS
        ]

        assert len(findings) == 1
        assert findings[0].affected_rows == 5
        assert findings[0].severity is Severity.MEDIUM

    def test_flags_whitespace_padding(self) -> None:
        values = ["london"] * 100
        for index in range(8):
            values[index] = "london "
        frame = pd.DataFrame({"city": values})

        findings = [
            finding
            for finding in self.detector.detect(context(frame))
            if finding.type is FindingType.WHITESPACE_PADDING
        ]

        assert len(findings) == 1
        assert findings[0].severity is Severity.LOW

    def test_ignores_a_handful_of_stray_values(self) -> None:
        values = ["clean"] * 1000
        values[0] = "clean "
        frame = pd.DataFrame({"city": values})

        assert self.detector.detect(context(frame)) == []
