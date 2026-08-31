"""Feature preparation for anomaly detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.features import (
    MAX_FEATURE_MISSING_SHARE,
    MIN_FEATURES,
    MIN_ROWS,
    prepare_features,
    robust_deviations,
    scale_features,
)
from app.profiling import profile_dataset


def prepare(frame: pd.DataFrame):
    return prepare_features(frame, profile_dataset(frame))


def numeric_frame(rows: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "amount": np.round(rng.normal(100, 20, rows), 2),
            "items": rng.integers(1, 12, rows),
            "age": rng.integers(18, 80, rows),
        }
    )


class TestSelection:
    def test_keeps_the_usable_numeric_columns(self) -> None:
        result = prepare(numeric_frame())

        assert result.usable
        assert set(result.feature_names) == {"amount", "items", "age"}

    def test_excludes_categorical_and_text_columns(self) -> None:
        frame = numeric_frame()
        frame["channel"] = ["online", "mobile"] * (len(frame) // 2)

        assert "channel" not in prepare(frame).feature_names

    def test_excludes_a_surrogate_key(self) -> None:
        """A row is not anomalous for having a high id, and including one lets
        the model rank rows by insertion order."""
        frame = numeric_frame()
        frame["row_id"] = range(len(frame))

        assert "row_id" not in prepare(frame).feature_names

    def test_excludes_a_constant_column(self) -> None:
        frame = numeric_frame()
        frame["batch"] = 7

        result = prepare(frame)
        assert "batch" not in result.feature_names

    def test_includes_numbers_stored_as_text(self) -> None:
        frame = numeric_frame()
        frame["points"] = [f"{value}.5" for value in range(len(frame))]

        assert "points" in prepare(frame).feature_names


class TestMissingValues:
    def test_imputes_gaps_with_the_median(self) -> None:
        """The median, not the mean: the mean is dragged by the very outliers
        the model is looking for, which would pull imputed rows towards them."""
        frame = numeric_frame()
        frame.loc[:19, "amount"] = np.nan
        expected = float(frame["amount"].median())

        result = prepare(frame)

        assert result.frame["amount"].isna().sum() == 0
        assert result.imputed_columns["amount"] == pytest.approx(expected, abs=1e-4)
        assert result.frame["amount"].iloc[0] == pytest.approx(expected, abs=1e-4)

    def test_drops_a_mostly_empty_feature_instead_of_inventing_it(self) -> None:
        frame = numeric_frame()
        frame.loc[:159, "age"] = np.nan  # 80% missing

        result = prepare(frame)

        assert "age" not in result.feature_names
        assert "age" in result.dropped_columns
        assert MAX_FEATURE_MISSING_SHARE == 0.5


class TestRefusals:
    def test_refuses_a_single_numeric_column(self) -> None:
        """One feature can only rediscover what the IQR rule already reports."""
        frame = pd.DataFrame({"amount": np.linspace(1, 100, 200)})

        result = prepare(frame)

        assert not result.usable
        assert str(MIN_FEATURES) in (result.skip_reason or "")
        assert "interquartile" in (result.skip_reason or "")

    def test_refuses_a_dataset_with_no_numeric_columns(self) -> None:
        frame = pd.DataFrame({"a": ["x", "y"] * 100, "b": ["p", "q"] * 100})
        assert not prepare(frame).usable

    def test_refuses_too_few_rows(self) -> None:
        result = prepare(numeric_frame(rows=30))

        assert not result.usable
        assert str(MIN_ROWS) in (result.skip_reason or "")

    def test_a_refusal_explains_itself(self) -> None:
        result = prepare(numeric_frame(rows=10))
        assert result.skip_reason and len(result.skip_reason) > 20


class TestScaling:
    def test_robust_scaling_centres_on_the_median(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]})
        scaled = scale_features(frame)
        assert scaled["a"].iloc[2] == pytest.approx(0.0)

    def test_a_zero_spread_column_does_not_divide_by_zero(self) -> None:
        frame = pd.DataFrame({"a": [5.0] * 10})
        assert scale_features(frame)["a"].abs().max() == 0.0

    def test_deviations_are_absolute_distances(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 100.0]})
        deviations = robust_deviations(frame)
        assert (deviations["a"] >= 0).all()
        assert deviations["a"].idxmax() == 4
