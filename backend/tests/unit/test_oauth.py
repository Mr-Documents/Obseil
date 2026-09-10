"""PKCE, provider request building, and the handoff store."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from app.oauth.base import PkcePair
from app.oauth.providers import GitHubProvider, GoogleProvider
from app.oauth.registry import build_providers
from app.schemas.auth import TokenPair
from app.services.oauth_handoff import HandoffStore


def tokens(marker: str = "a") -> TokenPair:
    return TokenPair(
        access_token=f"access-{marker}",
        refresh_token=f"refresh-{marker}",
        expires_in=1800,
    )


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestPkce:
    def test_the_challenge_is_the_sha256_of_the_verifier(self) -> None:
        pair = PkcePair.generate()
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(pair.verifier.encode("ascii")).digest())
            .decode("ascii")
            .rstrip("=")
        )
        assert pair.challenge == expected

    def test_the_challenge_is_unpadded(self) -> None:
        """RFC 7636 requires base64url with the padding removed."""
        assert "=" not in PkcePair.generate().challenge

    def test_the_verifier_is_within_the_permitted_length(self) -> None:
        assert 43 <= len(PkcePair.generate().verifier) <= 128

    def test_every_pair_is_unique(self) -> None:
        assert len({PkcePair.generate().verifier for _ in range(50)}) == 50


class TestAuthorizationUrls:
    def test_google_asks_for_a_code_with_pkce(self) -> None:
        url = GoogleProvider("client-id", "secret").authorization_url(
            redirect_uri="https://obseil.test/api/v1/auth/oauth/google/callback",
            state="the-state",
            code_challenge="the-challenge",
        )
        query = parse_qs(urlparse(url).query)
        assert urlparse(url).netloc == "accounts.google.com"
        assert query["response_type"] == ["code"]
        assert query["client_id"] == ["client-id"]
        assert query["state"] == ["the-state"]
        assert query["code_challenge"] == ["the-challenge"]
        assert query["code_challenge_method"] == ["S256"]

    def test_the_client_secret_never_appears_in_the_browser_url(self) -> None:
        """It is a *secret*; only the server-side token exchange may carry it."""
        for provider in (GoogleProvider("id", "top-secret"), GitHubProvider("id", "top-secret")):
            url = provider.authorization_url(
                redirect_uri="https://obseil.test/cb", state="s", code_challenge="c"
            )
            assert "top-secret" not in url

    def test_github_requests_the_email_scope(self) -> None:
        """Without it the verified address cannot be read, and no account can be linked."""
        url = GitHubProvider("id", "secret").authorization_url(
            redirect_uri="https://obseil.test/cb", state="s", code_challenge="c"
        )
        assert "user:email" in parse_qs(urlparse(url).query)["scope"][0]


class TestRegistry:
    def test_a_provider_without_credentials_is_not_offered(self, monkeypatch) -> None:
        from app.core.config import settings

        monkeypatch.setattr(settings, "oauth_google_client_id", "", raising=False)
        monkeypatch.setattr(settings, "oauth_google_client_secret", "", raising=False)
        monkeypatch.setattr(settings, "oauth_github_client_id", "", raising=False)
        monkeypatch.setattr(settings, "oauth_github_client_secret", "", raising=False)
        assert build_providers() == {}

    def test_half_configured_is_still_not_offered(self, monkeypatch) -> None:
        """An id without a secret cannot complete the flow, so offering the
        button would only produce a failure the user cannot act on."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "oauth_google_client_id", "an-id", raising=False)
        monkeypatch.setattr(settings, "oauth_google_client_secret", "", raising=False)
        monkeypatch.setattr(settings, "oauth_github_client_id", "", raising=False)
        monkeypatch.setattr(settings, "oauth_github_client_secret", "", raising=False)
        assert "google" not in build_providers()

    def test_a_configured_provider_is_offered(self, monkeypatch) -> None:
        from app.core.config import settings

        monkeypatch.setattr(settings, "oauth_google_client_id", "an-id", raising=False)
        monkeypatch.setattr(settings, "oauth_google_client_secret", "a-secret", raising=False)
        assert "google" in build_providers()


class TestHandoffStore:
    def test_a_code_can_be_redeemed_once(self) -> None:
        store = HandoffStore()
        code = store.issue(tokens())
        assert store.redeem(code) is not None

    def test_a_code_cannot_be_redeemed_twice(self) -> None:
        """The whole point of a handoff code: replaying a leaked one is useless."""
        store = HandoffStore()
        code = store.issue(tokens())
        store.redeem(code)
        assert store.redeem(code) is None

    def test_an_unknown_code_is_refused(self) -> None:
        assert HandoffStore().redeem("never-issued") is None

    def test_a_code_expires(self) -> None:
        clock = FakeClock()
        store = HandoffStore(ttl_seconds=60, clock=clock)
        code = store.issue(tokens())
        clock.advance(61)
        assert store.redeem(code) is None

    def test_a_code_still_works_just_inside_the_window(self) -> None:
        clock = FakeClock()
        store = HandoffStore(ttl_seconds=60, clock=clock)
        code = store.issue(tokens())
        clock.advance(59)
        assert store.redeem(code) is not None

    def test_codes_are_unguessable(self) -> None:
        store = HandoffStore()
        issued = {store.issue(tokens()) for _ in range(100)}
        assert len(issued) == 100
        assert all(len(code) >= 32 for code in issued)

    def test_each_code_returns_its_own_tokens(self) -> None:
        store = HandoffStore()
        first, second = store.issue(tokens("one")), store.issue(tokens("two"))
        assert store.redeem(second).access_token == "access-two"  # type: ignore[union-attr]
        assert store.redeem(first).access_token == "access-one"  # type: ignore[union-attr]

    def test_expired_codes_do_not_accumulate(self) -> None:
        clock = FakeClock()
        store = HandoffStore(ttl_seconds=60, clock=clock)
        for _ in range(50):
            store.issue(tokens())
        clock.advance(61)
        store.issue(tokens())
        assert len(store._codes) == 1


@pytest.mark.parametrize("provider", [GoogleProvider, GitHubProvider])
def test_providers_declare_a_name_and_label(provider) -> None:
    instance = provider("id", "secret")
    assert instance.name and instance.label
    assert instance.is_configured
