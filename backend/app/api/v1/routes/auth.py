"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserRead,
)
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    responses={409: {"description": "Email already registered"}},
)
def register(payload: RegisterRequest, db: DbSession) -> AuthResponse:
    """Register and sign in immediately — one step, not two."""
    user = auth_service.register_user(
        db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
    )
    return AuthResponse(user=UserRead.model_validate(user), tokens=auth_service.issue_tokens(user))


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in",
    responses={401: {"description": "Incorrect email or password"}},
)
def login(payload: LoginRequest, db: DbSession) -> AuthResponse:
    user = auth_service.authenticate_user(db, email=payload.email, password=payload.password)
    return AuthResponse(user=UserRead.model_validate(user), tokens=auth_service.issue_tokens(user))


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a refresh token for a new token pair",
    responses={401: {"description": "Refresh token invalid or expired"}},
)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    _, tokens = auth_service.refresh_tokens(db, payload.refresh_token)
    return tokens


@router.post("/logout", response_model=MessageResponse, summary="Sign out")
def logout() -> MessageResponse:
    """Sign out.

    Obseil issues stateless JWTs, so the authoritative action is the client
    discarding its tokens. The endpoint exists so that clients have one call to
    make, and so that server-side token revocation can be added later without
    changing the client contract.
    """
    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=UserRead, summary="The signed-in user")
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
