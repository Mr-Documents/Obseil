"""Security properties, asserted rather than assumed.

Each test here corresponds to a line in the security review
(``docs/SECURITY_REVIEW.md``). They are deliberately blunt: they check the
property a reviewer would check by hand, so that a regression is caught by CI
rather than by an incident.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from tests.conftest import DEFAULT_PASSWORD

CSV = b"id,amount\n1,10.5\n2,20.0\n"


@pytest.fixture
def project_id(authed_client: TestClient) -> str:
    return authed_client.post("/api/v1/projects", json={"name": "Secure"}).json()["id"]


class TestSecretsAndConfiguration:
    def test_production_refuses_to_boot_with_a_default_secret(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.core.config import Settings

        with pytest.raises(PydanticValidationError, match="SECRET_KEY"):
            Settings(env="production", secret_key="change-me", debug=False)

    def test_production_refuses_to_boot_with_debug_enabled(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.core.config import Settings

        with pytest.raises(PydanticValidationError, match="DEBUG"):
            Settings(env="production", secret_key="x" * 48, debug=True)

    def test_no_secret_is_hardcoded_outside_configuration(self) -> None:
        """The only default secret lives in Settings, where production rejects it."""
        import pathlib

        source_root = pathlib.Path(__file__).resolve().parents[2] / "app"
        offenders = [
            path
            for path in source_root.rglob("*.py")
            if path.name != "config.py"
            and any(
                marker in path.read_text(encoding="utf-8")
                for marker in ("SECRET_KEY =", "password = 'admin", 'password = "admin')
            )
        ]
        assert offenders == []


class TestPasswordHandling:
    def test_passwords_are_never_returned(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "leak@example.com",
                "full_name": "Leak Test",
                "password": "correct-horse-1",
            },
        )
        body = response.text
        assert "correct-horse-1" not in body
        assert "hashed_password" not in body

    def test_passwords_are_stored_hashed_and_salted(self, client: TestClient, db: Session) -> None:
        for email in ("a@example.com", "b@example.com"):
            client.post(
                "/api/v1/auth/register",
                json={"email": email, "full_name": "T", "password": "same-password-1"},
            )

        hashes = [user.hashed_password for user in db.query(User).all()]
        assert all(value.startswith("$2b$") for value in hashes)
        assert len(set(hashes)) == len(hashes), "identical passwords must not share a hash"


class TestTokenHandling:
    def test_a_tampered_token_is_rejected(self, client: TestClient, user: User) -> None:
        token = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        ).json()["tokens"]["access_token"]

        header, payload, signature = token.split(".")
        forged = f"{header}.{payload}.{signature[:-4]}AAAA"

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    def test_the_none_algorithm_is_rejected(self, client: TestClient, user: User) -> None:
        """A classic JWT bypass: an unsigned token claiming `alg: none`."""
        import base64
        import json

        def segment(data: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

        forged = (
            f"{segment({'alg': 'none', 'typ': 'JWT'})}."
            f"{segment({'sub': user.id, 'type': 'access'})}."
        )

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    def test_a_bearer_prefix_is_required(self, client: TestClient, user: User) -> None:
        token = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        ).json()["tokens"]["access_token"]

        assert client.get("/api/v1/auth/me", headers={"Authorization": token}).status_code == 401


class TestAuthorizationCoverage:
    """Every resource-scoped endpoint must reject another user's id."""

    def test_every_scoped_endpoint_is_protected(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        owner = make_user(email="owner@example.com")
        owner_headers = auth_headers(owner)

        project = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=owner_headers
        ).json()["id"]
        dataset = client.post(
            f"/api/v1/projects/{project}/datasets",
            files={"file": ("data.csv", io.BytesIO(CSV), "text/csv")},
            headers=owner_headers,
        ).json()
        dataset_id = dataset["id"]
        analysis_id = dataset["latest_analysis"]["id"]

        intruder = auth_headers(user)
        forbidden = [
            ("GET", f"/api/v1/projects/{project}"),
            ("PATCH", f"/api/v1/projects/{project}"),
            ("DELETE", f"/api/v1/projects/{project}"),
            ("GET", f"/api/v1/projects/{project}/datasets"),
            ("GET", f"/api/v1/projects/{project}/history"),
            ("GET", f"/api/v1/projects/{project}/history/trend"),
            ("GET", f"/api/v1/datasets/{dataset_id}"),
            ("DELETE", f"/api/v1/datasets/{dataset_id}"),
            ("POST", f"/api/v1/datasets/{dataset_id}/analyze"),
            ("GET", f"/api/v1/datasets/{dataset_id}/statistics"),
            ("GET", f"/api/v1/datasets/{dataset_id}/preview"),
            ("GET", f"/api/v1/datasets/{dataset_id}/findings"),
            ("GET", f"/api/v1/datasets/{dataset_id}/findings/summary"),
            ("GET", f"/api/v1/datasets/{dataset_id}/anomalies"),
            ("GET", f"/api/v1/datasets/{dataset_id}/anomalies/overview"),
            ("GET", f"/api/v1/datasets/{dataset_id}/score"),
            ("GET", f"/api/v1/datasets/{dataset_id}/history"),
            ("GET", f"/api/v1/analyses/{analysis_id}/compare"),
            ("POST", f"/api/v1/reports/{analysis_id}/export"),
        ]

        for method, path in forbidden:
            response = client.request(method, path, headers=intruder, json={})
            assert (
                response.status_code == 404
            ), f"{method} {path} leaked (got {response.status_code})"

    def test_every_scoped_endpoint_requires_a_token(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        owner = make_user(email="owner2@example.com")
        headers = auth_headers(owner)
        project = client.post("/api/v1/projects", json={"name": "Theirs"}, headers=headers).json()[
            "id"
        ]

        for method, path in [
            ("GET", "/api/v1/projects"),
            ("POST", "/api/v1/projects"),
            ("GET", f"/api/v1/projects/{project}"),
            ("GET", "/api/v1/auth/me"),
            ("GET", "/api/v1/datasets/anything"),
            ("GET", "/api/v1/datasets/anything/findings"),
            ("POST", "/api/v1/reports/anything/export"),
        ]:
            response = client.request(method, path, json={})
            assert response.status_code == 401, f"{method} {path} did not require a token"


class TestUploadHardening:
    def test_a_traversal_filename_cannot_escape_the_storage_root(
        self, authed_client: TestClient, project_id: str, db: Session
    ) -> None:
        from app.models.dataset import Dataset

        authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("../../../../etc/passwd.csv", io.BytesIO(CSV), "text/csv")},
        )

        dataset = db.query(Dataset).one()
        assert ".." not in dataset.storage_key
        assert dataset.storage_key.startswith(f"projects/{project_id}/")
        # The stored path stays inside the configured root.
        stored = settings.storage_dir / dataset.storage_key
        assert stored.resolve().is_relative_to(settings.storage_dir.resolve())

    def test_the_storage_key_ignores_the_users_filename_entirely(
        self, authed_client: TestClient, project_id: str, db: Session
    ) -> None:
        from app.models.dataset import Dataset

        authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("payload$(whoami).csv", io.BytesIO(CSV), "text/csv")},
        )

        key = db.query(Dataset).one().storage_key
        assert "payload" not in key and "whoami" not in key

    def test_the_size_limit_is_enforced_while_streaming(
        self, authed_client: TestClient, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "max_upload_bytes", 256)

        response = authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("big.csv", io.BytesIO(b"id,v\n" + b"1,2\n" * 500), "text/csv")},
        )

        assert response.status_code == 413

    def test_an_oversized_upload_leaves_nothing_behind(
        self,
        authed_client: TestClient,
        project_id: str,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.models.dataset import Dataset

        monkeypatch.setattr(settings, "max_upload_bytes", 256)
        authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("big.csv", io.BytesIO(b"id,v\n" + b"1,2\n" * 500), "text/csv")},
        )

        assert db.query(Dataset).count() == 0
        # Scoped to this project: the storage root is shared across the module.
        project_dir = settings.storage_dir / "projects" / project_id
        assert list(project_dir.glob("*")) == [] if project_dir.exists() else True


