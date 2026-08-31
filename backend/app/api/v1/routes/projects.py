"""Project endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession, OwnedProject, Pagination
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectRead, ProjectSummary, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=Page[ProjectSummary], summary="List your projects")
def list_projects(db: DbSession, user: CurrentUser, page: Pagination) -> Page[ProjectSummary]:
    items = project_service.list_projects(db, owner=user, limit=page.limit, offset=page.offset)
    total = project_service.count_projects(db, owner=user)
    return Page[ProjectSummary](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
def create_project(payload: ProjectCreate, db: DbSession, user: CurrentUser) -> ProjectRead:
    project = project_service.create_project(db, owner=user, payload=payload)
    return ProjectRead.model_validate(project)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project",
    responses={404: {"description": "No such project, or not yours"}},
)
def get_project(project: OwnedProject) -> ProjectRead:
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead, summary="Update a project")
def update_project(payload: ProjectUpdate, project: OwnedProject, db: DbSession) -> ProjectRead:
    updated = project_service.update_project(db, project=project, payload=payload)
    return ProjectRead.model_validate(updated)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project and everything in it",
)
def delete_project(project: OwnedProject, db: DbSession) -> Response:
    project_service.delete_project(db, project=project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
