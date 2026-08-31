"""The quality score."""

from __future__ import annotations

import pytest

from app.ml import anomaly_finding, detect_anomalies
from app.profiling import profile_dataset
from app.quality import run_detectors
from app.quality.scoring import (
    DIMENSION_CAPS,
    SEVERITY_WEIGHTS,
    QualityDimension,
    QualityGrade,
    calculate_quality_score,
    coverage_multiplier,
    finding_penalty,
    grade_for,
)
from app.quality.types import DetectionMethod, FindingDraft, FindingType, Severity
from tests.fixtures import load_sample


def draft(
    finding_type: FindingType = FindingType.MISSING_VALUES,
    severity: Severity = Severity.MEDIUM,
    affected_percentage: float | None = 50.0,
) -> FindingDraft:
    return FindingDraft(
        type=finding_type,
        severity=severity,
        title="t",
        description="d",
        impact="i",
        recommendation="r",
        detection_method=DetectionMethod.NULL_COUNT,
        affected_percentage=affected_percentage,
    )


class TestCoverage:
    def test_spans_half_to_one_and_a_half(self) -> None:
        assert coverage_multiplier(0) == pytest.approx(0.5)
        assert coverage_multiplier(50) == pytest.approx(1.0)
        assert coverage_multiplier(100) == pytest.approx(1.5)

    def test_clamps_out_of_range_input(self) -> None:
        assert coverage_multiplier(-10) == pytest.approx(0.5)
        assert coverage_multiplier(500) == pytest.approx(1.5)

    def test_defaults_to_mid_range_when_unknown(self) -> None:
        assert coverage_multiplier(None) == pytest.approx(1.0)


class TestPenalties:
    def test_severity_dominates_coverage(self) -> None:
        """A critical issue in 5% of rows must outrank a low issue in all of
        them, or the score would reward triviality."""
        critical_narrow = finding_penalty(draft(severity=Severity.CRITICAL, affected_percentage=5))
        low_universal = finding_penalty(draft(severity=Severity.LOW, affected_percentage=100))

        assert critical_narrow > low_universal

    def test_wider_coverage_costs_more_at_equal_severity(self) -> None:
        assert finding_penalty(draft(affected_percentage=90)) > finding_penalty(
            draft(affected_percentage=5)
        )

    def test_weights_are_strictly_ordered(self) -> None:
        weights = [SEVERITY_WEIGHTS[severity] for severity in Severity]
        assert weights == sorted(weights)


class TestGrades:
    @pytest.mark.parametrize(
        ("score", "grade"),
        [
            (100, QualityGrade.EXCELLENT),
            (95, QualityGrade.EXCELLENT),
            (94.9, QualityGrade.GOOD),
            (80, QualityGrade.GOOD),
            (79.9, QualityGrade.NEEDS_ATTENTION),
            (60, QualityGrade.NEEDS_ATTENTION),
            (59.9, QualityGrade.POOR),
            (40, QualityGrade.POOR),
            (39.9, QualityGrade.CRITICAL),
            (0, QualityGrade.CRITICAL),
        ],
    )
    def test_bands_are_exactly_as_documented(self, score: float, grade: QualityGrade) -> None:
        assert grade_for(score) is grade


