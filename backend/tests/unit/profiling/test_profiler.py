"""The profiling engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.profiling.profiler import numeric_feature_frame, profile_column, profile_dataset
from app.profiling.types import ColumnType
from tests.fixtures import clean_frame, load_sample


class TestColumnProfile:
    def test_counts_missing_values(self) -> None:
        profile = profile_column(pd.Series([1.0, np.nan, 3.0, np.nan], name="amount"), 0)

        assert profile.count == 2
        assert profile.missing_count == 2
        assert profile.missing_percentage == 50.0

    def test_counts_unique_values_against_non_missing(self) -> None:
        """The denominator matters: 2 distinct values in 3 present values is
        67% unique, not 50% of the four rows."""
        profile = profile_column(pd.Series(["a", "b", "a", np.nan], name="category"), 0)

        assert profile.unique_count == 2
        assert profile.unique_percentage == pytest.approx(66.6667, abs=1e-3)

    def test_detects_a_constant_column(self) -> None:
        assert profile_column(pd.Series(["v3"] * 50, name="batch"), 0).is_constant is True

    def test_an_all_missing_column_is_not_constant(self) -> None:
        profile = profile_column(pd.Series([np.nan] * 10, name="blank"), 0)
        assert profile.is_constant is False
        assert profile.inferred_type is ColumnType.EMPTY

    def test_detects_a_candidate_identifier(self) -> None:
        profile = profile_column(pd.Series([f"TXN-{i}" for i in range(500)], name="id"), 0)
        assert profile.is_unique is True

    def test_a_low_cardinality_column_is_not_an_identifier(self) -> None:
        assert profile_column(pd.Series(["a", "b"] * 50, name="flag"), 0).is_unique is False


class TestStatisticsAreTypeAppropriate:
    def test_numeric_columns_get_numeric_statistics(self) -> None:
        profile = profile_column(pd.Series([1.0, 2.0, 3.0, 4.0, 100.0], name="amount"), 0)

        assert profile.numeric is not None
        assert profile.numeric.mean == pytest.approx(22.0)
        assert profile.numeric.median == pytest.approx(3.0)
        assert profile.numeric.minimum == 1.0
        assert profile.numeric.maximum == 100.0
        assert profile.numeric.q1 is not None and profile.numeric.q3 is not None
        assert profile.numeric.iqr == pytest.approx(profile.numeric.q3 - profile.numeric.q1)

    def test_categorical_columns_get_no_numeric_statistics(self) -> None:
        """A mean over categories is noise dressed up as insight."""
        profile = profile_column(pd.Series(["a", "b", "c"] * 20, name="category"), 0)

        assert profile.numeric is None
        assert profile.datetime is None

    def test_datetime_columns_get_a_range_not_a_mean(self) -> None:
        profile = profile_column(
            pd.Series(pd.date_range("2026-01-01", periods=31, freq="D"), name="day"), 0
        )

        assert profile.numeric is None
        assert profile.datetime is not None
        assert profile.datetime.range_days == pytest.approx(30.0)

    def test_zero_and_negative_counts_are_recorded(self) -> None:
        profile = profile_column(pd.Series([-5.0, 0.0, 0.0, 7.0], name="balance"), 0)

        assert profile.numeric is not None
        assert profile.numeric.zero_count == 2
        assert profile.numeric.negative_count == 1

    def test_standard_deviation_of_a_single_value_is_zero_not_nan(self) -> None:
        profile = profile_column(pd.Series([42.0], name="single"), 0)
        assert profile.numeric is not None
        assert profile.numeric.std == 0.0

    def test_infinite_statistics_become_null_rather_than_invalid_json(self) -> None:
        profile = profile_column(pd.Series([1.0, np.inf, 3.0], name="ratio"), 0)
        assert profile.numeric is not None
        assert profile.numeric.maximum is None


class TestTextStatistics:
    def test_counts_empty_strings_that_pandas_does_not_see_as_missing(self) -> None:
        profile = profile_column(pd.Series(["a", "", "   ", "b"], name="label"), 0)

        assert profile.missing_count == 0, "pandas reads '' as a value, not as NaN"
        assert profile.text is not None
        assert profile.text.empty_string_count == 2

    def test_counts_whitespace_padded_values(self) -> None:
        profile = profile_column(pd.Series(["ok", " padded", "trailing "], name="label"), 0)
        assert profile.text is not None
        assert profile.text.whitespace_padded_count == 2


class TestTopValues:
    def test_returns_the_most_frequent_values_with_shares(self) -> None:
        profile = profile_column(pd.Series(["a"] * 7 + ["b"] * 3, name="category"), 0)

        assert profile.top_values[0].value == "a"
        assert profile.top_values[0].count == 7
        assert profile.top_values[0].percentage == pytest.approx(70.0)

    def test_is_capped(self) -> None:
        profile = profile_column(pd.Series([f"v{i}" for i in range(100)], name="wide"), 0)
        assert len(profile.top_values) <= 10


class TestDatasetProfile:
    def test_reports_shape_and_missing_cells(self) -> None:
        frame = clean_frame(50)
        frame.loc[:9, "amount"] = np.nan

        profile = profile_dataset(frame)

        assert profile.row_count == 50
        assert profile.column_count == 5
        assert profile.total_cells == 250
        assert profile.missing_cells == 10
        assert profile.missing_percentage == pytest.approx(4.0)

    def test_counts_duplicate_rows_keeping_the_first(self) -> None:
        row = {"a": 1, "b": "x"}
        frame = pd.DataFrame([row, row, row, {"a": 2, "b": "y"}])

        profile = profile_dataset(frame)

        assert profile.duplicate_row_count == 2, "three identical rows are two duplicates"
        assert profile.duplicate_row_percentage == pytest.approx(50.0)

    def test_groups_columns_by_inferred_type(self) -> None:
        profile = profile_dataset(clean_frame(60))

        assert set(profile.numeric_columns) == {"id", "amount"}
        assert profile.categorical_columns == ["category"]
        assert profile.boolean_columns == ["active"]
        assert profile.datetime_columns == ["created_at"]

    def test_records_sampling_so_percentages_are_never_misread(self) -> None:
        profile = profile_dataset(clean_frame(100), source_rows=1_000_000, sampled=True)

        assert profile.sampled is True
        assert profile.sampled_rows == 100
        assert profile.source_rows == 1_000_000

    def test_serialises_to_json_safe_output(self) -> None:
        frame = clean_frame(20)
        frame.loc[0, "amount"] = np.inf
        frame.loc[1, "amount"] = np.nan

        payload = profile_dataset(frame).model_dump(mode="json")

        import json

        json.dumps(payload)  # must not raise on NaN/Infinity

    def test_round_trips_through_its_own_schema(self) -> None:
        from app.profiling.types import DatasetProfile

        original = profile_dataset(clean_frame(30))
        restored = DatasetProfile.model_validate(original.model_dump(mode="json"))

        assert restored.row_count == original.row_count
        assert [c.name for c in restored.columns] == [c.name for c in original.columns]


class TestNumericFeatureFrame:
    def test_includes_only_usable_numeric_columns(self) -> None:
        frame = pd.DataFrame(
            {
                "amount": np.round(np.linspace(10.0, 90.0, 40), 2),
                "category": ["a", "b", "c", "d"] * 10,
                "constant": [7] * 40,
                "row_id": range(1, 41),
            }
        )
        profile = profile_dataset(frame)

        features = numeric_feature_frame(frame, profile)

        assert list(features.columns) == [
            "amount"
        ], "the constant column carries no signal, and row_id is a surrogate key"

    def test_keeps_a_continuous_column_even_though_every_value_is_distinct(self) -> None:
        """Uniqueness alone must not exclude a column: a float measurement is
        naturally all-distinct and is usually the most informative feature."""
        frame = pd.DataFrame({"amount": np.round(np.linspace(1.5, 99.5, 50), 3)})

        features = numeric_feature_frame(frame, profile_dataset(frame))

        assert list(features.columns) == ["amount"]

    def test_coerces_numbers_stored_as_text(self) -> None:
        frame = pd.DataFrame(
            {
                "amount": [f"{value}.50" for value in range(20)],
                "other": list(range(100, 120)),
            }
        )
        profile = profile_dataset(frame)

        features = numeric_feature_frame(frame, profile)

        assert "amount" in features.columns
        assert features["amount"].iloc[0] == pytest.approx(0.5)

    def test_replaces_infinities_which_scikit_learn_cannot_use(self) -> None:
        frame = pd.DataFrame({"a": [1.0, np.inf, 3.0, -np.inf], "b": [1.0, 2.0, 3.0, 4.0]})
        profile = profile_dataset(frame)

        features = numeric_feature_frame(frame, profile)

        assert not np.isinf(features["a"].to_numpy()).any()


class TestAgainstTheSampleDatasets:
    """The committed fixtures must actually contain what their README claims."""

    def test_clean_dataset_has_no_missing_values_or_duplicates(self) -> None:
        profile = profile_dataset(load_sample("clean_transactions.csv"))

        assert profile.missing_cells == 0
        assert profile.duplicate_row_count == 0
        assert profile.row_count == 600

    def test_missing_values_dataset_has_the_documented_severity_spread(self) -> None:
        profile = profile_dataset(load_sample("missing_values.csv"))

        rates = {column.name: column.missing_percentage for column in profile.columns}
        assert 1 < rates["country"] < 10
        assert 10 < rates["customer_age"] < 25
        assert 35 < rates["loyalty_points"] < 55
        assert rates["promo_code"] > 85

    def test_duplicate_dataset_contains_exact_duplicates(self) -> None:
        profile = profile_dataset(load_sample("duplicate_records.csv"))
        assert profile.duplicate_row_count >= 40

    def test_invalid_values_dataset_has_a_constant_column(self) -> None:
        profile = profile_dataset(load_sample("invalid_values.csv"))

        batch = profile.column("batch_version")
        assert batch is not None and batch.is_constant

    def test_invalid_values_dataset_has_numbers_stored_as_text(self) -> None:
        profile = profile_dataset(load_sample("invalid_values.csv"))

        loyalty = profile.column("loyalty_points")
        assert loyalty is not None
        assert loyalty.is_numeric_like is True

    def test_outlier_dataset_has_an_extreme_amount_range(self) -> None:
        profile = profile_dataset(load_sample("outliers.csv"))

        amount = profile.column("amount")
        assert amount is not None and amount.numeric is not None
        assert amount.numeric.maximum is not None and amount.numeric.maximum > 40_000
