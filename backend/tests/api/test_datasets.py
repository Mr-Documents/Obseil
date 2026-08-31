"""Dataset upload, analysis, statistics, preview and the ownership boundary."""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.user import User
from tests.fixtures import sample_bytes

CSV = b"id,amount,category\n1,10.5,a\n2,20.0,b\n3,30.25,a\n"


@pytest.fixture
def project_id(authed_client: TestClient) -> str:
    return authed_client.post("/api/v1/projects", json={"name": "Transactions"}).json()["id"]


def upload(
    client: TestClient,
    project_id: str,
    *,
    content: bytes = CSV,
    filename: str = "data.csv",
    **data: object,
):
    return client.post(
        f"/api/v1/projects/{project_id}/datasets",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
        data={key: str(value) for key, value in data.items()},
    )


class TestUpload:
    def test_stores_and_analyses_a_csv(self, authed_client: TestClient, project_id: str) -> None:
        response = upload(authed_client, project_id)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "data.csv"
        assert body["file_format"] == "csv"
        assert body["status"] == "ready"
        assert body["row_count"] == 3
        assert body["column_count"] == 3
        assert body["latest_analysis"]["status"] == "completed"
        assert body["checksum_sha256"]

    def test_accepts_an_explicit_display_name(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        body = upload(authed_client, project_id, name="March export").json()
        assert body["name"] == "March export"

    def test_can_defer_the_analysis(self, authed_client: TestClient, project_id: str) -> None:
        body = upload(authed_client, project_id, analyze=False).json()

        assert body["status"] == "uploaded"
        assert body["latest_analysis"] is None

    def test_uploads_an_xlsx_workbook(self, authed_client: TestClient, project_id: str) -> None:
        response = upload(
            authed_client,
            project_id,
            content=sample_bytes("clean_transactions.xlsx"),
            filename="clean_transactions.xlsx",
        )

        assert response.status_code == 201
        body = response.json()
        assert body["file_format"] == "xlsx"
        assert body["row_count"] == 600

    def test_strips_a_path_from_the_filename(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        body = upload(authed_client, project_id, filename="../../etc/passwd.csv").json()

        assert body["name"] == "passwd.csv"
        assert ".." not in body["original_filename"]

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/projects/whatever/datasets",
            files={"file": ("data.csv", io.BytesIO(CSV), "text/csv")},
        )
        assert response.status_code == 401


class TestUploadValidation:
    def test_rejects_an_unsupported_extension(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        response = upload(authed_client, project_id, content=b"%PDF-1.4", filename="report.pdf")

        assert response.status_code == 415
        error = response.json()["error"]
        assert error["code"] == "unsupported_media_type"
        assert ".csv" in error["message"], "the error must list what is accepted"

    def test_rejects_an_empty_file(self, authed_client: TestClient, project_id: str) -> None:
        response = upload(authed_client, project_id, content=b"")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "dataset_empty"

    def test_rejects_a_csv_that_is_really_a_workbook(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        response = upload(authed_client, project_id, content=b"PK\x03\x04junk")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "format_mismatch"

    def test_rejects_a_workbook_that_is_really_a_csv(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        response = upload(authed_client, project_id, content=CSV, filename="data.xlsx")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "format_mismatch"

    def test_rejects_a_file_over_the_size_limit(
        self, authed_client: TestClient, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "max_upload_bytes", 128)

        response = upload(authed_client, project_id, content=b"id,value\n" + b"1,2\n" * 200)

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"

    def test_rejects_a_header_with_no_rows(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        response = upload(authed_client, project_id, content=b"id,amount,category\n")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "dataset_empty"

    def test_a_failed_analysis_is_recorded_rather_than_lost(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        """The upload succeeded; the analysis did not. The dataset must still
        exist with a readable reason, not vanish."""
        upload(authed_client, project_id, content=b"id,amount\n")

        datasets = authed_client.get(f"/api/v1/projects/{project_id}/datasets").json()
        assert datasets["total"] == 1
        assert datasets["items"][0]["status"] == "failed"
        assert datasets["items"][0]["error_message"]


class TestListingAndRetrieval:
    def test_lists_datasets_newest_first(self, authed_client: TestClient, project_id: str) -> None:
        for index in range(3):
            upload(authed_client, project_id, filename=f"file{index}.csv")

        items = authed_client.get(f"/api/v1/projects/{project_id}/datasets").json()["items"]

        assert [item["name"] for item in items] == ["file2.csv", "file1.csv", "file0.csv"]

    def test_gets_a_dataset_with_its_latest_analysis(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(authed_client, project_id).json()["id"]

        body = authed_client.get(f"/api/v1/datasets/{dataset_id}").json()

        assert body["id"] == dataset_id
        assert body["latest_analysis"]["row_count"] == 3

    def test_unknown_dataset_is_a_404(self, authed_client: TestClient) -> None:
        assert authed_client.get("/api/v1/datasets/does-not-exist").status_code == 404

    def test_projects_report_their_dataset_count(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        upload(authed_client, project_id)
        upload(authed_client, project_id, filename="second.csv")

        projects = authed_client.get("/api/v1/projects").json()["items"]

        assert projects[0]["dataset_count"] == 2
        assert projects[0]["analysis_count"] == 2


class TestStatistics:
    def test_returns_dataset_and_column_statistics(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(
            authed_client, project_id, content=sample_bytes("clean_transactions.csv")
        ).json()["id"]

        body = authed_client.get(f"/api/v1/datasets/{dataset_id}/statistics").json()

        assert body["row_count"] == 600
        assert body["column_count"] == 10
        assert body["missing_cells"] == 0
        assert len(body["columns"]) == 10

        amount = next(column for column in body["columns"] if column["name"] == "amount")
        assert amount["inferred_type"] in {"numeric", "integer"}
        assert amount["numeric"]["mean"] is not None

    def test_categorical_columns_carry_no_numeric_statistics(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(
            authed_client, project_id, content=sample_bytes("clean_transactions.csv")
        ).json()["id"]

        body = authed_client.get(f"/api/v1/datasets/{dataset_id}/statistics").json()
        channel = next(column for column in body["columns"] if column["name"] == "channel")

        assert channel["numeric"] is None

    def test_asks_for_an_analysis_when_there_is_none(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(authed_client, project_id, analyze=False).json()["id"]

        response = authed_client.get(f"/api/v1/datasets/{dataset_id}/statistics")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_missing"


class TestReanalysis:
    def test_creates_a_new_analysis_each_time(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(authed_client, project_id).json()["id"]
        first = authed_client.get(f"/api/v1/datasets/{dataset_id}").json()["latest_analysis"]["id"]

        response = authed_client.post(f"/api/v1/datasets/{dataset_id}/analyze")

        assert response.status_code == 201
        assert response.json()["id"] != first
        assert response.json()["profile"]["row_count"] == 3


class TestPreview:
    def test_returns_a_bounded_window_of_rows(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(
            authed_client, project_id, content=sample_bytes("clean_transactions.csv")
        ).json()["id"]

        body = authed_client.get(
            f"/api/v1/datasets/{dataset_id}/preview", params={"offset": 10, "limit": 5}
        ).json()

        assert body["total_rows"] == 600
        assert len(body["rows"]) == 5
        assert body["rows"][0]["index"] == 10
        assert body["columns"][0] == "transaction_id"

    def test_caps_the_page_size_server_side(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(authed_client, project_id).json()["id"]

        response = authed_client.get(
            f"/api/v1/datasets/{dataset_id}/preview", params={"limit": 100_000}
        )
        assert response.status_code == 422

    def test_renders_missing_values_as_null(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload(authed_client, project_id, content=b"id,value\n1,\n2,7\n").json()["id"]

        rows = authed_client.get(f"/api/v1/datasets/{dataset_id}/preview").json()["rows"]

        assert rows[0]["values"]["value"] is None
        assert rows[1]["values"]["value"] == "7"


class TestAuthorization:
    def test_cannot_upload_into_another_users_project(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        theirs = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other)
        ).json()["id"]

        response = client.post(
            f"/api/v1/projects/{theirs}/datasets",
            files={"file": ("data.csv", io.BytesIO(CSV), "text/csv")},
            headers=auth_headers(user),
        )
        assert response.status_code == 404

    def test_cannot_read_another_users_dataset(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        theirs = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other)
        ).json()["id"]
        dataset_id = client.post(
            f"/api/v1/projects/{theirs}/datasets",
            files={"file": ("data.csv", io.BytesIO(CSV), "text/csv")},
            headers=auth_headers(other),
        ).json()["id"]

        for path in ("", "/statistics", "/preview"):
            assert (
                client.get(f"/api/v1/datasets/{dataset_id}{path}", headers=auth_headers(user))
            ).status_code == 404

    def test_cannot_delete_another_users_dataset(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        theirs = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other)
        ).json()["id"]
        dataset_id = client.post(
            f"/api/v1/projects/{theirs}/datasets",
            files={"file": ("data.csv", io.BytesIO(CSV), "text/csv")},
            headers=auth_headers(other),
        ).json()["id"]

        assert (
            client.delete(f"/api/v1/datasets/{dataset_id}", headers=auth_headers(user)).status_code
            == 404
        )


class TestDeletion:
    def test_removes_the_dataset_and_its_stored_file(
        self, authed_client: TestClient, project_id: str, db
    ) -> None:
        from app.models.dataset import Dataset
        from app.storage import get_storage

        dataset_id = upload(authed_client, project_id).json()["id"]
        storage_key = db.get(Dataset, dataset_id).storage_key
        assert get_storage().exists(storage_key)

        assert authed_client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
        assert authed_client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
        assert not get_storage().exists(storage_key)

    def test_deleting_a_project_removes_its_datasets(
        self, authed_client: TestClient, project_id: str, db
    ) -> None:
        from app.models.dataset import Dataset, DatasetAnalysis

        upload(authed_client, project_id)
        assert db.query(Dataset).count() == 1

        authed_client.delete(f"/api/v1/projects/{project_id}")

        assert db.query(Dataset).count() == 0
        assert db.query(DatasetAnalysis).count() == 0
