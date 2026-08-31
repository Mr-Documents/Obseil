"""Isolation Forest detection, thresholding, and the anomaly finding.

The load-bearing test here is
``test_finds_every_injected_multivariate_anomaly``: the fixture's twelve rows
are unremarkable in every individual column, so the deterministic engine
reports nothing on them. If the model does not find them, the ML component is
decoration.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.detectors.isolation_forest import (
    MAX_ANOMALY_SHARE,
    MODIFIED_Z_CUTOFF,
    IsolationForestDetector,
    modified_z_scores,
)
from app.ml.engine import anomaly_finding, detect_anomalies
from app.ml.features import prepare_features
from app.profiling import profile_dataset
from app.quality import FindingCategory, FindingType, Severity, run_detectors
from tests.fixtures import load_sample


def structured_frame(rows: int = 400, seed: int = 3) -> pd.DataFrame:
    """Correlated data: amount tracks basket size, points track age."""
    rng = np.random.default_rng(seed)
    items = rng.integers(1, 12, rows)
    age = rng.integers(18, 80, rows)
    return pd.DataFrame(
        {
            "amount": np.round(items * rng.uniform(6, 9, rows), 2),
            "items": items,
            "age": age,
            "points": np.round((age - 18) * 60 + rng.normal(0, 200, rows)).clip(0),
        }
    )


class TestThresholding:
    def test_modified_z_scores_are_zero_for_identical_scores(self) -> None:
        assert modified_z_scores(np.full(50, 0.5)).tolist() == [0.0] * 50

    def test_modified_z_scores_are_robust_to_the_extremes_themselves(self) -> None:
        scores = np.concatenate([np.full(99, 0.5), [5.0]])
        result = modified_z_scores(scores)

        assert result[-1] > MODIFIED_Z_CUTOFF
        assert (np.abs(result[:-1]) < 1e-9).all()

    def test_never_flags_more_than_the_ceiling(self) -> None:
        """Anomalies are rare by definition; a list of 300 is a list nobody reads."""
        frame = structured_frame(rows=500)
        features = prepare_features(frame, profile_dataset(frame))

        result = IsolationForestDetector(max_anomaly_share=1.0).detect(features.frame)

        assert result.anomaly_count <= 5
        assert MAX_ANOMALY_SHARE == 2.0

    def test_an_explicit_contamination_rate_is_honoured(self) -> None:
        frame = structured_frame(rows=400)
        features = prepare_features(frame, profile_dataset(frame))

        result = IsolationForestDetector(contamination=0.05, max_anomaly_share=100).detect(
            features.frame
        )

        assert result.parameters["threshold_rule"] == "explicit contamination rate"
        assert result.anomaly_count == pytest.approx(20, abs=3)


class TestDetection:
    def test_is_reproducible_for_a_fixed_seed(self) -> None:
        frame = structured_frame()
        features = prepare_features(frame, profile_dataset(frame))

        first = IsolationForestDetector().detect(features.frame)
        second = IsolationForestDetector().detect(features.frame)

        assert [row.row_index for row in first.anomalies] == [
            row.row_index for row in second.anomalies
        ]

    def test_reports_the_features_it_used(self) -> None:
        frame = structured_frame()
        result = detect_anomalies(frame, profile_dataset(frame))

        assert result.ran
        assert set(result.features) == {"amount", "items", "age", "points"}

    def test_does_not_standardise_and_says_why(self) -> None:
        """Isolation Forest is invariant to per-feature rescaling; a scaling
        step would change nothing while implying that it matters."""
        frame = structured_frame()
        result = detect_anomalies(frame, profile_dataset(frame))

        assert result.parameters["scaled"] is False
        assert "invariant" in str(result.parameters["scaling_note"])

    def test_anomalies_are_ordered_most_unusual_first(self) -> None:
        frame = structured_frame()
        result = detect_anomalies(frame, profile_dataset(frame))

        scores = [row.raw_score for row in result.anomalies]
        assert scores == sorted(scores, reverse=True)

    def test_each_anomaly_carries_its_values_and_what_stood_out(self) -> None:
        frame = structured_frame()
        result = detect_anomalies(frame, profile_dataset(frame))
        assert result.anomaly_count > 0

        row = result.anomalies[0]
        assert set(row.feature_values) == set(result.features)
        assert 0 <= row.anomaly_score <= 100
        assert row.top_contributors
        assert {"feature", "value", "deviation_iqr"} == set(row.top_contributors[0])

    def test_skips_gracefully_when_the_data_cannot_support_it(self) -> None:
        frame = pd.DataFrame({"amount": [1.0, 2.0, 3.0], "label": ["a", "b", "c"]})

        result = detect_anomalies(frame, profile_dataset(frame))

        assert result.ran is False
        assert result.reason
        assert result.anomaly_count == 0


class TestAgainstTheSampleDatasets:
    def test_finds_every_injected_multivariate_anomaly(self) -> None:
        """The twelve rows in the fixture are ordinary in every single column -
        the deterministic engine reports nothing on this file - but each is a
        one-item basket priced like ten, bought by an 18-year-old with a
        maximal loyalty balance. Finding them is the entire case for the ML
        component."""
        frame = load_sample("anomalous_transactions.csv")
        profile = profile_dataset(frame)

        assert run_detectors(frame, profile) == [], "no rule fires on this fixture"

        result = detect_anomalies(frame, profile)
        flagged = {row.row_index for row in result.anomalies}

        # The injected rows are identifiable by their signature: one item, a
        # high amount, a young customer and a large loyalty balance.
        injected = frame.index[
            (frame["items"] == 1)
            & (frame["customer_age"] <= 20)
            & (frame["loyalty_points"] >= 4200)
        ]
        assert len(injected) == 12, "fixture integrity"
        assert set(injected).issubset(flagged), "every injected anomaly must be found"

    def test_flags_only_a_small_share_of_a_clean_dataset(self) -> None:
        """A handful of candidates on clean data is expected - unsupervised
        detection has no ground truth - but it must stay a handful."""
        frame = load_sample("clean_transactions.csv")
        result = detect_anomalies(frame, profile_dataset(frame))

        assert result.anomaly_rate <= MAX_ANOMALY_SHARE


class TestAnomalyFinding:
    def test_summarises_a_run_as_one_finding(self) -> None:
        frame = load_sample("anomalous_transactions.csv")
        result = detect_anomalies(frame, profile_dataset(frame))

        finding = anomaly_finding(result, len(frame))

        assert finding is not None
        assert finding.type is FindingType.ML_ANOMALY
        assert finding.category is FindingCategory.ANOMALY, "kept distinct from rule findings"
        assert finding.affected_rows == result.anomaly_count

    def test_never_claims_to_know_why(self) -> None:
        frame = load_sample("anomalous_transactions.csv")
        finding = anomaly_finding(detect_anomalies(frame, profile_dataset(frame)), 700)

        assert finding is not None
        assert "not necessarily wrong" in finding.description
        assert "does not know why" in str(finding.details["note"])

    def test_severity_never_exceeds_high(self) -> None:
        """An anomaly is a candidate for review, not an established defect."""
        frame = load_sample("anomalous_transactions.csv")
        finding = anomaly_finding(detect_anomalies(frame, profile_dataset(frame)), 700)

        assert finding is not None
        assert finding.severity.rank <= Severity.HIGH.rank

    def test_returns_nothing_when_detection_was_skipped(self) -> None:
        frame = pd.DataFrame({"amount": [1.0, 2.0, 3.0]})
        result = detect_anomalies(frame, profile_dataset(frame))

        assert anomaly_finding(result, 3) is None
