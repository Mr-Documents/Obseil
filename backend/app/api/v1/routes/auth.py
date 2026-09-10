"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import AuthenticationError, RateLimitedError
from app.core.ratelimit import InMemoryRateLimiter, NullRateLimiter, RateLimiter
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


def _build_login_limiter() -> RateLimiter:
    if not settings.login_rate_limit_enabled:
        return NullRateLimiter()
    return InMemoryRateLimiter(
        max_attempts=settings.login_max_attempts,
        window_seconds=settings.login_attempt_window_seconds,
    )


#: Module-level so the counts survive between requests. In-process, so it is
#: correct for the single-container deployment this ships as; more than one
#: replica needs shared storage behind the same `RateLimiter` interface.
login_limiter: RateLimiter = _build_login_limiter()


def client_key(request: Request) -> str:
    """The caller's address, which is what login failures are counted against.

    Behind a reverse proxy this is the proxy unless uvicorn is run with
    `--proxy-headers` and a trusted `--forwarded-allow-ips`. Parsing
    `X-Forwarded-For` here instead would let any caller spoof the header and
    step around the limit entirely.
    """
    return request.client.host if request.client else "unknown"


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    responses={409: {"description": "Email already registered"}},
)
def register(payload: RegisterRequest, db: DbSession) -> AuthResponse:
    """Register and sign in immediately - one step, not two."""
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
    responses={
        401: {"description": "Incorrect email or password"},
        429: {"description": "Too many failed attempts from this address"},
    },
)
def login(payload: LoginRequest, request: Request, db: DbSession) -> AuthResponse:
    key = client_key(request)

    wait = login_limiter.retry_after(key)
    if wait is not None:
        raise RateLimitedError(wait)

    try:
        user = auth_service.authenticate_user(db, email=payload.email, password=payload.password)
    except AuthenticationError:
        # Only failures are counted, so signing in correctly never brings a
        # legitimate user closer to being locked out.
        login_limiter.record_failure(key)
        raise

    login_limiter.reset(key)
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
