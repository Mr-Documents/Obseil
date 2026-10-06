"""Rule business logic, including the authorisation choke point."""

from __future__ import annotations

import logging

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.project import Project
from app.models.rule import Rule
from app.models.user import User
from app.quality.rules.types import RulePredicateName, RuleSpec, validate_rule_shape
from app.quality.scoring import QualityDimension
from app.quality.types import Severity
from app.schemas.rule import RuleCreate, RuleUpdate

logger = logging.getLogger(__name__)

#: Fields whose change alters what the rule *means*, and therefore bumps its
#: version. Renaming a rule or editing its description does not: the assertion
#: being made is the same one, so a finding judged before and after is still
#: comparable.
SEMANTIC_FIELDS = ("predicate", "parameters", "severity", "dimension", "column_name")


def get_owned_rule(db: Session, *, rule_id: str, user: User) -> Rule:
    """Fetch a rule the user owns, via its project.

    Like ``get_owned_project``, a rule belonging to somebody else is a 404 and
    not a 403: a 403 would confirm the id exists.
    """
    rule = db.scalar(
        select(Rule)
        .join(Project, Project.id == Rule.project_id)
        .where(Rule.id == rule_id, Project.owner_id == user.id)
    )
    if rule is None:
        raise NotFoundError("That rule does not exist, or you do not have access to it.")
    return rule


def list_rules(db: Session, *, project: Project, limit: int, offset: int) -> list[Rule]:
    return list(
        db.scalars(
            select(Rule)
            .where(Rule.project_id == project.id)
            .order_by(Rule.created_at.desc(), Rule.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )


def count_rules(db: Session, *, project: Project) -> int:
    return (
        db.scalar(select(func.count()).select_from(Rule).where(Rule.project_id == project.id)) or 0
    )


def create_rule(db: Session, *, project: Project, payload: RuleCreate) -> Rule:
    rule = Rule(
        project_id=project.id,
        name=payload.name,
        description=payload.description,
        column_name=payload.column_name,
        predicate=payload.predicate.value,
        parameters=payload.parameters,
        severity=payload.severity.value,
        dimension=payload.dimension.value,
        enabled=payload.enabled,
        version=1,
    )
    db.add(rule)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"This project already has a rule called “{payload.name}”.") from exc
    db.refresh(rule)
    logger.info("Created rule", extra={"rule_id": rule.id, "project_id": project.id})
    return rule


def update_rule(db: Session, *, rule: Rule, payload: RuleUpdate) -> Rule:
    """Apply a partial update, re-validating the result and versioning it.

    The coherence check happens here rather than on the schema because a
    partial change can only be judged against the rule's current state:
    sending new ``parameters`` alone has to be validated against the
    ``predicate`` already stored.
    """
    # `mode="json"` so enum members arrive as the plain strings the columns
    # hold, which keeps the before/after comparison below an honest one.
    changes = payload.model_dump(exclude_unset=True, mode="json")

    # `.get` is right even when the client deliberately sent `"column_name":
    # null`: the key is then present holding None, so the clearing is honoured
    # rather than falling back to the stored value.
    predicate = RulePredicateName(changes.get("predicate", rule.predicate))
    column = changes.get("column_name", rule.column_name)
    parameters = changes.get("parameters", rule.parameters)

    try:
        validate_rule_shape(predicate, column, parameters)
    except (ValueError, PydanticValidationError) as exc:
        raise ValidationError(str(exc)) from exc

    before = {field: getattr(rule, field) for field in SEMANTIC_FIELDS}

    for field, value in changes.items():
        setattr(rule, field, value)

    if any(getattr(rule, field) != before[field] for field in SEMANTIC_FIELDS):
        rule.version += 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("This project already has a rule with that name.") from exc
    db.refresh(rule)
    return rule


def delete_rule(db: Session, *, rule: Rule) -> None:
    """Delete a rule.

    Findings it produced are kept: ``findings.rule_id`` is ``ON DELETE SET
    NULL``, because a finding records what one run actually saw and removing
    the rule afterwards does not unmake that.
    """
    logger.info("Deleting rule", extra={"rule_id": rule.id})
    db.delete(rule)
    db.commit()


def active_rule_specs(db: Session, *, project_id: str) -> list[RuleSpec]:
    """The enabled rules for a project, as domain objects.

    A stored rule that no longer validates - written before a predicate's
    parameters changed, say - is logged and skipped rather than failing the
    analysis. This is the same fail-soft stance the detector engine takes: one
    unusable rule must not cost the user every other finding in their dataset.
    """
    rows = db.scalars(
        select(Rule)
        .where(Rule.project_id == project_id, Rule.enabled.is_(True))
        .order_by(Rule.created_at, Rule.id)
    ).all()

    specs: list[RuleSpec] = []
    for row in rows:
        try:
            specs.append(
                RuleSpec(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    column=row.column_name,
                    predicate=RulePredicateName(row.predicate),
                    parameters=row.parameters or {},
                    severity=Severity(row.severity),
                    dimension=QualityDimension(row.dimension),
                    version=row.version,
                )
            )
        except (ValueError, PydanticValidationError):
            logger.warning(
                "Skipping a rule that no longer validates",
                extra={"rule_id": row.id, "predicate": row.predicate},
            )
    return specs
