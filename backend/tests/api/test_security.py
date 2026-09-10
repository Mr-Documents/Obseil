"""Security properties, asserted rather than assumed.

Each test here corresponds to a line in the security review
(``docs/SECURITY_REVIEW.md``). They are deliberately blunt: they check the
property a reviewer would check by hand, so that a regression is caught by CI
rather than by an incident.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute, APIRouter
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.main import create_app
from app.models.user import User
from app.services import auth_service
from tests.conftest import DEFAULT_PASSWORD
from tests.fixtures import sample_bytes

CSV = b"id,amount\n1,10.5\n2,20.0\n"


#: Path parameters that name a resource somebody owns. Any route carrying one
#: has to reject an id belonging to another account.
OWNED_PATH_PARAMETERS = frozenset({"project_id", "dataset_id", "analysis_id", "finding_id"})

#: Every resource-scoped endpoint, as (method, path template).
#:
#: One list drives three properties: that each endpoint rejects another
#: account's id, that each rejects an anonymous caller, and - via
#: ``test_the_matrix_lists_every_scoped_route`` - that no scoped route is
#: missing from the list. That last check is what stops an endpoint shipping
#: untested, which is how the two findings routes and the dataset upload came
#: to be sitting here unverified.
SCOPED_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v1/projects/{project_id}"),
    ("PATCH", "/api/v1/projects/{project_id}"),
    ("DELETE", "/api/v1/projects/{project_id}"),
    ("GET", "/api/v1/projects/{project_id}/datasets"),
    ("POST", "/api/v1/projects/{project_id}/datasets"),
    ("GET", "/api/v1/projects/{project_id}/history"),
    ("GET", "/api/v1/projects/{project_id}/history/trend"),
    ("GET", "/api/v1/datasets/{dataset_id}"),
    ("DELETE", "/api/v1/datasets/{dataset_id}"),
    ("POST", "/api/v1/datasets/{dataset_id}/analyze"),
    ("GET", "/api/v1/datasets/{dataset_id}/statistics"),
    ("GET", "/api/v1/datasets/{dataset_id}/preview"),
    ("GET", "/api/v1/datasets/{dataset_id}/findings"),
    ("GET", "/api/v1/datasets/{dataset_id}/findings/summary"),
    ("GET", "/api/v1/datasets/{dataset_id}/anomalies"),
    ("GET", "/api/v1/datasets/{dataset_id}/anomalies/overview"),
    ("GET", "/api/v1/datasets/{dataset_id}/score"),
    ("GET", "/api/v1/datasets/{dataset_id}/history"),
    ("GET", "/api/v1/findings/{finding_id}"),
    ("PATCH", "/api/v1/findings/{finding_id}"),
    ("GET", "/api/v1/analyses/{analysis_id}/compare"),
    ("POST", "/api/v1/reports/{analysis_id}/export"),
)

#: A walk that finds nothing would make every check below vacuously pass, so
#: the enumeration is asserted against a floor. Raise it as routes are added.
MINIMUM_EXPECTED_ROUTES = 25


def _request_body(method: str, template: str) -> dict[str, Any]:
    """Whatever a request needs besides its path to reach the ownership check.

    The upload endpoint parses its multipart body while resolving dependencies,
    so without a file it fails validation first - and a 422 would be mistaken
    for a test that passed.
    """
    if method == "POST" and template.endswith("/datasets"):
        return {"files": {"file": ("data.csv", io.BytesIO(CSV), "text/csv")}}
    if method == "PATCH" and template.endswith("/findings/{finding_id}"):
        # Triage rejects an empty body during validation, which happens before
        # the handler runs. Without a valid body the request would 422 and
        # never reach the ownership check this test exists to exercise.
        return {"json": {"status": "reviewed"}}
    return {"json": {}}


def _api_routes() -> Iterator[tuple[str, str]]:
    """Every (method, path) the application actually serves.

    Walks the router tree rather than reading the OpenAPI schema, because a
    route hidden from the docs is exactly where a missing check would hide.
    """

    def walk(routes: list[Any], prefix: str = "") -> Iterator[tuple[str, str]]:
        for route in routes:
            if isinstance(route, APIRoute):
                for method in route.methods - {"HEAD", "OPTIONS"}:
                    yield method, prefix + route.path
            elif hasattr(route, "original_router"):  # a router included in the app
                yield from walk(route.original_router.routes, prefix + route.include_context.prefix)
            elif isinstance(route, APIRouter):
                yield from walk(route.routes, prefix + route.prefix)

    yield from walk(create_app().routes)


def _is_scoped(path: str) -> bool:
    return bool(set(re.findall(r"{(\w+)}", path)) & OWNED_PATH_PARAMETERS)


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


class TestPasswordHashCost:
    """The work factor is tunable, but only downwards outside production."""

    def test_production_refuses_a_weak_work_factor(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.core.config import MINIMUM_PRODUCTION_HASH_ROUNDS, Settings

        with pytest.raises(PydanticValidationError, match="PASSWORD_HASH_ROUNDS"):
            Settings(
                env="production",
                debug=False,
                secret_key="x" * 48,
                password_hash_rounds=MINIMUM_PRODUCTION_HASH_ROUNDS - 1,
            )

    def test_the_equal_timing_hash_matches_the_configured_cost(self) -> None:
        """The dummy hash stands in for a real one, so it must cost the same.

        Verifying a cheaper hash for unknown emails than for known ones makes
        login timing depend on whether the account exists - which is the
        enumeration oracle this dummy hash was introduced to remove.
        """
        prefix = f"$2b${settings.password_hash_rounds:02d}$"
        assert auth_service._DUMMY_HASH.startswith(prefix)
        assert hash_password("anything").startswith(prefix)


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

    def test_the_matrix_lists_every_scoped_route(self) -> None:
        """The list below must not fall behind the router.

        Without this, adding a route is enough to ship it unprotected: the
        other two tests only check what someone remembered to write down.
        """
        served = set(_api_routes())
        assert len(served) >= MINIMUM_EXPECTED_ROUTES, (
            f"only found {len(served)} routes - the router walk is broken, "
            "so every authorization check below is passing vacuously"
        )

        scoped = {(method, path) for method, path in served if _is_scoped(path)}
        missing = scoped - set(SCOPED_ENDPOINTS)
        stale = set(SCOPED_ENDPOINTS) - scoped

        assert not missing, (
            "these scoped routes are not in SCOPED_ENDPOINTS, so nothing proves "
            f"they reject another account: {sorted(missing)}"
        )
        assert not stale, f"SCOPED_ENDPOINTS lists routes that no longer exist: {sorted(stale)}"

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
        # The fixture of record rather than a toy frame: a dataset with real
        # defects is the only way to get a finding id to attempt access to.
        dataset = client.post(
            f"/api/v1/projects/{project}/datasets",
            files={
                "file": (
                    "invalid_values.csv",
                    io.BytesIO(sample_bytes("invalid_values.csv")),
                    "text/csv",
                )
            },
            headers=owner_headers,
        ).json()
        findings = client.get(
            f"/api/v1/datasets/{dataset['id']}/findings", headers=owner_headers
        ).json()["items"]
        assert findings, "the sample must produce findings, or the finding routes go untested"
        finding = findings[0]

        ids = {
            "project_id": project,
            "dataset_id": dataset["id"],
            "analysis_id": dataset["latest_analysis"]["id"],
            "finding_id": finding["id"],
        }

        intruder = auth_headers(user)
        for method, template in SCOPED_ENDPOINTS:
            path = template.format(**ids)
            response = client.request(
                method, path, headers=intruder, **_request_body(method, template)
            )
            assert (
                response.status_code == 404
            ), f"{method} {template} leaked (got {response.status_code})"

    def test_every_scoped_endpoint_requires_a_token(self, client: TestClient) -> None:
        """An anonymous caller is refused before any lookup happens.

        Real ids are unnecessary: the answer must not depend on whether the
        resource exists, which is the same reason these routes answer 404
        rather than 403 for a signed-in stranger.
        """
        placeholders = dict.fromkeys(OWNED_PATH_PARAMETERS, "does-not-matter")

        for method, template in SCOPED_ENDPOINTS:
            path = template.format(**placeholders)
            response = client.request(method, path, **_request_body(method, template))
            assert (
                response.status_code == 401
            ), f"{method} {template} did not require a token (got {response.status_code})"

    def test_unscoped_endpoints_still_require_a_token(self, client: TestClient) -> None:
        """The collection routes are scoped to the caller, not to a path id."""
        for method, path in (
            ("GET", "/api/v1/projects"),
            ("POST", "/api/v1/projects"),
            ("GET", "/api/v1/auth/me"),
        ):
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


class TestLoginRateLimiting:
    """Repeated failures from one caller are slowed down.

    The counter is keyed on the caller's address, never on the submitted
    email - see ``app/core/ratelimit`` for why that distinction is the whole
    point of the design.
    """

    def _fail_login(self, client: TestClient, email: str = "nobody@example.com"):
        return client.post(
            "/api/v1/auth/login", json={"email": email, "password": "definitely-wrong"}
        )

    def test_repeated_failures_are_eventually_refused(self, client: TestClient) -> None:
        for _ in range(settings.login_max_attempts):
            assert self._fail_login(client).status_code == 401

        response = self._fail_login(client)
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"

    def test_the_refusal_says_how_long_to_wait(self, client: TestClient) -> None:
        for _ in range(settings.login_max_attempts):
            self._fail_login(client)

        response = self._fail_login(client)
        retry_after = int(response.headers["Retry-After"])
        assert 0 < retry_after <= settings.login_attempt_window_seconds
        assert response.json()["error"]["details"]["retry_after_seconds"] == retry_after

    def test_being_limited_does_not_reveal_whether_an_account_exists(
        self, client: TestClient, user: User
    ) -> None:
        """The 429 must be as uninformative as the 401 it replaces.

        If a rate-limited response differed for a real account, the limiter
        would have reintroduced exactly the enumeration oracle that the equal
        401 responses were designed to remove.
        """
        for _ in range(settings.login_max_attempts):
            self._fail_login(client)

        real = self._fail_login(client, email=user.email)
        unknown = self._fail_login(client, email="no-such-account@example.com")

        assert real.status_code == unknown.status_code == 429
        assert real.json()["error"]["message"] == unknown.json()["error"]["message"]
        assert real.json()["error"]["code"] == unknown.json()["error"]["code"]

    def test_the_right_password_is_refused_once_the_limit_is_reached(
        self, client: TestClient, user: User
    ) -> None:
        """Otherwise the limit is no obstacle to guessing: the guess that
        happens to be correct would still be accepted."""
        for _ in range(settings.login_max_attempts):
            self._fail_login(client)

        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        )
        assert response.status_code == 429

    def test_signing_in_successfully_clears_the_count(self, client: TestClient, user: User) -> None:
        """A person who mistypes their password a few times, then gets it
        right, must not be closer to a lockout than someone who never did."""
        for _ in range(settings.login_max_attempts - 1):
            assert self._fail_login(client).status_code == 401

        good = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        )
        assert good.status_code == 200

        for _ in range(settings.login_max_attempts - 1):
            assert self._fail_login(client).status_code == 401

    def test_registration_is_not_blocked_by_login_failures(self, client: TestClient) -> None:
        """The limit belongs to the login endpoint, not to the whole API."""
        for _ in range(settings.login_max_attempts + 2):
            self._fail_login(client)

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "new.person@example.com",
                "password": DEFAULT_PASSWORD,
                "full_name": "New Person",
            },
        )
        assert response.status_code == 201
