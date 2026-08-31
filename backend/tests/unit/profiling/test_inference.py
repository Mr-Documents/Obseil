"""Semantic type inference."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.profiling.inference import (
    coerce_numeric,
    datetime_parse_ratio,
    infer_column_type,
    looks_boolean,
    numeric_parse_ratio,
)
from app.profiling.types import ColumnType


def infer(values: list[object]) -> ColumnType:
    return infer_column_type(pd.Series(values))[0]


class TestNumericTypes:
    def test_integers_are_integer(self) -> None:
        assert infer([1, 2, 3, 4]) is ColumnType.INTEGER

    def test_floats_with_fractions_are_numeric(self) -> None:
        assert infer([1.5, 2.25, 3.75]) is ColumnType.NUMERIC

    def test_whole_valued_floats_are_reported_as_integer(self) -> None:
        """A float column of whole numbers is still integer-valued data."""
        assert infer([1.0, 2.0, 3.0]) is ColumnType.INTEGER

    def test_missing_values_do_not_change_the_type(self) -> None:
        assert infer([1, 2, np.nan, 4]) is ColumnType.INTEGER


class TestNumbersStoredAsText:
    def test_a_text_column_of_numbers_is_flagged(self) -> None:
        column_type, is_numeric_like = infer_column_type(
            pd.Series(["12.50", "8.00", "133.75", "9.99"] * 10)
        )
        assert column_type is ColumnType.NUMERIC
        assert is_numeric_like is True

    def test_free_text_containing_a_few_numerals_is_not_flagged(self) -> None:
        values = [f"order {index}" for index in range(40)] + ["12", "13"]
        column_type, is_numeric_like = infer_column_type(pd.Series(values))
        assert is_numeric_like is False
        assert column_type is not ColumnType.NUMERIC

    def test_a_genuinely_numeric_column_is_not_flagged_as_text(self) -> None:
        _, is_numeric_like = infer_column_type(pd.Series([1, 2, 3]))
        assert is_numeric_like is False


class TestBooleans:
    def test_native_booleans(self) -> None:
        assert infer([True, False, True]) is ColumnType.BOOLEAN

    @pytest.mark.parametrize(
        "values",
        [
            ["yes", "no", "yes"],
            ["true", "false", "TRUE"],
            ["Y", "N", "y"],
            ["on", "off", "on"],
        ],
    )
    def test_boolean_vocabularies_in_text(self, values: list[str]) -> None:
        assert infer(values * 5) is ColumnType.BOOLEAN

    def test_zero_and_one_stay_numeric(self) -> None:
        """A 0/1 flag is a numeric indicator; treating it as boolean would
        suppress statistics that are genuinely useful for it."""
        assert infer([0, 1, 1, 0]) is ColumnType.INTEGER
        assert looks_boolean(pd.Series(["0", "1", "0"])) is False


class TestDatetimes:
    def test_native_datetimes(self) -> None:
        assert infer(list(pd.date_range("2026-01-01", periods=5))) is ColumnType.DATETIME

    def test_iso_date_strings(self) -> None:
        assert infer(["2026-01-01", "2026-02-15", "2026-03-30"] * 5) is ColumnType.DATETIME

    def test_mostly_unparseable_dates_are_not_datetime(self) -> None:
        assert infer(["2026-01-01", "banana", "kiwi", "cherry", "plum"]) is not ColumnType.DATETIME


class TestCategoricalVersusText:
    def test_few_repeated_values_are_categorical(self) -> None:
        assert infer(["north", "south", "east"] * 40) is ColumnType.CATEGORICAL

    def test_mostly_distinct_strings_are_text(self) -> None:
        assert infer([f"free text note {index}" for index in range(200)]) is ColumnType.TEXT

    def test_forty_distinct_values_in_fifty_rows_is_not_a_category(self) -> None:
        """Both the absolute and the ratio condition must hold."""
        values = [f"value-{index}" for index in range(40)] + ["value-0"] * 10
        assert infer(values) is ColumnType.TEXT


def test_an_all_missing_column_is_empty() -> None:
    assert infer([np.nan, np.nan, np.nan]) is ColumnType.EMPTY


class TestRatios:
    def test_numeric_ratio_counts_parseable_values(self) -> None:
        assert numeric_parse_ratio(pd.Series(["1", "2", "x", "4"])) == pytest.approx(0.75)

    def test_numeric_ratio_of_an_empty_column_is_zero(self) -> None:
        assert numeric_parse_ratio(pd.Series([], dtype=object)) == 0.0

    def test_datetime_ratio_counts_parseable_values(self) -> None:
        ratio = datetime_parse_ratio(pd.Series(["2026-01-01", "2026-01-02", "nope", "also-nope"]))
        assert ratio == pytest.approx(0.5)


class TestCoercion:
    def test_numeric_coercion_handles_padding_and_junk(self) -> None:
        result = coerce_numeric(pd.Series([" 12 ", "8.5", "n/a"]))
        assert result.tolist()[:2] == [12.0, 8.5]
        assert pd.isna(result.iloc[2])

    def test_numeric_coercion_leaves_numeric_columns_untouched(self) -> None:
        original = pd.Series([1, 2, 3])
        assert coerce_numeric(original).equals(original)
