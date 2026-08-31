"""Reusable FastAPI dependencies.

These are the only place the API layer learns *who* is calling and *what* they
are allowed to touch. Route handlers declare the dependency and get either a
valid object or an error response — they never write an authorisation check
inline.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.common import PaginationParams
from app.services import auth_service, project_service

# auto_error=False so a missing header raises our own error envelope rather
# than Starlette's bare {"detail": ...}.
_bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> User:
    """Resolve the caller from the ``Authorization: Bearer <token>`` header."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Sign in to continue.", code="not_authenticated")

    user_id = decode_token(credentials.credentials, "access")
    user = auth_service.get_user_by_id(db, user_id)

    if user is None:
        # The token is validly signed but the account is gone.
        raise AuthenticationError("Your session is no longer valid. Please sign in again.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.", code="account_inactive")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_project(project_id: str, db: DbSession, user: CurrentUser) -> Project:
    """Path-parameter dependency that also enforces ownership."""
    return project_service.get_owned_project(db, project_id=project_id, user=user)


OwnedProject = Annotated[Project, Depends(get_project)]


def pagination(
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum items to return.")] = 50,
    offset: Annotated[int, Query(ge=0, description="Items to skip.")] = 0,
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)


Pagination = Annotated[PaginationParams, Depends(pagination)]
