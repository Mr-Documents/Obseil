"""User-defined quality rules.

The built-in detectors answer questions that can be settled from the data
alone. A rule is how a user supplies the domain knowledge Obseil deliberately
refuses to invent - see ``app/quality/detectors/validity.py``.

This package holds the domain representation only. The stored definition is
``app.models.rule.Rule`` and the HTTP contract ``app.schemas.rule``, mirroring
the ``FindingDraft`` / ``Finding`` / ``FindingRead`` split the findings already
use.
"""

from app.quality.rules.types import (
    AUTHORABLE_DIMENSIONS,
    NAMED_FORMAT_PATTERNS,
    PREDICATES,
    AllowedValuesParameters,
    LengthParameters,
    NamedFormat,
    NotNullParameters,
    PatternParameters,
    PredicateMeta,
    RangeParameters,
    RuleParameters,
    RulePredicateName,
    RuleSpec,
    UniqueParameters,
    validate_parameters,
    validate_rule_shape,
)

__all__ = [
    "AUTHORABLE_DIMENSIONS",
    "NAMED_FORMAT_PATTERNS",
    "PREDICATES",
    "AllowedValuesParameters",
    "LengthParameters",
    "NamedFormat",
    "NotNullParameters",
    "PatternParameters",
    "PredicateMeta",
    "RangeParameters",
    "RuleParameters",
    "RulePredicateName",
    "RuleSpec",
    "UniqueParameters",
    "validate_parameters",
    "validate_rule_shape",
]
