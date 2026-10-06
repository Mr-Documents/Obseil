"""Rule CRUD, validation, versioning and the ownership boundary."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User

RULE = {
    "name": "Currency must be one we settle",
    "description": "Settlement only supports these four.",
    "column_name": "currency",
    "predicate": "allowed_values",
    "parameters": {"values": ["GBP", "USD", "EUR", "JPY"]},
    "severity": "high",
    "dimension": "validity",
}


def project_id(client: TestClient, **kwargs: object) -> str:
    """Create a project and return its id."""
    response = client.post("/api/v1/projects", json={"name": "Settlement"}, **kwargs)  # type: ignore[arg-type]
    return str(response.json()["id"])


class TestCreate:
    def test_creates_a_rule(self, authed_client: TestClient) -> None:
        response = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules", json=RULE
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == RULE["name"]
        assert body["predicate"] == "allowed_values"
        assert body["parameters"]["values"] == ["GBP", "USD", "EUR", "JPY"]
        assert body["enabled"] is True
        assert body["version"] == 1

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post("/api/v1/projects/anything/rules", json=RULE)
        assert response.status_code == 401

    def test_renders_a_readable_predicate_label(self, authed_client: TestClient) -> None:
        body = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules", json=RULE
        ).json()
        assert body["predicate_label"] == "Must be one of"

    def test_collapses_whitespace_in_the_name(self, authed_client: TestClient) -> None:
        body = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules",
            json={**RULE, "name": "  Currency   check  "},
        ).json()
        assert body["name"] == "Currency check"

    def test_rejects_a_duplicate_name_in_the_same_project(self, authed_client: TestClient) -> None:
        pid = project_id(authed_client)
        authed_client.post(f"/api/v1/projects/{pid}/rules", json=RULE)

        response = authed_client.post(f"/api/v1/projects/{pid}/rules", json=RULE)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_allows_the_same_name_in_a_different_project(self, authed_client: TestClient) -> None:
        first = project_id(authed_client)
        authed_client.post(f"/api/v1/projects/{first}/rules", json=RULE)

        second = authed_client.post("/api/v1/projects", json={"name": "Other"}).json()["id"]
        assert authed_client.post(f"/api/v1/projects/{second}/rules", json=RULE).status_code == 201

    def test_unknown_project_is_a_404(self, authed_client: TestClient) -> None:
        response = authed_client.post(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/rules", json=RULE
        )
        assert response.status_code == 404


class TestValidation:
    def test_rejects_an_unknown_predicate(self, authed_client: TestClient) -> None:
        response = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules",
            json={**RULE, "predicate": "vibes"},
        )
        assert response.status_code == 422

    def test_rejects_a_misspelled_parameter(self, authed_client: TestClient) -> None:
        """`extra="forbid"` is what stops a rule silently never firing."""
        response = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules",
            json={**RULE, "parameters": {"value": ["GBP"]}},
        )
        assert response.status_code == 422

    def test_rejects_parameters_that_do_not_suit_the_predicate(
        self, authed_client: TestClient
    ) -> None:
        response = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules",
            json={**RULE, "predicate": "range", "parameters": {}},
        )
        assert response.status_code == 422

    def test_rejects_a_column_predicate_without_a_column(self, authed_client: TestClient) -> None:
        response = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules",
            json={**RULE, "column_name": None},
        )
        assert response.status_code == 422

    def test_rejects_the_anomaly_dimension(self, authed_client: TestClient) -> None:
        """That dimension belongs to the model, not to a deterministic rule."""
        response = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules",
            json={**RULE, "dimension": "anomaly"},
        )
        assert response.status_code == 422

    def test_rejects_an_uncompilable_regex(self, authed_client: TestClient) -> None:
        response = authed_client.post(
            f"/api/v1/projects/{project_id(authed_client)}/rules",
            json={
                **RULE,
                "predicate": "pattern",
                "parameters": {"regex": "([unclosed"},
            },
        )
        assert response.status_code == 422


class TestList:
    def test_returns_an_empty_page_for_a_new_project(self, authed_client: TestClient) -> None:
        body = authed_client.get(f"/api/v1/projects/{project_id(authed_client)}/rules").json()
        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_lists_most_recent_first(self, authed_client: TestClient) -> None:
        pid = project_id(authed_client)
        for name in ("First", "Second", "Third"):
            authed_client.post(f"/api/v1/projects/{pid}/rules", json={**RULE, "name": name})

        items = authed_client.get(f"/api/v1/projects/{pid}/rules").json()["items"]
        assert [item["name"] for item in items] == ["Third", "Second", "First"]

    def test_paginates(self, authed_client: TestClient) -> None:
        pid = project_id(authed_client)
        for index in range(5):
            authed_client.post(
                f"/api/v1/projects/{pid}/rules", json={**RULE, "name": f"Rule {index}"}
            )

        page = authed_client.get(
            f"/api/v1/projects/{pid}/rules", params={"limit": 2, "offset": 2}
        ).json()
        assert page["total"] == 5
        assert len(page["items"]) == 2

    def test_does_not_leak_another_projects_rules(self, authed_client: TestClient) -> None:
        first = project_id(authed_client)
        authed_client.post(f"/api/v1/projects/{first}/rules", json=RULE)
        second = authed_client.post("/api/v1/projects", json={"name": "Other"}).json()["id"]

        assert authed_client.get(f"/api/v1/projects/{second}/rules").json()["total"] == 0


class TestPredicates:
    def test_lists_every_predicate_with_a_schema(self, authed_client: TestClient) -> None:
        body = authed_client.get("/api/v1/rules/predicates").json()

        names = {item["predicate"] for item in body}
        assert {"not_null", "unique", "allowed_values", "range", "pattern", "length"} == names
        for item in body:
            assert item["label"] and item["summary"]
            assert item["parameters_schema"]["type"] == "object"

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.get("/api/v1/rules/predicates").status_code == 401

    def test_is_not_shadowed_by_the_rule_detail_route(self, authed_client: TestClient) -> None:
        """ "predicates" must not be read as a rule id."""
        assert authed_client.get("/api/v1/rules/predicates").status_code == 200


class TestRetrieveUpdateDelete:
    def _create(self, client: TestClient) -> dict[str, object]:
        pid = project_id(client)
        return dict(client.post(f"/api/v1/projects/{pid}/rules", json=RULE).json())

    def test_reads_back_a_rule(self, authed_client: TestClient) -> None:
        created = self._create(authed_client)
        response = authed_client.get(f"/api/v1/rules/{created['id']}")

        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_unknown_id_is_a_404(self, authed_client: TestClient) -> None:
        response = authed_client.get("/api/v1/rules/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_partial_update_leaves_other_fields_alone(self, authed_client: TestClient) -> None:
        created = self._create(authed_client)

        updated = authed_client.patch(
            f"/api/v1/rules/{created['id']}", json={"enabled": False}
        ).json()

        assert updated["enabled"] is False
        assert updated["parameters"] == RULE["parameters"]
        assert updated["severity"] == "high"

    def test_rejects_parameters_that_do_not_suit_the_stored_predicate(
        self, authed_client: TestClient
    ) -> None:
        """A partial change is validated against the predicate already stored."""
        created = self._create(authed_client)

        response = authed_client.patch(
            f"/api/v1/rules/{created['id']}", json={"parameters": {"min_length": 3}}
        )
        assert response.status_code == 422

    def test_deletes_a_rule(self, authed_client: TestClient) -> None:
        created = self._create(authed_client)

        assert authed_client.delete(f"/api/v1/rules/{created['id']}").status_code == 204
        assert authed_client.get(f"/api/v1/rules/{created['id']}").status_code == 404


class TestVersioning:
    def _create(self, client: TestClient) -> dict[str, object]:
        pid = project_id(client)
        return dict(client.post(f"/api/v1/projects/{pid}/rules", json=RULE).json())

    def test_a_meaning_change_bumps_the_version(self, authed_client: TestClient) -> None:
        created = self._create(authed_client)

        updated = authed_client.patch(
            f"/api/v1/rules/{created['id']}",
            json={"parameters": {"values": ["GBP", "USD"]}},
        ).json()

        assert updated["version"] == 2

    def test_changing_severity_bumps_the_version(self, authed_client: TestClient) -> None:
        created = self._create(authed_client)
        updated = authed_client.patch(
            f"/api/v1/rules/{created['id']}", json={"severity": "critical"}
        ).json()
        assert updated["version"] == 2

    def test_a_rename_does_not_bump_the_version(self, authed_client: TestClient) -> None:
        """The same assertion is being made, so findings stay comparable."""
        created = self._create(authed_client)

        updated = authed_client.patch(
            f"/api/v1/rules/{created['id']}", json={"name": "Renamed", "description": "New text."}
        ).json()

        assert updated["version"] == 1

    def test_disabling_does_not_bump_the_version(self, authed_client: TestClient) -> None:
        created = self._create(authed_client)
        updated = authed_client.patch(
            f"/api/v1/rules/{created['id']}", json={"enabled": False}
        ).json()
        assert updated["version"] == 1


class TestAuthorization:
    """Another user's rule must be indistinguishable from one that does not exist."""

    def _their_rule(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> tuple[str, dict[str, str]]:
        other = make_user(email="other@example.com")
        headers = auth_headers(other)
        pid = project_id(client, headers=headers)
        rule = client.post(f"/api/v1/projects/{pid}/rules", json=RULE, headers=headers).json()
        return str(rule["id"]), headers

    def test_cannot_read_another_users_rule(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        rule_id, _ = self._their_rule(client, make_user, auth_headers)

        response = client.get(f"/api/v1/rules/{rule_id}", headers=auth_headers(user))
        assert response.status_code == 404

    def test_cannot_update_another_users_rule(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        rule_id, _ = self._their_rule(client, make_user, auth_headers)

        response = client.patch(
            f"/api/v1/rules/{rule_id}", json={"enabled": False}, headers=auth_headers(user)
        )
        assert response.status_code == 404

    def test_cannot_delete_another_users_rule(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        rule_id, owner_headers = self._their_rule(client, make_user, auth_headers)

        assert (
            client.delete(f"/api/v1/rules/{rule_id}", headers=auth_headers(user)).status_code == 404
        )
        assert client.get(f"/api/v1/rules/{rule_id}", headers=owner_headers).status_code == 200


def test_deleting_a_project_cascades_to_its_rules(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    from app.models.rule import Rule

    owner = make_user(email="cascade-rules@example.com")
    headers = auth_headers(owner)
    pid = project_id(client, headers=headers)
    client.post(f"/api/v1/projects/{pid}/rules", json=RULE, headers=headers)
    assert db.query(Rule).count() == 1

    assert client.delete(f"/api/v1/projects/{pid}", headers=headers).status_code == 204
    assert db.query(Rule).count() == 0