class TestErrorDisclosure:
    def test_an_unexpected_error_never_returns_a_traceback(
        self, authed_client: TestClient, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import analysis_pipeline

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("secret internal detail: /etc/shadow")

        monkeypatch.setattr(analysis_pipeline, "run_analysis", explode)

        response = authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("data.csv", io.BytesIO(CSV), "text/csv")},
        )

        assert response.status_code == 500
        body = response.text
        assert "secret internal detail" not in body
        assert "Traceback" not in body
        assert "/etc/shadow" not in body
        # A reference the user can quote when reporting it.
        assert response.json()["error"]["request_id"]

    def test_validation_errors_do_not_echo_the_submitted_password(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "full_name": "T", "password": "sup3rsecret-value"},
        )

        assert response.status_code == 422
        assert "sup3rsecret-value" not in response.text


class TestTransportHeaders:
    def test_security_headers_are_present_on_every_response(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"

    def test_cors_is_restricted_to_configured_origins(self, client: TestClient) -> None:
        allowed = settings.cors_origin_list[0]

        permitted = client.get("/api/v1/health", headers={"Origin": allowed})
        assert permitted.headers.get("access-control-allow-origin") == allowed

        blocked = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
        assert blocked.headers.get("access-control-allow-origin") != "https://evil.example"


class TestInjection:
    def test_a_sql_payload_in_a_filter_is_treated_as_data(
        self, authed_client: TestClient, project_id: str, db: Session
    ) -> None:
        """SQLAlchemy binds parameters, but the property is worth asserting."""
        from app.models.project import Project

        authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("data.csv", io.BytesIO(CSV), "text/csv")},
        )
        dataset_id = authed_client.get(f"/api/v1/projects/{project_id}/datasets").json()["items"][
            0
        ]["id"]

        response = authed_client.get(
            f"/api/v1/datasets/{dataset_id}/findings",
            params={"search": "'; DROP TABLE projects; --"},
        )

        assert response.status_code == 200
        assert db.query(Project).count() == 1, "the table is still there"

    def test_a_script_payload_in_a_project_name_is_stored_verbatim(
        self, authed_client: TestClient
    ) -> None:
        """The API is not an HTML renderer: it stores and returns text as text.
        Escaping is React's job at the point of rendering."""
        payload = "<script>alert('x')</script>"

        created = authed_client.post("/api/v1/projects", json={"name": payload}).json()

        assert created["name"] == payload
        assert authed_client.get(f"/api/v1/projects/{created['id']}").json()["name"] == payload
