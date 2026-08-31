"""Findings listing, filtering, triage and feedback."""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.models.user import User
from tests.fixtures import sample_bytes


@pytest.fixture
def project_id(authed_client: TestClient) -> str:
    return authed_client.post("/api/v1/projects", json={"name": "Transactions"}).json()["id"]


def upload_sample(client: TestClient, project_id: str, sample: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        files={"file": (sample, io.BytesIO(sample_bytes(sample)), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def messy_dataset(authed_client: TestClient, project_id: str) -> str:
    return upload_sample(authed_client, project_id, "invalid_values.csv")


class TestListing:
    def test_returns_the_findings_from_the_latest_analysis(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        body = authed_client.get(f"/api/v1/datasets/{messy_dataset}/findings").json()

        assert body["total"] > 0
        finding = body["items"][0]
        assert finding["title"] and finding["description"]
        assert finding["impact"] and finding["recommendation"]
        assert finding["detection_method_label"], "the UI must never render a raw enum"
        assert finding["status"] == "open"

    def test_orders_most_severe_first(self, authed_client: TestClient, messy_dataset: str) -> None:
        items = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings", params={"limit": 100}
        ).json()["items"]

        ranks = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        severities = [ranks[item["severity"]] for item in items]
        assert severities == sorted(severities, reverse=True)

    def test_a_clean_dataset_has_no_rule_findings(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        """No *deterministic* finding fires on the clean fixture.

        The unsupervised model may still surface a handful of candidates —
        that is an expected outcome of anomaly detection on any real dataset,
        and it is reported as a separate category rather than as a defect.
        """
        dataset_id = upload_sample(authed_client, project_id, "clean_transactions.csv")

        body = authed_client.get(
            f"/api/v1/datasets/{dataset_id}/findings",
            params={"category": "rule", "limit": 100},
        ).json()

        assert body["total"] == 0
        assert body["items"] == []

    def test_asks_for_an_analysis_when_there_is_none(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("data.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
            data={"analyze": "false"},
        ).json()["id"]

        response = authed_client.get(f"/api/v1/datasets/{dataset_id}/findings")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_missing"


class TestFilters:
    def test_filters_by_severity(self, authed_client: TestClient, messy_dataset: str) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings", params={"severity": "medium"}
        ).json()

        assert body["total"] > 0
        assert {item["severity"] for item in body["items"]} == {"medium"}

    def test_accepts_several_severities(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings",
            params=[("severity", "low"), ("severity", "medium")],
        ).json()

        assert {item["severity"] for item in body["items"]} <= {"low", "medium"}

    def test_filters_by_type(self, authed_client: TestClient, messy_dataset: str) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings", params={"type": "negative_values"}
        ).json()

        assert body["total"] == 2
        assert {item["column_name"] for item in body["items"]} == {"amount", "items"}

    def test_searches_titles_descriptions_and_columns(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings", params={"search": "batch_version"}
        ).json()

        assert body["total"] >= 1
        assert all("batch_version" in (item["column_name"] or "") for item in body["items"])

    def test_search_matches_nothing_gracefully(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings", params={"search": "zzz-nothing"}
        ).json()

        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_paginates(self, authed_client: TestClient, messy_dataset: str) -> None:
        page = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings", params={"limit": 2, "offset": 1}
        ).json()

        assert len(page["items"]) <= 2
        assert page["offset"] == 1


class TestSummary:
    def test_reports_counts_by_severity_and_type(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        body = authed_client.get(f"/api/v1/datasets/{messy_dataset}/findings/summary").json()

        assert body["total"] > 0
        assert set(body["by_severity"]) == {"low", "medium", "high", "critical"}
        assert sum(body["by_severity"].values()) == body["total"]
        assert "negative_values" in body["by_type"]
        assert body["open_count"] == body["total"]


class TestTriage:
    def first_finding(self, client: TestClient, dataset_id: str) -> dict:
        return client.get(f"/api/v1/datasets/{dataset_id}/findings").json()["items"][0]

    def test_marks_a_finding_reviewed(self, authed_client: TestClient, messy_dataset: str) -> None:
        finding = self.first_finding(authed_client, messy_dataset)

        response = authed_client.patch(
            f"/api/v1/findings/{finding['id']}", json={"status": "reviewed"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "reviewed"

    def test_records_a_valid_issue_verdict(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        finding = self.first_finding(authed_client, messy_dataset)

        body = authed_client.patch(
            f"/api/v1/findings/{finding['id']}",
            json={"verdict": "valid_issue", "note": "Confirmed with the upstream team."},
        ).json()

        assert body["feedback"]["verdict"] == "valid_issue"
        assert body["feedback"]["note"] == "Confirmed with the upstream team."
        # A confirmed issue is reviewed, not ignored.
        assert body["status"] == "reviewed"

    def test_a_false_positive_is_also_ignored(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        """Saying the detector was wrong and then leaving the finding in the
        queue would be a pointless second step."""
        finding = self.first_finding(authed_client, messy_dataset)

        body = authed_client.patch(
            f"/api/v1/findings/{finding['id']}", json={"verdict": "false_positive"}
        ).json()

        assert body["feedback"]["verdict"] == "false_positive"
        assert body["status"] == "ignored"

    def test_an_explicit_status_overrides_the_implied_one(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        finding = self.first_finding(authed_client, messy_dataset)

        body = authed_client.patch(
            f"/api/v1/findings/{finding['id']}",
            json={"verdict": "false_positive", "status": "reviewed"},
        ).json()

        assert body["status"] == "reviewed"

    def test_a_verdict_can_be_changed(self, authed_client: TestClient, messy_dataset: str) -> None:
        finding = self.first_finding(authed_client, messy_dataset)

        authed_client.patch(f"/api/v1/findings/{finding['id']}", json={"verdict": "false_positive"})
        body = authed_client.patch(
            f"/api/v1/findings/{finding['id']}", json={"verdict": "valid_issue"}
        ).json()

        assert body["feedback"]["verdict"] == "valid_issue"

    def test_rejects_an_empty_update(self, authed_client: TestClient, messy_dataset: str) -> None:
        finding = self.first_finding(authed_client, messy_dataset)

        response = authed_client.patch(f"/api/v1/findings/{finding['id']}", json={})

        assert response.status_code == 422

    def test_rejects_an_unknown_status(self, authed_client: TestClient, messy_dataset: str) -> None:
        finding = self.first_finding(authed_client, messy_dataset)
        response = authed_client.patch(
            f"/api/v1/findings/{finding['id']}", json={"status": "wontfix"}
        )
        assert response.status_code == 422

    def test_triage_is_reflected_in_the_summary(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        finding = self.first_finding(authed_client, messy_dataset)
        authed_client.patch(f"/api/v1/findings/{finding['id']}", json={"verdict": "false_positive"})

        summary = authed_client.get(f"/api/v1/datasets/{messy_dataset}/findings/summary").json()

        assert summary["false_positive_count"] == 1
        assert summary["ignored_count"] == 1
        assert summary["open_count"] == summary["total"] - 1

    def test_filters_by_status_after_triage(
        self, authed_client: TestClient, messy_dataset: str
    ) -> None:
        finding = self.first_finding(authed_client, messy_dataset)
        authed_client.patch(f"/api/v1/findings/{finding['id']}", json={"status": "ignored"})

        body = authed_client.get(
            f"/api/v1/datasets/{messy_dataset}/findings", params={"status": "ignored"}
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["id"] == finding["id"]


class TestAuthorization:
    def test_cannot_read_another_users_findings(
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
        dataset_id = client.post(
            f"/api/v1/projects/{project}/datasets",
            files={
                "file": (
                    "invalid_values.csv",
                    io.BytesIO(sample_bytes("invalid_values.csv")),
                    "text/csv",
                )
            },
            headers=auth_headers(other),
        ).json()["id"]

        assert (
            client.get(
                f"/api/v1/datasets/{dataset_id}/findings", headers=auth_headers(user)
            ).status_code
            == 404
        )

    def test_cannot_triage_another_users_finding(
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
        dataset_id = client.post(
            f"/api/v1/projects/{project}/datasets",
            files={
                "file": (
                    "invalid_values.csv",
                    io.BytesIO(sample_bytes("invalid_values.csv")),
                    "text/csv",
                )
            },
            headers=auth_headers(other),
        ).json()["id"]
        finding_id = client.get(
            f"/api/v1/datasets/{dataset_id}/findings", headers=auth_headers(other)
        ).json()["items"][0]["id"]

        response = client.patch(
            f"/api/v1/findings/{finding_id}",
            json={"status": "ignored"},
            headers=auth_headers(user),
        )
        assert response.status_code == 404


def test_reanalysing_replaces_the_previous_findings(
    authed_client: TestClient, messy_dataset: str, db
) -> None:
    """Findings belong to the run that produced them; carrying them forward
    would make the history claim a run saw something it did not."""
    from app.models.finding import Finding

    first = authed_client.get(f"/api/v1/datasets/{messy_dataset}/findings").json()
    authed_client.post(f"/api/v1/datasets/{messy_dataset}/analyze")
    second = authed_client.get(f"/api/v1/datasets/{messy_dataset}/findings").json()

    assert second["total"] == first["total"]
    assert {item["id"] for item in second["items"]} != {item["id"] for item in first["items"]}
    # Both runs' findings are retained, each attached to its own analysis.
    assert db.query(Finding).count() == first["total"] * 2


def test_deleting_a_dataset_removes_its_findings(
    authed_client: TestClient, messy_dataset: str, db
) -> None:
    from app.models.finding import Finding

    assert db.query(Finding).count() > 0
    authed_client.delete(f"/api/v1/datasets/{messy_dataset}")
    assert db.query(Finding).count() == 0
