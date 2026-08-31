"""Project CRUD and the ownership boundary."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User

PROJECT = {"name": "Customer Transactions", "description": "Monthly card settlement exports."}


class TestCreate:
    def test_creates_a_project(self, authed_client: TestClient) -> None:
        response = authed_client.post("/api/v1/projects", json=PROJECT)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Customer Transactions"
        assert body["description"] == "Monthly card settlement exports."
        assert body["id"] and body["created_at"] and body["updated_at"]

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.post("/api/v1/projects", json=PROJECT).status_code == 401

    def test_collapses_whitespace_in_the_name(self, authed_client: TestClient) -> None:
        body = authed_client.post(
            "/api/v1/projects", json={"name": "  Customer   Transactions  "}
        ).json()
        assert body["name"] == "Customer Transactions"

    def test_blank_description_is_stored_as_null(self, authed_client: TestClient) -> None:
        body = authed_client.post("/api/v1/projects", json={"name": "Ledger", "description": "  "})
        assert body.json()["description"] is None

    def test_rejects_a_blank_name(self, authed_client: TestClient) -> None:
        assert authed_client.post("/api/v1/projects", json={"name": "   "}).status_code == 422

    def test_rejects_an_overlong_name(self, authed_client: TestClient) -> None:
        assert authed_client.post("/api/v1/projects", json={"name": "x" * 121}).status_code == 422


class TestList:
    def test_returns_an_empty_page_for_a_new_account(self, authed_client: TestClient) -> None:
        body = authed_client.get("/api/v1/projects").json()
        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_lists_most_recently_updated_first(self, authed_client: TestClient) -> None:
        for name in ("First", "Second", "Third"):
            authed_client.post("/api/v1/projects", json={"name": name})

        items = authed_client.get("/api/v1/projects").json()["items"]
        assert [item["name"] for item in items] == ["Third", "Second", "First"]

    def test_paginates(self, authed_client: TestClient) -> None:
        for index in range(5):
            authed_client.post("/api/v1/projects", json={"name": f"Project {index}"})

        page = authed_client.get("/api/v1/projects", params={"limit": 2, "offset": 2}).json()
        assert page["total"] == 5
        assert len(page["items"]) == 2
        assert page["limit"] == 2 and page["offset"] == 2

    def test_rejects_an_absurd_page_size(self, authed_client: TestClient) -> None:
        assert authed_client.get("/api/v1/projects", params={"limit": 5000}).status_code == 422

    def test_only_shows_your_own_projects(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        client.post("/api/v1/projects", json={"name": "Mine"}, headers=auth_headers(user))
        client.post("/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other))

        mine = client.get("/api/v1/projects", headers=auth_headers(user)).json()
        assert [item["name"] for item in mine["items"]] == ["Mine"]
        assert mine["total"] == 1


class TestRetrieveUpdateDelete:
    def test_reads_back_a_project(self, authed_client: TestClient) -> None:
        created = authed_client.post("/api/v1/projects", json=PROJECT).json()

        response = authed_client.get(f"/api/v1/projects/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_unknown_id_is_a_404(self, authed_client: TestClient) -> None:
        response = authed_client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_partial_update_leaves_other_fields_alone(self, authed_client: TestClient) -> None:
        created = authed_client.post("/api/v1/projects", json=PROJECT).json()

        updated = authed_client.patch(
            f"/api/v1/projects/{created['id']}", json={"name": "Renamed"}
        ).json()

        assert updated["name"] == "Renamed"
        assert updated["description"] == PROJECT["description"]

    def test_description_can_be_cleared(self, authed_client: TestClient) -> None:
        created = authed_client.post("/api/v1/projects", json=PROJECT).json()
        updated = authed_client.patch(
            f"/api/v1/projects/{created['id']}", json={"description": None}
        ).json()
        assert updated["description"] is None

    def test_delete_removes_the_project(self, authed_client: TestClient) -> None:
        created = authed_client.post("/api/v1/projects", json=PROJECT).json()

        assert authed_client.delete(f"/api/v1/projects/{created['id']}").status_code == 204
        assert authed_client.get(f"/api/v1/projects/{created['id']}").status_code == 404


class TestAuthorization:
    """Another user's project must be indistinguishable from one that does not exist."""

    def test_cannot_read_another_users_project(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        theirs = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other)
        ).json()

        response = client.get(f"/api/v1/projects/{theirs['id']}", headers=auth_headers(user))
        assert response.status_code == 404

    def test_cannot_update_another_users_project(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        theirs = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other)
        ).json()

        response = client.patch(
            f"/api/v1/projects/{theirs['id']}",
            json={"name": "Hijacked"},
            headers=auth_headers(user),
        )
        assert response.status_code == 404

    def test_cannot_delete_another_users_project(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        theirs = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other)
        ).json()

        assert (
            client.delete(
                f"/api/v1/projects/{theirs['id']}", headers=auth_headers(user)
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/v1/projects/{theirs['id']}", headers=auth_headers(other)).status_code
            == 200
        )


def test_deleting_a_user_cascades_to_their_projects(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    from app.models.project import Project

    owner = make_user(email="cascade@example.com")
    client.post("/api/v1/projects", json={"name": "Doomed"}, headers=auth_headers(owner))
    assert db.query(Project).count() == 1

    db.delete(owner)
    db.commit()

    assert db.query(Project).count() == 0
