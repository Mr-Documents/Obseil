"""Rule parameter validation.

A rule is a configuration surface, so most of these tests are about what has to
be **rejected**. A rule that quietly accepts a misspelled parameter is a rule
that never fires and never says why, which is worse than one that refuses to be
saved.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.quality.rules.types import (
    AUTHORABLE_DIMENSIONS,
    MAX_REGEX_LENGTH,
    PREDICATES,
    AllowedValuesParameters,
    LengthParameters,
    NamedFormat,
    PatternParameters,
    RangeParameters,
    RulePredicateName,
    RuleSpec,
    UniqueParameters,
    validate_parameters,
    validate_rule_shape,
)
from app.quality.scoring import QualityDimension
from app.quality.types import Severity


def spec(**overrides: object) -> RuleSpec:
    """A valid spec, with fields overridden per test."""
    payload: dict[str, object] = {
        "id": "rule-1",
        "name": "Identifier must be present",
        "column": "id",
        "predicate": RulePredicateName.NOT_NULL,
        "parameters": {},
        "severity": Severity.HIGH,
        "dimension": QualityDimension.COMPLETENESS,
    }
    payload.update(overrides)
    return RuleSpec(**payload)  # type: ignore[arg-type]


class TestRegistry:
    def test_every_predicate_has_metadata(self) -> None:
        """A predicate without metadata would be unusable from the builder."""
        assert set(PREDICATES) == set(RulePredicateName)

    def test_every_predicate_exposes_a_parameter_schema(self) -> None:
        for meta in PREDICATES.values():
            assert meta.parameters_model.model_json_schema()["type"] == "object"


class TestUnknownParametersAreRejected:
    def test_a_misspelled_parameter_is_an_error(self) -> None:
        with pytest.raises(ValidationError):
            UniqueParameters.model_validate({"ignore_null": True})

    def test_not_null_takes_no_parameters_at_all(self) -> None:
        with pytest.raises(ValidationError):
            validate_parameters(RulePredicateName.NOT_NULL, {"column": "id"})

    def test_not_null_accepts_an_empty_blob(self) -> None:
        assert validate_parameters(RulePredicateName.NOT_NULL, {}) is not None


class TestRange:
    def test_requires_at_least_one_bound(self) -> None:
        with pytest.raises(ValidationError):
            RangeParameters.model_validate({})

    def test_rejects_a_minimum_above_the_maximum(self) -> None:
        with pytest.raises(ValidationError):
            RangeParameters.model_validate({"minimum": 10, "maximum": 1})

    def test_accepts_a_single_bound(self) -> None:
        assert RangeParameters.model_validate({"minimum": 0}).maximum is None

    def test_accepts_iso_dates(self) -> None:
        params = RangeParameters.model_validate({"minimum": "2020-01-01", "maximum": "2026-12-31"})
        assert params.minimum == "2020-01-01"

    def test_rejects_dates_the_wrong_way_round(self) -> None:
        with pytest.raises(ValidationError):
            RangeParameters.model_validate({"minimum": "2026-01-01", "maximum": "2020-01-01"})

    def test_rejects_mixing_a_number_and_a_date(self) -> None:
        with pytest.raises(ValidationError):
            RangeParameters.model_validate({"minimum": 0, "maximum": "2026-12-31"})

    def test_rejects_a_string_that_is_not_a_date(self) -> None:
        with pytest.raises(ValidationError):
            RangeParameters.model_validate({"minimum": "last tuesday"})

    def test_rejects_a_boolean_bound(self) -> None:
        """`bool` is an `int` subclass, so this would otherwise sneak through."""
        with pytest.raises(ValidationError):
            RangeParameters.model_validate({"minimum": True})


class TestPattern:
    def test_requires_a_regex_or_a_format(self) -> None:
        with pytest.raises(ValidationError):
            PatternParameters.model_validate({})

    def test_rejects_both_at_once(self) -> None:
        with pytest.raises(ValidationError):
            PatternParameters.model_validate({"regex": "^a$", "format": "email"})

    def test_rejects_an_uncompilable_regex(self) -> None:
        with pytest.raises(ValidationError):
            PatternParameters.model_validate({"regex": "([unclosed"})

    def test_rejects_an_overlong_regex(self) -> None:
        with pytest.raises(ValidationError):
            PatternParameters.model_validate({"regex": "a" * (MAX_REGEX_LENGTH + 1)})

    def test_a_named_format_resolves_to_a_pattern(self) -> None:
        params = PatternParameters.model_validate({"format": NamedFormat.EMAIL})
        assert params.effective_pattern.startswith("^")

    def test_a_regex_is_returned_verbatim(self) -> None:
        assert PatternParameters.model_validate({"regex": "^x$"}).effective_pattern == "^x$"


class TestLength:
    def test_requires_at_least_one_bound(self) -> None:
        with pytest.raises(ValidationError):
            LengthParameters.model_validate({})

    def test_rejects_a_minimum_above_the_maximum(self) -> None:
        with pytest.raises(ValidationError):
            LengthParameters.model_validate({"min_length": 9, "max_length": 8})

    def test_rejects_a_negative_minimum(self) -> None:
        with pytest.raises(ValidationError):
            LengthParameters.model_validate({"min_length": -1})


class TestAllowedValues:
    def test_requires_at_least_one_value(self) -> None:
        with pytest.raises(ValidationError):
            AllowedValuesParameters.model_validate({"values": []})

    def test_is_case_sensitive_by_default(self) -> None:
        assert AllowedValuesParameters.model_validate({"values": ["GBP"]}).case_sensitive


class TestRuleShape:
    def test_a_column_predicate_needs_a_column(self) -> None:
        with pytest.raises(ValueError, match="needs a column"):
            validate_rule_shape(RulePredicateName.NOT_NULL, None, {})

    def test_a_spec_validates_its_own_parameters(self) -> None:
        with pytest.raises(ValidationError):
            spec(predicate=RulePredicateName.RANGE, parameters={})

    def test_a_valid_spec_exposes_typed_parameters(self) -> None:
        typed = spec(
            predicate=RulePredicateName.LENGTH, parameters={"min_length": 8}
        ).typed_parameters
        assert isinstance(typed, LengthParameters)

    def test_a_spec_is_frozen(self) -> None:
        """A detector must not be able to edit the rule it is evaluating."""
        with pytest.raises(ValidationError):
            spec().name = "changed"  # type: ignore[misc]


class TestAuthorableDimensions:
    def test_anomalies_are_not_authorable(self) -> None:
        """That dimension is reserved for the unsupervised model."""
        assert QualityDimension.ANOMALY not in AUTHORABLE_DIMENSIONS

    def test_every_other_dimension_is_authorable(self) -> None:
        assert len(AUTHORABLE_DIMENSIONS) == len(QualityDimension) - 1
