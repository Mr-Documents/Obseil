"""The shape every third-party sign-in provider has to fit.

Obseil implements the **authorization code flow with PKCE, entirely on the
server**. The browser never sees the client secret and never handles a
provider token: it is redirected to the provider, the provider redirects back
to the API, and the API does the code exchange over its own TLS connection.

The alternative - letting the SPA talk to the provider and post an id token to
the API - needs the API to verify that token's signature against the provider's
rotating keys, and is easy to get subtly wrong. Exchanging the code
server-side means the profile below arrives over a direct, authenticated
channel with the provider, so it can be trusted without further proof.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OAuthProfile:
    """Who the provider says this is.

    ``account_id`` is the provider's stable subject identifier and is the only
    field treated as identity. ``email`` is descriptive, and is trusted enough
    to link to an existing Obseil account **only** when ``email_verified`` is
    true - see ``services/oauth_service.py`` for why that distinction carries
    the whole security of account linking.
    """

    provider: str
    account_id: str
    email: str | None
    email_verified: bool
    full_name: str | None


@dataclass(frozen=True)
class PkcePair:
    """A PKCE verifier and the challenge derived from it."""

    verifier: str
    challenge: str

    @classmethod
    def generate(cls) -> PkcePair:
        # 32 random bytes, URL-safe, unpadded: comfortably inside RFC 7636's
        # 43-128 character range.
        verifier = secrets.token_urlsafe(32)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return cls(verifier=verifier, challenge=challenge)


class OAuthError(Exception):
    """The provider refused, or answered with something unusable."""


class OAuthProvider(ABC):
    """One sign-in provider.

    Adding another means implementing this and registering it - the routes,
    the linking rules and the frontend need no change, the same way a new
    quality detector needs no change to the engine.
    """

    #: Stable key used in URLs, the database and the UI.
    name: str
    #: Human-readable, for the button.
    label: str

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def is_configured(self) -> bool:
        """A provider without credentials is not offered to anyone."""
        return bool(self.client_id and self.client_secret)

    @abstractmethod
    def authorization_url(self, *, redirect_uri: str, state: str, code_challenge: str) -> str:
        """Where to send the browser to begin."""

    @abstractmethod
    def fetch_profile(self, *, code: str, redirect_uri: str, code_verifier: str) -> OAuthProfile:
        """Exchange the callback code for the signed-in user's profile."""
