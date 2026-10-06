"""Rule request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.quality.rules.types import (
    AUTHORABLE_DIMENSIONS,
    PREDICATES,
    RulePredicateName,
    validate_rule_shape,
)
from app.quality.scoring import QualityDimension
from app.quality.types import Severity
from app.schemas.common import ORMModel


def _clean_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Rule name cannot be blank.")
    return cleaned


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _check_dimension(value: QualityDimension) -> QualityDimension:
    if value not in AUTHORABLE_DIMENSIONS:
        allowed = ", ".join(sorted(dimension.value for dimension in AUTHORABLE_DIMENSIONS))
        raise ValueError(
            f"'{value.value}' is reserved for model-detected anomalies. Choose one of: {allowed}."
        )
    return value


class RuleCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    column_name: Annotated[str | None, Field(max_length=255)] = None
    predicate: RulePredicateName
    parameters: dict[str, Any] = Field(default_factory=dict)
    severity: Severity
    dimension: QualityDimension
    enabled: bool = True

    _normalise_name = field_validator("name")(staticmethod(_clean_name))
    _normalise_description = field_validator("description")(staticmethod(_blank_to_none))
    _normalise_column = field_validator("column_name")(staticmethod(_blank_to_none))
    _validate_dimension = field_validator("dimension")(staticmethod(_check_dimension))

    @model_validator(mode="after")
    def _validate_shape(self) -> RuleCreate:
        validate_rule_shape(self.predicate, self.column_name, self.parameters)
        return self


class RuleUpdate(BaseModel):
    """Partial update. Absent fields are left untouched.

    Coherence between ``predicate``, ``column_name`` and ``parameters`` is
    checked in the service layer rather than here, because validating a partial
    change requires the rule's current state - changing only ``parameters``
    has to be checked against the predicate already stored.
    """

    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    column_name: Annotated[str | None, Field(max_length=255)] = None
    predicate: RulePredicateName | None = None
    parameters: dict[str, Any] | None = None
    severity: Severity | None = None
    dimension: QualityDimension | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _normalise_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @field_validator("description", "column_name")
    @classmethod
    def _normalise_optional_text(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("dimension")
    @classmethod
    def _validate_dimension(cls, value: QualityDimension | None) -> QualityDimension | None:
        return None if value is None else _check_dimension(value)


class RuleRead(ORMModel):
    id: str
    project_id: str
    name: str
    description: str | None
    column_name: str | None
    predicate: str
    parameters: dict[str, Any]
    severity: str
    dimension: str
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def predicate_label(self) -> str:
        """Readable name, so the UI never renders a raw enum value."""
        try:
            return PREDICATES[RulePredicateName(self.predicate)].label
        except (ValueError, KeyError):
            return self.predicate.replace("_", " ").capitalize()


class PredicateRead(BaseModel):
    """One available predicate, for the rule builder to render a form from."""

    predicate: RulePredicateName
    label: str
    summary: str
    requires_column: bool
    #: JSON Schema for this predicate's parameters, so the form is generated
    #: from the backend's definition rather than duplicated in the client.
    parameters_schema: dict[str, Any]
