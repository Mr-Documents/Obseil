"""Google and GitHub.

Both speak OAuth 2.0, and they differ in exactly the ways that matter here:
Google returns a verified-email flag in one call, while GitHub does not return
the email with the profile at all and needs a second request to find the
verified primary address. Those differences live here so the rest of the
application only ever sees an ``OAuthProfile``.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.oauth.base import OAuthError, OAuthProfile, OAuthProvider

logger = logging.getLogger(__name__)

#: Providers are reached over the internet during a user-facing request, so the
#: wait is bounded well below the client's patience.
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _post_json(url: str, data: dict[str, str], headers: dict[str, str]) -> dict[str, Any]:
    try:
        response = httpx.post(url, data=data, headers=headers, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise OAuthError(f"Could not reach the provider: {exc}") from exc
    except ValueError as exc:
        raise OAuthError("The provider's token response was not JSON.") from exc

    if not isinstance(payload, dict):
        raise OAuthError("The provider's token response was not an object.")
    if "error" in payload:
        # Logged, not surfaced: it can name the client id and the exact reason.
        logger.warning("OAuth token exchange refused", extra={"error": str(payload.get("error"))})
        raise OAuthError("The provider refused the sign-in attempt.")
    return payload


def _get_json(url: str, token: str, accept: str = "application/json") -> Any:
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": accept},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise OAuthError(f"Could not read the profile from the provider: {exc}") from exc
    except ValueError as exc:
        raise OAuthError("The provider's profile response was not JSON.") from exc


def _access_token(payload: dict[str, Any]) -> str:
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise OAuthError("The provider did not return an access token.")
    return token


class GoogleProvider(OAuthProvider):
    name = "google"
    label = "Google"

    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
    SCOPES = "openid email profile"

    def authorization_url(self, *, redirect_uri: str, state: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": self.SCOPES,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                # Ask for a fresh choice rather than silently reusing whichever
                # Google account the browser happens to be signed into.
                "prompt": "select_account",
            }
        )
        return f"{self.AUTHORIZE_URL}?{query}"

    def fetch_profile(self, *, code: str, redirect_uri: str, code_verifier: str) -> OAuthProfile:
        payload = _post_json(
            self.TOKEN_URL,
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            {"Accept": "application/json"},
        )

        # The userinfo endpoint is read with the token we were just handed over
        # our own TLS connection to Google, so its answer needs no further
        # proof. Verifying the id_token instead would mean tracking Google's
        # rotating signing keys for no additional guarantee in this flow.
        info = _get_json(self.USERINFO_URL, _access_token(payload))
        if not isinstance(info, dict):
            raise OAuthError("Google returned an unexpected profile.")

        subject = info.get("sub")
        if not isinstance(subject, str) or not subject:
            raise OAuthError("Google did not return an account identifier.")

        email = info.get("email")
        return OAuthProfile(
            provider=self.name,
            account_id=subject,
            email=email if isinstance(email, str) and email else None,
            email_verified=info.get("email_verified") is True,
            full_name=info.get("name") if isinstance(info.get("name"), str) else None,
        )


class GitHubProvider(OAuthProvider):
    name = "github"
    label = "GitHub"

    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"
    SCOPES = "read:user user:email"

    def authorization_url(self, *, redirect_uri: str, state: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "scope": self.SCOPES,
                "state": state,
                # GitHub ignores PKCE today. Sending it costs nothing and means
                # the flow is already correct if and when they honour it.
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self.AUTHORIZE_URL}?{query}"

    def fetch_profile(self, *, code: str, redirect_uri: str, code_verifier: str) -> OAuthProfile:
        payload = _post_json(
            self.TOKEN_URL,
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            # Without this GitHub answers form-encoded, not JSON.
            {"Accept": "application/json"},
        )
        token = _access_token(payload)

        profile = _get_json(self.USER_URL, token, accept="application/vnd.github+json")
        if not isinstance(profile, dict):
            raise OAuthError("GitHub returned an unexpected profile.")

        account_id = profile.get("id")
        if account_id is None:
            raise OAuthError("GitHub did not return an account identifier.")

        email, verified = self._primary_email(token)
        name = profile.get("name") or profile.get("login")
        return OAuthProfile(
            provider=self.name,
            account_id=str(account_id),
            email=email,
            email_verified=verified,
            full_name=name if isinstance(name, str) else None,
        )

    def _primary_email(self, token: str) -> tuple[str | None, bool]:
        """GitHub's profile omits the email whenever the user hides it.

        The dedicated endpoint is the only way to learn both the primary
        address and whether GitHub has confirmed it - and confirmation is what
        decides whether this identity may attach to an existing account.
        """
        try:
            entries = _get_json(self.EMAILS_URL, token, accept="application/vnd.github+json")
        except OAuthError:
            # The scope may have been declined. Sign-in can still proceed as a
            # brand-new account; it simply cannot link to an existing one.
            logger.info("GitHub email scope unavailable; continuing without an address")
            return None, False

        if not isinstance(entries, list):
            return None, False
        for entry in entries:
            if (
                isinstance(entry, dict)
                and entry.get("primary")
                and isinstance(entry.get("email"), str)
            ):
                return entry["email"], entry.get("verified") is True
        return None, False
