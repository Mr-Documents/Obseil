"""Third-party sign-in endpoints.

The flow, end to end:

1. ``GET  /auth/oauth/{provider}/start``    redirects the browser to the provider
2. the provider redirects back to
   ``GET  /auth/oauth/{provider}/callback``  with a code and the state
3. the API exchanges the code, resolves the account, and redirects to the SPA
   with a **single-use handoff code**
4. ``POST /auth/oauth/exchange``            trades that code for Obseil tokens

Steps 1 and 2 are tied together by a signed, httpOnly cookie holding the CSRF
state and the PKCE verifier. Nothing about the flow is trusted from the query
string alone.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Annotated, Any
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Cookie, Query, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import DbSession
from app.core.config import settings
from app.core.errors import AuthenticationError, NotFoundError, ValidationError
from app.oauth import OAuthError, PkcePair, available_providers, get_provider
from app.schemas.auth import (
    AuthResponse,
    OAuthExchangeRequest,
    OAuthProviderInfo,
    TokenPair,
    UserRead,
)
from app.services import auth_service, oauth_service
from app.services.oauth_handoff import handoff_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["auth"])

#: Holds the CSRF state and PKCE verifier between the redirect out and back.
STATE_COOKIE = "obseil_oauth_state"
STATE_TTL_SECONDS = 600
#: Distinct from access and refresh, so a state cookie can never be presented
#: as a credential - the same discipline `decode_token` applies elsewhere.
STATE_TOKEN_TYPE = "oauth_state"


def _redirect_uri(provider_name: str) -> str:
    base = settings.api_base_url.rstrip("/")
    return f"{base}{settings.api_v1_prefix}/auth/oauth/{provider_name}/callback"


def _frontend(path: str, **params: str) -> str:
    base = settings.frontend_base_url.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}{path}{query}"


def _encode_state(provider: str, state: str, verifier: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "type": STATE_TOKEN_TYPE,
            "provider": provider,
            "state": state,
            "verifier": verifier,
            "iat": now,
            "exp": now + STATE_TTL_SECONDS,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def _decode_state(cookie: str | None) -> dict[str, Any]:
    if not cookie:
        raise AuthenticationError(
            "That sign-in attempt expired. Please try again.", code="oauth_state_missing"
        )
    try:
        payload = jwt.decode(cookie, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError(
            "That sign-in attempt could not be verified. Please try again.",
            code="oauth_state_invalid",
        ) from exc
    if payload.get("type") != STATE_TOKEN_TYPE:
        raise AuthenticationError("Invalid sign-in state.", code="oauth_state_invalid")
    return payload


@router.get(
    "/providers",
    response_model=list[OAuthProviderInfo],
    summary="Sign-in providers this deployment offers",
)
def list_providers() -> list[OAuthProviderInfo]:
    """Empty unless credentials are configured, so the UI shows no dead buttons."""
    return [
        OAuthProviderInfo(name=provider.name, label=provider.label)
        for provider in available_providers()
    ]


@router.get(
    "/{provider_name}/start",
    summary="Begin sign-in with a provider",
    responses={307: {"description": "Redirect to the provider"}},
)
def start(provider_name: str, response: Response) -> RedirectResponse:
    provider = get_provider(provider_name)
    if provider is None:
        raise NotFoundError("That sign-in provider is not enabled.", code="oauth_provider_unknown")

    state = secrets.token_urlsafe(24)
    pkce = PkcePair.generate()
    redirect = RedirectResponse(
        provider.authorization_url(
            redirect_uri=_redirect_uri(provider.name),
            state=state,
            code_challenge=pkce.challenge,
        ),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    redirect.set_cookie(
        STATE_COOKIE,
        _encode_state(provider.name, state, pkce.verifier),
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        # Lax, not Strict: the provider's redirect is a cross-site navigation,
        # and Strict would withhold the cookie exactly when it is needed.
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )
    # The response object carries the header the dependency system set up; the
    # redirect is what is actually returned.
    response.headers.update(redirect.headers)
    return redirect


@router.get(
    "/{provider_name}/callback",
    summary="Where the provider sends the browser back",
    responses={307: {"description": "Redirect to the frontend"}},
)
def callback(
    provider_name: str,
    db: DbSession,
    state: Annotated[str | None, Query()] = None,
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    obseil_oauth_state: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
) -> RedirectResponse:
    """Complete the flow, then hand the SPA a single-use code.

    Every failure ends at the frontend's callback page with a reason, never as
    a raw API error page: the browser is here because a person clicked a
    button, so they have to land somewhere they can act on.
    """

    def fail(reason: str, code_name: str) -> RedirectResponse:
        logger.info("OAuth sign-in failed", extra={"provider": provider_name, "reason": code_name})
        return RedirectResponse(
            _frontend("/auth/callback", error=reason),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    if error:
        # The user pressed "cancel" at the provider, most of the time.
        return fail("Sign-in was cancelled.", error)

    provider = get_provider(provider_name)
    if provider is None:
        return fail("That sign-in provider is not enabled.", "provider_unknown")
    if not code or not state:
        return fail("That sign-in attempt was incomplete. Please try again.", "missing_code")

    try:
        payload = _decode_state(obseil_oauth_state)
    except AuthenticationError as exc:
        return fail(exc.message, exc.code)

    # The CSRF check: the state in the URL must match the one this browser was
    # given. Without it, an attacker could feed their own callback URL to a
    # signed-in victim and attach their identity to the victim's session.
    if not secrets.compare_digest(str(payload.get("state", "")), state):
        return fail("That sign-in attempt could not be verified.", "state_mismatch")
    if payload.get("provider") != provider.name:
        return fail("That sign-in attempt could not be verified.", "provider_mismatch")

    try:
        profile = provider.fetch_profile(
            code=code,
            redirect_uri=_redirect_uri(provider.name),
            code_verifier=str(payload.get("verifier", "")),
        )
    except OAuthError as exc:
        logger.warning(
            "OAuth exchange failed", extra={"provider": provider.name, "error": str(exc)}
        )
        return fail("Could not complete sign-in with that provider.", "exchange_failed")

    try:
        user = oauth_service.sign_in_with_provider(db, profile)
    except AuthenticationError as exc:
        return fail(exc.message, exc.code)

    handoff = handoff_store.issue(auth_service.issue_tokens(user))
    redirect = RedirectResponse(
        _frontend("/auth/callback", code=handoff), status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    # The state has served its purpose; leaving it would let a stale attempt be
    # replayed against a later callback.
    redirect.delete_cookie(STATE_COOKIE, path="/")
    return redirect


@router.post(
    "/exchange",
    response_model=AuthResponse,
    summary="Trade a handoff code for Obseil tokens",
    responses={401: {"description": "The code is unknown, expired or already used"}},
)
def exchange(payload: OAuthExchangeRequest, db: DbSession) -> AuthResponse:
    tokens: TokenPair | None = handoff_store.redeem(payload.code)
    if tokens is None:
        raise AuthenticationError(
            "That sign-in link has expired. Please try again.", code="oauth_code_invalid"
        )

    user_id = auth_service.decode_token(tokens.access_token, "access")
    user = auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise ValidationError("That account no longer exists.")
    return AuthResponse(user=UserRead.model_validate(user), tokens=tokens)
