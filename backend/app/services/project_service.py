"""Project business logic, including the single authorisation choke point."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectSummary, ProjectUpdate

logger = logging.getLogger(__name__)


def get_owned_project(db: Session, *, project_id: str, user: User) -> Project:
    """Fetch a project the user is allowed to see.

    Every project-scoped operation goes through here. A project belonging to
    somebody else returns 404 rather than 403 on purpose: a 403 would confirm
    that the id exists, which is itself information the caller has no right to.

    When team collaboration is added, the membership check goes in this one
    function and every caller inherits it.
    """
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if project is None:
        raise NotFoundError("That project does not exist, or you do not have access to it.")
    return project


def create_project(db: Session, *, owner: User, payload: ProjectCreate) -> Project:
    project = Project(owner_id=owner.id, name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    logger.info("Created project", extra={"project_id": project.id, "user_id": owner.id})
    return project


def update_project(db: Session, *, project: Project, payload: ProjectUpdate) -> Project:
    """Apply a partial update. Fields omitted by the client are left alone."""
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, *, project: Project) -> None:
    """Delete a project and, by cascade, everything inside it."""
    logger.info("Deleting project", extra={"project_id": project.id})
    db.delete(project)
    db.commit()


def count_projects(db: Session, *, owner: User) -> int:
    return (
        db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == owner.id))
        or 0
    )


def list_projects(db: Session, *, owner: User, limit: int, offset: int) -> list[ProjectSummary]:
    """Most recently updated first, with roll-up counts attached.

    The counts come from two grouped aggregate queries rather than from loading
    each project's relationships, so listing N projects costs three queries
    regardless of how many datasets each one holds.
    """
    from app.services import dataset_service

    projects = db.scalars(
        select(Project)
        .where(Project.owner_id == owner.id)
        .order_by(Project.updated_at.desc(), Project.id)
        .limit(limit)
        .offset(offset)
    ).all()

    dataset_counts = dataset_service.project_dataset_counts(db, owner=owner)
    analysis_counts = dataset_service.project_analysis_counts(db, owner=owner)
    latest_scores = dataset_service.project_latest_scores(db, owner=owner)

    summaries = []
    for project in projects:
        summary = ProjectSummary.model_validate(project)
        summary.dataset_count = dataset_counts.get(project.id, 0)
        summary.analysis_count = analysis_counts.get(project.id, 0)
        score = latest_scores.get(project.id)
        if score is not None:
            summary.latest_quality_score, summary.last_analysed_at = score
        summaries.append(summary)
    return summaries