class TestCalculation:
    def test_a_dataset_with_no_findings_scores_full_marks(self) -> None:
        result = calculate_quality_score([])

        assert result.score == 100.0
        assert result.grade is QualityGrade.EXCELLENT
        assert result.total_penalty == 0.0

    def test_the_score_is_never_negative(self) -> None:
        findings = [
            draft(finding_type, Severity.CRITICAL, 100.0)
            for finding_type in (
                FindingType.MISSING_VALUES,
                FindingType.DUPLICATE_ROWS,
                FindingType.NEGATIVE_VALUES,
                FindingType.CONSTANT_COLUMN,
                FindingType.OUTLIERS,
                FindingType.ML_ANOMALY,
            )
        ] * 20

        assert calculate_quality_score(findings).score == 0.0

    def test_a_dataset_broken_in_every_dimension_can_reach_zero(self) -> None:
        """The caps sum to more than 100 for exactly this reason."""
        assert sum(DIMENSION_CAPS.values()) > 100

    def test_a_dimension_cannot_exceed_its_cap(self) -> None:
        findings = [draft(FindingType.MISSING_VALUES, Severity.CRITICAL, 100.0)] * 10

        result = calculate_quality_score(findings)
        completeness = next(
            dimension
            for dimension in result.dimensions
            if dimension.dimension is QualityDimension.COMPLETENESS
        )

        assert completeness.capped is True
        assert completeness.penalty == DIMENSION_CAPS[QualityDimension.COMPLETENESS]
        assert completeness.raw_penalty > completeness.penalty

    def test_one_noisy_dimension_cannot_sink_the_whole_score(self) -> None:
        findings = [draft(FindingType.CONSTANT_COLUMN, Severity.LOW, 100.0)] * 40

        assert calculate_quality_score(findings).score >= 90

    def test_reports_every_dimension_including_the_clean_ones(self) -> None:
        result = calculate_quality_score([draft()])
        assert len(result.dimensions) == len(QualityDimension)

    def test_lists_the_most_expensive_findings_first(self) -> None:
        findings = [
            draft(FindingType.CONSTANT_COLUMN, Severity.LOW, 5.0),
            draft(FindingType.MISSING_VALUES, Severity.CRITICAL, 95.0),
            draft(FindingType.OUTLIERS, Severity.MEDIUM, 50.0),
        ]

        contributors = calculate_quality_score(findings).top_contributors

        assert contributors[0].severity is Severity.CRITICAL
        assert [item.penalty for item in contributors] == sorted(
            (item.penalty for item in contributors), reverse=True
        )

    def test_the_derivation_adds_up(self) -> None:
        """Every number shown to the user must reconcile with the headline."""
        findings = [
            draft(FindingType.MISSING_VALUES, Severity.HIGH, 60.0),
            draft(FindingType.DUPLICATE_ROWS, Severity.MEDIUM, 10.0),
            draft(FindingType.OUTLIERS, Severity.LOW, 2.0),
        ]

        result = calculate_quality_score(findings)

        assert result.total_penalty == pytest.approx(
            sum(dimension.penalty for dimension in result.dimensions), abs=0.05
        )
        assert result.score == pytest.approx(100 - result.total_penalty, abs=0.05)

    def test_ml_anomalies_are_weighted_lightly(self) -> None:
        """They are candidates for review, not established defects."""
        anomaly = calculate_quality_score([draft(FindingType.ML_ANOMALY, Severity.HIGH, 100.0)])
        duplicates = calculate_quality_score(
            [draft(FindingType.DUPLICATE_ROWS, Severity.HIGH, 100.0)]
        )

        assert anomaly.score > duplicates.score


class TestAgainstTheSampleDatasets:
    """The score must rank the fixtures the way a person would."""

    def score_for(self, name: str) -> float:
        frame = load_sample(name)
        profile = profile_dataset(frame)
        findings = run_detectors(frame, profile)
        ml = anomaly_finding(detect_anomalies(frame, profile), profile.row_count)
        if ml is not None:
            findings.append(ml)
        return calculate_quality_score(findings).score

    def test_the_clean_dataset_scores_excellent(self) -> None:
        assert self.score_for("clean_transactions.csv") >= 95

    def test_the_missing_values_dataset_needs_attention(self) -> None:
        assert 40 <= self.score_for("missing_values.csv") < 80

    def test_the_invalid_values_dataset_needs_attention(self) -> None:
        assert 40 <= self.score_for("invalid_values.csv") < 80

    def test_a_dataset_with_only_anomalies_still_scores_well(self) -> None:
        """Its structure is sound; some rows are worth a look. Punishing it
        would tell the user that ML candidates are defects."""
        assert self.score_for("anomalous_transactions.csv") >= 90

    def test_the_ranking_matches_intuition(self) -> None:
        clean = self.score_for("clean_transactions.csv")
        outliers = self.score_for("outliers.csv")
        invalid = self.score_for("invalid_values.csv")

        assert clean > outliers > invalid
