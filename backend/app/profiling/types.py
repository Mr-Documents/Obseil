"""Profile data structures.

These are Pydantic models rather than plain dataclasses because a profile is
both an API response and a JSON document persisted with the analysis. One
definition keeps the two in step.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ColumnType(StrEnum):
    """Semantic type, which is not the same thing as the pandas dtype.

    A column of ``"1"``, ``"2"``, ``"3"`` has dtype ``object`` but is
    semantically numeric, and saying so is what lets the quality engine flag it
    as numbers-stored-as-text.
    """

    NUMERIC = "numeric"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    CATEGORICAL = "categorical"
    TEXT = "text"
    EMPTY = "empty"

    @property
    def is_numeric(self) -> bool:
        return self in {ColumnType.NUMERIC, ColumnType.INTEGER}

    @property
    def is_discrete(self) -> bool:
        return self in {ColumnType.CATEGORICAL, ColumnType.BOOLEAN}


class ValueCount(BaseModel):
    value: str
    count: int
    percentage: float


class NumericStatistics(BaseModel):
    """Only produced for columns where these quantities mean something."""

    mean: float | None = None
    median: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    q1: float | None = None
    q3: float | None = None
    iqr: float | None = None
    skewness: float | None = None
    zero_count: int = 0
    negative_count: int = 0


class DatetimeStatistics(BaseModel):
    earliest: str | None = None
    latest: str | None = None
    range_days: float | None = None


class TextStatistics(BaseModel):
    min_length: int | None = None
    max_length: int | None = None
    mean_length: float | None = None
    empty_string_count: int = 0
    whitespace_padded_count: int = 0


class ColumnProfile(BaseModel):
    """Everything Obseil knows about one column."""

    name: str
    position: int
    dtype: str = Field(description="The underlying pandas dtype.")
    inferred_type: ColumnType

    count: int = Field(description="Non-missing values.")
    missing_count: int
    missing_percentage: float
    unique_count: int
    unique_percentage: float = Field(description="Unique values as a share of non-missing values.")

    is_constant: bool = False
    is_unique: bool = Field(default=False, description="A candidate identifier column.")
    #: Text column whose values are almost all parseable as numbers.
    is_numeric_like: bool = False
    memory_bytes: int = 0

    numeric: NumericStatistics | None = None
    datetime: DatetimeStatistics | None = None
    text: TextStatistics | None = None
    top_values: list[ValueCount] = Field(default_factory=list)


class DatasetProfile(BaseModel):
    """Dataset-level summary plus every column profile."""

    row_count: int
    column_count: int
    total_cells: int
    missing_cells: int
    missing_percentage: float
    duplicate_row_count: int
    duplicate_row_percentage: float
    memory_bytes: int

    numeric_columns: list[str] = Field(default_factory=list)
    categorical_columns: list[str] = Field(default_factory=list)
    datetime_columns: list[str] = Field(default_factory=list)
    boolean_columns: list[str] = Field(default_factory=list)
    text_columns: list[str] = Field(default_factory=list)
    empty_columns: list[str] = Field(default_factory=list)

    columns: list[ColumnProfile] = Field(default_factory=list)

    #: True when the profile describes a sample rather than the whole file.
    sampled: bool = False
    sampled_rows: int | None = None
    source_rows: int | None = None
    #: Reader assumptions and normalisations worth telling the user about.
    notes: list[str] = Field(default_factory=list)

    def column(self, name: str) -> ColumnProfile | None:
        return next((column for column in self.columns if column.name == name), None)
