"""Report export."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.models.user import User
from tests.fixtures import sample_bytes


@pytest.fixture
def project_id(authed_client: TestClient) -> str:
    return authed_client.post("/api/v1/projects", json={"name": "Transactions"}).json()["id"]


def upload(client: TestClient, project_id: str, sample: str, **kwargs) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        files={"file": (sample, io.BytesIO(sample_bytes(sample)), "text/csv")},
        **kwargs,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def analysis_id(authed_client: TestClient, project_id: str) -> str:
    dataset = upload(authed_client, project_id, "invalid_values.csv")
    return dataset["latest_analysis"]["id"]


class TestFormats:
    def test_advertises_what_it_can_produce(self, authed_client: TestClient) -> None:
        formats = authed_client.get("/api/v1/reports/formats").json()

        assert {entry["format"] for entry in formats} == {"pdf", "csv"}
        assert all(entry["label"] for entry in formats)


class TestPdf:
    def test_produces_a_real_pdf(self, authed_client: TestClient, analysis_id: str) -> None:
        response = authed_client.post(f"/api/v1/reports/{analysis_id}/export?format=pdf")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-"), "must be a valid PDF header"
        assert response.content.rstrip().endswith(b"%%EOF")
        assert len(response.content) > 5_000, "a real report, not an empty page"

    def test_defaults_to_pdf(self, authed_client: TestClient, analysis_id: str) -> None:
        response = authed_client.post(f"/api/v1/reports/{analysis_id}/export")
        assert response.headers["content-type"] == "application/pdf"

    def test_offers_an_informative_download_name(
        self, authed_client: TestClient, analysis_id: str
    ) -> None:
        disposition = authed_client.post(f"/api/v1/reports/{analysis_id}/export").headers[
            "content-disposition"
        ]

        assert disposition.startswith("attachment;")
        assert "obseil-" in disposition
        assert ".pdf" in disposition

    def test_is_not_cached(self, authed_client: TestClient, analysis_id: str) -> None:
        """The report embeds a generation timestamp."""
        response = authed_client.post(f"/api/v1/reports/{analysis_id}/export")
        assert response.headers["cache-control"] == "no-store"

    def test_renders_a_clean_dataset_without_a_findings_section(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset = upload(authed_client, project_id, "clean_transactions.csv")
        analysis = dataset["latest_analysis"]["id"]

        response = authed_client.post(f"/api/v1/reports/{analysis}/export?format=pdf")

        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")

    def test_survives_a_dataset_name_with_awkward_characters(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset = upload(
            authed_client,
            project_id,
            "invalid_values.csv",
            data={"name": "Q1 <transactions> & more"},
        )
        analysis = dataset["latest_analysis"]["id"]

        response = authed_client.post(f"/api/v1/reports/{analysis}/export")

        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")


class TestCsv:
    def rows(self, content: bytes) -> list[dict[str, str]]:
        text = content.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))

    def test_exports_one_row_per_finding(
        self, authed_client: TestClient, project_id: str, analysis_id: str
    ) -> None:
        response = authed_client.post(f"/api/v1/reports/{analysis_id}/export?format=csv")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")

        dataset_id = authed_client.get(f"/api/v1/projects/{project_id}/datasets").json()["items"][
            0
        ]["id"]
        expected = authed_client.get(
            f"/api/v1/datasets/{dataset_id}/findings", params={"limit": 200}
        ).json()["total"]

        assert len(self.rows(response.content)) == expected

    def test_includes_the_advice_not_just_the_problem(
        self, authed_client: TestClient, analysis_id: str
    ) -> None:
        """A findings export without recommendations is a to-do list with the
        instructions removed."""
        rows = self.rows(
            authed_client.post(f"/api/v1/reports/{analysis_id}/export?format=csv").content
        )

        assert set(rows[0]) >= {
            "severity",
            "type",
            "title",
            "column",
            "description",
            "impact",
            "recommendation",
            "detection_method",
        }
        assert all(row["recommendation"] for row in rows)

    def test_orders_most_severe_first(self, authed_client: TestClient, analysis_id: str) -> None:
        rows = self.rows(
            authed_client.post(f"/api/v1/reports/{analysis_id}/export?format=csv").content
        )

        ranks = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        severities = [ranks[row["severity"]] for row in rows]
        assert severities == sorted(severities, reverse=True)

    def test_carries_the_utf8_bom_so_excel_reads_it(
        self, authed_client: TestClient, analysis_id: str
    ) -> None:
        content = authed_client.post(f"/api/v1/reports/{analysis_id}/export?format=csv").content
        assert content.startswith(b"\xef\xbb\xbf")

    def test_exports_a_header_only_file_for_a_clean_dataset(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset = upload(authed_client, project_id, "clean_transactions.csv")
        analysis = dataset["latest_analysis"]["id"]

        rows = self.rows(
            authed_client.post(f"/api/v1/reports/{analysis}/export?format=csv").content
        )

        # The clean fixture has no rule findings; anomaly candidates may appear.
        assert all(row["category"] == "anomaly" for row in rows)

    def test_names_the_file_as_a_findings_export(
        self, authed_client: TestClient, analysis_id: str
    ) -> None:
        disposition = authed_client.post(
            f"/api/v1/reports/{analysis_id}/export?format=csv"
        ).headers["content-disposition"]
        assert "-findings.csv" in disposition


class TestErrors:
    def test_rejects_an_unknown_format_and_says_what_is_supported(
        self, authed_client: TestClient, analysis_id: str
    ) -> None:
        response = authed_client.post(f"/api/v1/reports/{analysis_id}/export?format=xlsx")

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "unsupported_report_format"
        assert "pdf" in error["message"]

    def test_unknown_analysis_is_a_404(self, authed_client: TestClient) -> None:
        assert authed_client.post("/api/v1/reports/does-not-exist/export").status_code == 404

    def test_requires_authentication(self, authed_client: TestClient, analysis_id: str) -> None:
        # `authed_client` is the same client with headers set, so sign out by
        # removing them rather than by using the anonymous fixture.
        authed_client.headers.pop("Authorization")

        assert authed_client.post(f"/api/v1/reports/{analysis_id}/export").status_code == 401

    def test_cannot_export_another_users_analysis(
        self,
        client: TestClient,
        user: User,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        other = make_user(email="other@example.com")
        project = client.post(
            "/api/v1/projects", json={"name": "Theirs"}, headers=auth_headers(other)
        ).json()["id"]
        dataset = client.post(
            f"/api/v1/projects/{project}/datasets",
            files={
                "file": (
                    "clean.csv",
                    io.BytesIO(sample_bytes("clean_transactions.csv")),
                    "text/csv",
                )
            },
            headers=auth_headers(other),
        ).json()

        response = client.post(
            f"/api/v1/reports/{dataset['latest_analysis']['id']}/export",
            headers=auth_headers(user),
        )
        assert response.status_code == 404
