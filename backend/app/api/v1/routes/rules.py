"""User-defined rule endpoints.

Routes carry their full path rather than a router prefix, because rules are
addressed two ways - nested under a project for the collection, and top-level
for a single rule - exactly as the findings routes are.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession, OwnedProject, OwnedRule, Pagination
from app.quality.rules.types import PREDICATES
from app.schemas.common import Page
from app.schemas.rule import PredicateRead, RuleCreate, RuleRead, RuleUpdate
from app.services import rule_service

router = APIRouter(tags=["rules"])


# Declared before "/rules/{rule_id}" deliberately: FastAPI matches in
# declaration order, so the literal path has to come first or "predicates"
# would be read as a rule id.
@router.get(
    "/rules/predicates",
    response_model=list[PredicateRead],
    summary="The kinds of rule that can be written",
)
def list_predicates(user: CurrentUser) -> list[PredicateRead]:
    """Enumerate predicates and their parameter schemas.

    Not project-scoped: this is a static description of the engine's
    capabilities, and the rule builder generates its forms from it rather than
    duplicating a form per predicate in the client.
    """
    return [
        PredicateRead(
            predicate=predicate,
            label=meta.label,
            summary=meta.summary,
            requires_column=meta.requires_column,
            parameters_schema=meta.parameters_model.model_json_schema(),
        )
        for predicate, meta in PREDICATES.items()
    ]


@router.get(
    "/projects/{project_id}/rules",
    response_model=Page[RuleRead],
    summary="List a project's rules",
)
def list_rules(project: OwnedProject, db: DbSession, page: Pagination) -> Page[RuleRead]:
    rules = rule_service.list_rules(db, project=project, limit=page.limit, offset=page.offset)
    total = rule_service.count_rules(db, project=project)
    return Page[RuleRead](
        items=[RuleRead.model_validate(rule) for rule in rules],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/projects/{project_id}/rules",
    response_model=RuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a rule",
    responses={409: {"description": "A rule with that name already exists here"}},
)
def create_rule(payload: RuleCreate, project: OwnedProject, db: DbSession) -> RuleRead:
    rule = rule_service.create_rule(db, project=project, payload=payload)
    return RuleRead.model_validate(rule)


@router.get(
    "/rules/{rule_id}",
    response_model=RuleRead,
    summary="Get a rule",
    responses={404: {"description": "No such rule, or not yours"}},
)
def get_rule(rule: OwnedRule) -> RuleRead:
    return RuleRead.model_validate(rule)


@router.patch(
    "/rules/{rule_id}",
    response_model=RuleRead,
    summary="Update a rule",
    description=(
        "Partial update. Changing what the rule *means* - its predicate, "
        "parameters, severity, dimension or column - bumps its version; "
        "renaming it does not."
    ),
)
def update_rule(payload: RuleUpdate, rule: OwnedRule, db: DbSession) -> RuleRead:
    return RuleRead.model_validate(rule_service.update_rule(db, rule=rule, payload=payload))


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a rule",
    description="Findings this rule produced are kept, with their rule link cleared.",
)
def delete_rule(rule: OwnedRule, db: DbSession) -> Response:
    rule_service.delete_rule(db, rule=rule)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
