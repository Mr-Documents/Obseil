"""The vocabulary of a user-defined rule.

A *rule* is how a user tells Obseil something it cannot work out for itself.
``app/quality/detectors/validity.py`` explains why that matters: the built-in
detectors deliberately never assert a business rule they cannot justify from the
data in front of them, so without this there is no way to say that ``currency``
may only hold one of four values.

This module is the domain layer and knows nothing about HTTP or the ORM.
:class:`RuleSpec` is what crosses into the analysis pipeline, which is why it is
a plain Pydantic model rather than a SQLAlchemy row - the pipeline is ORM-free
by design (see ``docs/IMPLEMENTATION_PLAN.md``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.quality.scoring import QualityDimension
from app.quality.types import Severity


class RulePredicateName(StrEnum):
    """The kinds of assertion a rule can make.

    Values are persisted in ``rules.predicate``, so they are stable. Adding a
    member is how a new predicate becomes available; removing one is a
    migration.
    """

    NOT_NULL = "not_null"
    UNIQUE = "unique"
    ALLOWED_VALUES = "allowed_values"
    RANGE = "range"
    PATTERN = "pattern"
    LENGTH = "length"


class NamedFormat(StrEnum):
    """Vetted patterns, offered so nobody has to write their own email regex.

    A hand-rolled email pattern is wrong far more often than it is right, and
    when it is wrong the user blames the tool rather than the pattern.
    """

    EMAIL = "email"
    UUID = "uuid"
    ISO_DATE = "iso_date"
    URL = "url"
    IPV4 = "ipv4"


#: Patterns behind :class:`NamedFormat`. Deliberately pragmatic rather than
#: exhaustively RFC-correct: the goal is to catch obviously malformed values,
#: not to adjudicate the grammar of every legal email address.
NAMED_FORMAT_PATTERNS: dict[NamedFormat, str] = {
    NamedFormat.EMAIL: r"^[^@\s]+@[^@\s.]+\.[^@\s]+$",
    NamedFormat.UUID: (
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    ),
    NamedFormat.ISO_DATE: r"^\d{4}-\d{2}-\d{2}$",
    NamedFormat.URL: r"^https?://[^\s/$.?#][^\s]*$",
    NamedFormat.IPV4: (r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$"),
}

#: Longest regex a rule may carry. A pattern longer than this is far likelier to
#: be pasted noise than an intentional assertion.
MAX_REGEX_LENGTH = 500

#: Most values an ``allowed_values`` rule may list. Beyond this the assertion is
#: really a lookup against a reference table - a cross-dataset rule, which is a
#: later phase - and the finding's evidence stops being readable.
MAX_ALLOWED_VALUES = 1000

#: Authors may not file a rule under Anomalies. That dimension is reserved for
#: the unsupervised model, and ``docs/METHODOLOGY.md`` is careful to keep "a fact
#: about the data" and "a row a model found interesting" in separate categories.
#: Letting a deterministic rule land there would blur the one distinction the
#: product is most careful about.
AUTHORABLE_DIMENSIONS: frozenset[QualityDimension] = frozenset(
    dimension for dimension in QualityDimension if dimension is not QualityDimension.ANOMALY
)


class RuleParameters(BaseModel):
    """Base for every predicate's parameters.

    ``extra="forbid"`` is the whole point: a misspelled parameter is a
    configuration error that must surface when the rule is written, not be
    silently ignored until somebody wonders why the rule never fires.
    """

    model_config = ConfigDict(extra="forbid")


class NotNullParameters(RuleParameters):
    """No parameters. The column simply has to be populated."""


class UniqueParameters(RuleParameters):
    #: Nulls are not duplicates of one another by default: three missing values
    #: are three absent values, which is the completeness detector's business,
    #: not a uniqueness violation.
    ignore_nulls: bool = True


class AllowedValuesParameters(RuleParameters):
    values: Annotated[list[str], Field(min_length=1, max_length=MAX_ALLOWED_VALUES)]
    case_sensitive: bool = True


class PatternParameters(RuleParameters):
    """A regex, or the name of one of ours. Exactly one of the two."""

    regex: Annotated[str | None, Field(max_length=MAX_REGEX_LENGTH)] = None
    format: NamedFormat | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> PatternParameters:
        if (self.regex is None) == (self.format is None):
            raise ValueError("Provide exactly one of 'regex' or 'format'.")
        if self.regex is not None:
            try:
                re.compile(self.regex)
            except re.error as exc:
                raise ValueError(f"'regex' is not a valid regular expression: {exc}") from exc
        return self

    @property
    def effective_pattern(self) -> str:
        """The pattern to apply, whether given directly or by name."""
        if self.regex is not None:
            return self.regex
        if self.format is not None:
            return NAMED_FORMAT_PATTERNS[self.format]
        raise ValueError("Pattern parameters carry neither a regex nor a format.")


#: A range bound is a number, or an ISO-8601 date as a string.
Bound = float | str


def _bound_sort_key(value: Bound, field: str) -> tuple[str, float]:
    """Classify one bound and reduce it to something orderable.

    Dates collapse to their ordinal so that the min/max comparison below is a
    plain float comparison regardless of which kind of bound was given.

    Booleans are refused earlier, by ``RangeParameters._reject_booleans``: by
    the time a value reaches here Pydantic has already coerced one to a float,
    so a guard at this point would never fire.
    """
    if isinstance(value, int | float):
        return "number", float(value)
    try:
        return "date", float(date.fromisoformat(value).toordinal())
    except ValueError as exc:
        raise ValueError(f"'{field}' must be a number or an ISO-8601 date (YYYY-MM-DD).") from exc


class RangeParameters(RuleParameters):
    """Numeric or date bounds. At least one bound is required."""

    minimum: Bound | None = None
    maximum: Bound | None = None
    #: Whether the bounds themselves are permitted values.
    inclusive: bool = True

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def _reject_booleans(cls, value: object) -> object:
        """Refuse ``true``/``false`` before Pydantic coerces them to 1.0/0.0.

        ``bool`` is an ``int`` subclass, so ``{"minimum": true}`` would
        otherwise be read as ``minimum: 1.0``. A boolean bound is always a
        mistake, and quietly treating it as a number would hide it. This has to
        run in ``mode="before"``, because after coercion the boolean is gone.
        """
        if isinstance(value, bool):
            raise ValueError("must be a number or an ISO-8601 date (YYYY-MM-DD), not a boolean")
        return value

    @model_validator(mode="after")
    def _check_bounds(self) -> RangeParameters:
        if self.minimum is None and self.maximum is None:
            raise ValueError("Provide 'minimum', 'maximum', or both.")

        kinds: set[str] = set()
        keys: dict[str, float] = {}
        for field in ("minimum", "maximum"):
            value: Bound | None = getattr(self, field)
            if value is None:
                continue
            kind, key = _bound_sort_key(value, field)
            kinds.add(kind)
            keys[field] = key

        if len(kinds) > 1:
            raise ValueError("'minimum' and 'maximum' must both be numbers or both be dates.")
        if len(keys) == 2 and keys["minimum"] > keys["maximum"]:
            raise ValueError("'minimum' cannot be greater than 'maximum'.")
        return self


class LengthParameters(RuleParameters):
    """String length bounds. At least one bound is required."""

    min_length: Annotated[int | None, Field(ge=0)] = None
    max_length: Annotated[int | None, Field(ge=1)] = None

    @model_validator(mode="after")
    def _check_bounds(self) -> LengthParameters:
        if self.min_length is None and self.max_length is None:
            raise ValueError("Provide 'min_length', 'max_length', or both.")
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("'min_length' cannot be greater than 'max_length'.")
        return self


@dataclass(frozen=True, slots=True)
class PredicateMeta:
    """Everything the rest of the system needs to know about one predicate.

    Keeping this in a single registry means the rule builder can enumerate
    predicates and generate a form from ``parameters_model.model_json_schema()``
    rather than hard-coding one form per predicate and drifting from the
    backend. It is the same reasoning as the detector registry.
    """

    parameters_model: type[RuleParameters]
    #: False for predicates that span columns. Every predicate requires one
    #: today; cross-column predicates arrive in the next slice.
    requires_column: bool
    label: str
    summary: str


PREDICATES: dict[RulePredicateName, PredicateMeta] = {
    RulePredicateName.NOT_NULL: PredicateMeta(
        parameters_model=NotNullParameters,
        requires_column=True,
        label="Must not be empty",
        summary="Every row must hold a value in this column.",
    ),
    RulePredicateName.UNIQUE: PredicateMeta(
        parameters_model=UniqueParameters,
        requires_column=True,
        label="Must be unique",
        summary="No value may appear in this column more than once.",
    ),
    RulePredicateName.ALLOWED_VALUES: PredicateMeta(
        parameters_model=AllowedValuesParameters,
        requires_column=True,
        label="Must be one of",
        summary="Values must come from a fixed list.",
    ),
    RulePredicateName.RANGE: PredicateMeta(
        parameters_model=RangeParameters,
        requires_column=True,
        label="Must fall within a range",
        summary="Numeric or date values must sit between the given bounds.",
    ),
    RulePredicateName.PATTERN: PredicateMeta(
        parameters_model=PatternParameters,
        requires_column=True,
        label="Must match a pattern",
        summary="Text must match a regular expression or a named format.",
    ),
    RulePredicateName.LENGTH: PredicateMeta(
        parameters_model=LengthParameters,
        requires_column=True,
        label="Must be a given length",
        summary="Text length must sit between the given bounds.",
    ),
}


def validate_parameters(predicate: RulePredicateName, parameters: dict[str, Any]) -> RuleParameters:
    """Validate a raw parameter blob against its predicate's model.

    Raises ``ValueError`` on anything invalid. Callers at the HTTP boundary
    translate that into the application's own ``ValidationError`` so the client
    receives the standard error envelope.
    """
    return PREDICATES[predicate].parameters_model.model_validate(parameters)


def validate_rule_shape(
    predicate: RulePredicateName,
    column: str | None,
    parameters: dict[str, Any],
) -> RuleParameters:
    """Check that a predicate, its column and its parameters agree.

    One definition, used by both the HTTP schema and :class:`RuleSpec`, so the
    API and the pipeline can never disagree about what a valid rule is.
    """
    meta = PREDICATES[predicate]
    if meta.requires_column and not column:
        raise ValueError(f"The '{predicate.value}' predicate needs a column.")
    if not meta.requires_column and column:
        raise ValueError(f"The '{predicate.value}' predicate does not take a single column.")
    return validate_parameters(predicate, parameters)


class RuleSpec(BaseModel):
    """One rule, as the analysis pipeline sees it.

    Deliberately not the ORM row: the pipeline is ORM-free, so
    ``rule_service.active_rule_specs`` converts rows into these before they
    cross the boundary. Frozen, because a detector must not be able to edit the
    rule it is evaluating.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str | None = None
    column: str | None = None
    predicate: RulePredicateName
    parameters: dict[str, Any] = Field(default_factory=dict)
    severity: Severity
    dimension: QualityDimension
    version: int = 1

    @model_validator(mode="after")
    def _validate_shape(self) -> RuleSpec:
        validate_rule_shape(self.predicate, self.column, self.parameters)
        return self

    @property
    def typed_parameters(self) -> RuleParameters:
        """The validated parameter model. Validation already passed on init."""
        return validate_parameters(self.predicate, self.parameters)
