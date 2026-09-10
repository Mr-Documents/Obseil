"""Third-party sign-in, end to end through the API.

The provider is replaced with a stub. That is the point: these tests are about
*Obseil's* half of the flow - the CSRF state, the linking rules, the handoff
code - not about whether Google's servers work. The stub lets the dangerous
cases (an unverified email, a mismatched state, a replayed code) be exercised,
which no amount of talking to the real Google would allow.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.oauth import registry
from app.oauth.base import OAuthError, OAuthProfile, OAuthProvider
from app.services.oauth_handoff import handoff_store
from tests.conftest import DEFAULT_PASSWORD

START = "/api/v1/auth/oauth/stub/start"
CALLBACK = "/api/v1/auth/oauth/stub/callback"


class StubProvider(OAuthProvider):
    """Answers with whatever the test asked for."""

    name = "stub"
    label = "Stub"

    def __init__(self) -> None:
        super().__init__("stub-client-id", "stub-client-secret")
        self.profile = OAuthProfile(
            provider="stub",
            account_id="provider-user-1",
            email="linked@example.com",
            email_verified=True,
            full_name="Linked Person",
        )
        self.raise_on_exchange: OAuthError | None = None
        self.seen_verifier: str | None = None

    def authorization_url(self, *, redirect_uri: str, state: str, code_challenge: str) -> str:
        return f"https://stub.test/authorize?state={state}&code_challenge={code_challenge}"

    def fetch_profile(self, *, code: str, redirect_uri: str, code_verifier: str) -> OAuthProfile:
        if self.raise_on_exchange is not None:
            raise self.raise_on_exchange
        self.seen_verifier = code_verifier
        return self.profile


@pytest.fixture
def stub() -> Iterator[StubProvider]:
    provider = StubProvider()
    original = registry._providers
    registry._providers = {provider.name: provider}
    handoff_store.clear()
    try:
        yield provider
    finally:
        registry._providers = original
        handoff_store.clear()


def begin(client: TestClient) -> str:
    """Run the start step and return the state the browser was given."""
    response = client.get(START, follow_redirects=False)
    assert response.status_code == 307
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def complete(client: TestClient, state: str, code: str = "provider-code"):
    return client.get(CALLBACK, params={"state": state, "code": code}, follow_redirects=False)


def handoff_code(response) -> str:
    return parse_qs(urlparse(response.headers["location"]).query)["code"][0]


class TestProviderListing:
    def test_nothing_is_offered_when_nothing_is_configured(self, client: TestClient) -> None:
        """Obseil ships with no credentials, so the UI must render no buttons."""
        assert client.get("/api/v1/auth/oauth/providers").json() == []

    def test_a_configured_provider_is_listed(self, client: TestClient, stub: StubProvider) -> None:
        assert client.get("/api/v1/auth/oauth/providers").json() == [
            {"name": "stub", "label": "Stub"}
        ]

    def test_starting_an_unknown_provider_is_a_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/auth/oauth/nope/start").status_code == 404


class TestTheStartStep:
    def test_it_redirects_to_the_provider(self, client: TestClient, stub: StubProvider) -> None:
        response = client.get(START, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"].startswith("https://stub.test/authorize")

    def test_it_sets_an_httponly_state_cookie(self, client: TestClient, stub: StubProvider) -> None:
        """Readable by script, and the CSRF state stops being a secret."""
        response = client.get(START, follow_redirects=False)
        cookie = response.headers["set-cookie"]
        assert "obseil_oauth_state=" in cookie
        assert "httponly" in cookie.lower()
        assert "samesite=lax" in cookie.lower()

    def test_the_pkce_verifier_never_reaches_the_browser(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        """Only the challenge may travel; the verifier is what proves the
        callback came from the same browser that started the flow."""
        response = client.get(START, follow_redirects=False)
        location = response.headers["location"]
        assert "code_challenge=" in location
        assert "code_verifier" not in location


class TestCsrfProtection:
    def test_a_callback_with_no_state_cookie_is_refused(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        response = complete(client, "some-state")
        assert "error=" in response.headers["location"]

    def test_a_mismatched_state_is_refused(self, client: TestClient, stub: StubProvider) -> None:
        """The attack this stops: an attacker sends a victim a callback URL
        carrying the attacker's code, attaching their identity to the victim."""
        begin(client)
        response = complete(client, "not-the-state-we-issued")
        assert "error=" in response.headers["location"]
        assert "code=" not in response.headers["location"]

    def test_a_tampered_state_cookie_is_refused(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        state = begin(client)
        client.cookies.set("obseil_oauth_state", "not.a.valid.jwt")
        assert "error=" in complete(client, state).headers["location"]

    def test_a_good_state_is_accepted(self, client: TestClient, stub: StubProvider) -> None:
        state = begin(client)
        response = complete(client, state)
        assert "code=" in response.headers["location"]

    def test_the_state_cookie_is_cleared_after_use(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        """Left in place, a stale attempt could be replayed against a later callback."""
        state = begin(client)
        response = complete(client, state)
        assert 'obseil_oauth_state=""' in response.headers.get("set-cookie", "")


class TestAccountLinking:
    """The rules that decide whose account a provider identity gets."""

    def test_a_new_identity_creates_an_account(
        self, client: TestClient, db: Session, stub: StubProvider
    ) -> None:
        state = begin(client)
        complete(client, state)

        user = db.scalar(select(User).where(User.email == "linked@example.com"))
        assert user is not None
        assert user.full_name == "Linked Person"
        assert user.hashed_password is None  # no password at all, not a random one

    def test_a_verified_email_links_to_the_existing_account(
        self, client: TestClient, db: Session, make_user, stub: StubProvider
    ) -> None:
        """Safe *because* the provider confirmed the address."""
        existing = make_user(email="linked@example.com")
        state = begin(client)
        complete(client, state)

        links = list(db.scalars(select(OAuthAccount).where(OAuthAccount.user_id == existing.id)))
        assert len(links) == 1
        assert db.scalar(select(User).where(User.email == "linked@example.com")).id == existing.id

    def test_an_unverified_email_never_links_to_an_existing_account(
        self, client: TestClient, db: Session, make_user, stub: StubProvider
    ) -> None:
        """The account-takeover case, and the reason the flag is checked.

        Anyone able to make a provider account claiming someone else's address
        would otherwise be handed that person's Obseil account.
        """
        existing = make_user(email="linked@example.com")
        stub.profile = OAuthProfile(
            provider="stub",
            account_id="attacker-account",
            email="linked@example.com",
            email_verified=False,
            full_name="Not The Owner",
        )

        state = begin(client)
        response = complete(client, state)

        assert "error=" in response.headers["location"]
        assert "code=" not in response.headers["location"]
        assert db.scalar(select(OAuthAccount).where(OAuthAccount.user_id == existing.id)) is None

    def test_a_provider_with_no_email_is_refused(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        stub.profile = OAuthProfile(
            provider="stub",
            account_id="no-email",
            email=None,
            email_verified=False,
            full_name="Anonymous",
        )
        assert "error=" in complete(client, begin(client)).headers["location"]

    def test_signing_in_twice_reuses_the_same_account(
        self, client: TestClient, db: Session, stub: StubProvider
    ) -> None:
        complete(client, begin(client))
        complete(client, begin(client))

        assert len(list(db.scalars(select(User).where(User.email == "linked@example.com")))) == 1
        assert len(list(db.scalars(select(OAuthAccount)))) == 1

    def test_the_identity_is_the_subject_id_not_the_email(
        self, client: TestClient, db: Session, stub: StubProvider
    ) -> None:
        """A changed address at the provider must not create a second account,
        because the subject id is what was linked."""
        complete(client, begin(client))
        stub.profile = OAuthProfile(
            provider="stub",
            account_id="provider-user-1",  # same person
            email="changed@example.com",  # new address
            email_verified=True,
            full_name="Linked Person",
        )
        complete(client, begin(client))

        assert len(list(db.scalars(select(User)))) == 1
        assert len(list(db.scalars(select(OAuthAccount)))) == 1


class TestTheHandoff:
    def test_the_code_exchanges_for_tokens(self, client: TestClient, stub: StubProvider) -> None:
        code = handoff_code(complete(client, begin(client)))
        body = client.post("/api/v1/auth/oauth/exchange", json={"code": code}).json()

        assert body["user"]["email"] == "linked@example.com"
        assert body["tokens"]["access_token"]
        assert body["tokens"]["refresh_token"]

    def test_the_returned_token_works(self, client: TestClient, stub: StubProvider) -> None:
        code = handoff_code(complete(client, begin(client)))
        tokens = client.post("/api/v1/auth/oauth/exchange", json={"code": code}).json()["tokens"]

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "linked@example.com"

    def test_no_token_ever_appears_in_a_redirect_url(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        """Tokens in a URL end up in browser history. Only the one-time code travels."""
        response = complete(client, begin(client))
        location = response.headers["location"]
        assert "access_token" not in location
        assert "refresh_token" not in location

    def test_a_code_cannot_be_used_twice(self, client: TestClient, stub: StubProvider) -> None:
        code = handoff_code(complete(client, begin(client)))
        assert client.post("/api/v1/auth/oauth/exchange", json={"code": code}).status_code == 200
        assert client.post("/api/v1/auth/oauth/exchange", json={"code": code}).status_code == 401

    def test_an_unknown_code_is_refused(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/oauth/exchange", json={"code": "x" * 40})
        assert response.status_code == 401


class TestFailureHandling:
    def test_a_cancelled_sign_in_lands_on_the_frontend(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        response = client.get(CALLBACK, params={"error": "access_denied"}, follow_redirects=False)
        assert response.status_code == 307
        assert "error=" in response.headers["location"]

    def test_a_provider_failure_is_not_leaked_to_the_user(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        """The provider's message can name the client id and the exact reason."""
        stub.raise_on_exchange = OAuthError("invalid_client: secret 'hunter2' is wrong")
        state = begin(client)
        location = complete(client, state).headers["location"]

        assert "error=" in location
        assert "hunter2" not in location
        assert "invalid_client" not in location


class TestPasswordAndProviderAccountsCoexist:
    def test_a_provider_account_cannot_be_signed_into_with_a_password(
        self, client: TestClient, stub: StubProvider
    ) -> None:
        """It has no password. The attempt must fail, not crash, and not
        reveal that this address is a provider-only account."""
        complete(client, begin(client))

        response = client.post(
            "/api/v1/auth/login",
            json={"email": "linked@example.com", "password": DEFAULT_PASSWORD},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_that_refusal_is_indistinguishable_from_a_wrong_password(
        self, client: TestClient, make_user, stub: StubProvider
    ) -> None:
        make_user(email="haspassword@example.com")
        complete(client, begin(client))

        provider_only = client.post(
            "/api/v1/auth/login",
            json={"email": "linked@example.com", "password": "wrong-password"},
        )
        wrong_password = client.post(
            "/api/v1/auth/login",
            json={"email": "haspassword@example.com", "password": "wrong-password"},
        )

        assert provider_only.status_code == wrong_password.status_code
        assert provider_only.json()["error"]["code"] == wrong_password.json()["error"]["code"]
        assert provider_only.json()["error"]["message"] == wrong_password.json()["error"]["message"]
