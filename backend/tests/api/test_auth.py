"""Registration, login, refresh and the protected-route boundary."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import DEFAULT_PASSWORD

REGISTRATION = {
    "email": "ada@example.com",
    "full_name": "Ada Lovelace",
    "password": "analytical-engine-1843",
}


def register(client: TestClient, **overrides: object) -> object:
    return client.post("/api/v1/auth/register", json={**REGISTRATION, **overrides})


class TestRegistration:
    def test_creates_an_account_and_signs_in(self, client: TestClient) -> None:
        response = register(client)

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "ada@example.com"
        assert body["user"]["full_name"] == "Ada Lovelace"
        assert body["tokens"]["access_token"]
        assert body["tokens"]["refresh_token"]
        assert body["tokens"]["token_type"] == "bearer"
        assert body["tokens"]["expires_in"] > 0

    def test_never_returns_the_password_hash(self, client: TestClient) -> None:
        body = register(client).json()
        assert "password" not in str(body)
        assert "hashed_password" not in body["user"]

    def test_stores_the_password_hashed(self, client: TestClient, db: Session) -> None:
        register(client)
        user = db.query(User).filter_by(email="ada@example.com").one()
        assert user.hashed_password != REGISTRATION["password"]
        assert user.hashed_password.startswith("$2b$")

    def test_email_is_normalised_to_lower_case(self, client: TestClient) -> None:
        body = register(client, email="  Ada@Example.COM  ").json()
        assert body["user"]["email"] == "ada@example.com"

    def test_duplicate_email_is_rejected_case_insensitively(self, client: TestClient) -> None:
        register(client)
        response = register(client, email="ADA@example.com")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_already_registered"

    def test_rejects_a_malformed_email(self, client: TestClient) -> None:
        assert register(client, email="not-an-email").status_code == 422

    def test_rejects_a_short_password(self, client: TestClient) -> None:
        response = register(client, password="ab1")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_rejects_a_password_with_no_digit(self, client: TestClient) -> None:
        assert register(client, password="onlyletters").status_code == 422

    def test_rejects_a_blank_name(self, client: TestClient) -> None:
        assert register(client, full_name="   ").status_code == 422


class TestLogin:
    def test_returns_tokens_for_valid_credentials(self, client: TestClient, user: User) -> None:
        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["user"]["id"] == user.id

    def test_email_is_case_insensitive(self, client: TestClient, user: User) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": user.email.upper(), "password": DEFAULT_PASSWORD},
        )
        assert response.status_code == 200

    def test_wrong_password_is_rejected(self, client: TestClient, user: User) -> None:
        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "wrong-password-1"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_unknown_email_gives_the_same_error_as_a_wrong_password(
        self, client: TestClient, user: User
    ) -> None:
        """Different messages here would let an attacker enumerate accounts."""
        unknown = client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever-1"}
        )
        wrong = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "whatever-1"}
        )

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["error"] == {
            **wrong.json()["error"],
            "request_id": unknown.json()["error"]["request_id"],
        }

    def test_deactivated_account_cannot_sign_in(
        self, client: TestClient, db: Session, user: User
    ) -> None:
        user.is_active = False
        db.commit()

        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "account_inactive"


class TestProtectedRoutes:
    def test_me_requires_a_token(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"

    def test_me_returns_the_signed_in_user(self, authed_client: TestClient, user: User) -> None:
        response = authed_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        assert response.json()["id"] == user.id

    def test_garbage_token_is_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
        )
        assert response.status_code == 401

    def test_refresh_token_is_not_accepted_as_an_access_token(
        self, client: TestClient, user: User
    ) -> None:
        tokens = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        ).json()["tokens"]

        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
        )
        assert response.status_code == 401

    def test_token_for_a_deleted_account_is_rejected(
        self,
        client: TestClient,
        db: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        doomed = make_user(email="doomed@example.com")
        headers = auth_headers(doomed)
        db.delete(doomed)
        db.commit()

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


class TestRefresh:
    def test_exchanges_a_refresh_token_for_a_new_pair(self, client: TestClient, user: User) -> None:
        tokens = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        ).json()["tokens"]

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 200
        refreshed = response.json()
        assert refreshed["access_token"]
        # Rotated, not reissued: the old refresh token should not come back.
        assert refreshed["refresh_token"] != tokens["refresh_token"]

    def test_an_access_token_cannot_be_used_to_refresh(
        self, client: TestClient, user: User
    ) -> None:
        tokens = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        ).json()["tokens"]

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
        )
        assert response.status_code == 401

    def test_rejects_a_forged_token(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/auth/refresh", json={"refresh_token": "abc.def.ghi"}).status_code
            == 401
        )


def test_logout_is_idempotent_and_needs_no_token(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"]
