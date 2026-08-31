"""Anomaly and quality-score endpoints."""

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


def upload_sample(client: TestClient, project_id: str, sample: str, **headers: object) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        files={"file": (sample, io.BytesIO(sample_bytes(sample)), "text/csv")},
        **headers,  # type: ignore[arg-type]
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def anomalous_dataset(authed_client: TestClient, project_id: str) -> str:
    return upload_sample(authed_client, project_id, "anomalous_transactions.csv")


class TestAnomalies:
    def test_lists_anomalous_rows_most_unusual_first(
        self, authed_client: TestClient, anomalous_dataset: str
    ) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{anomalous_dataset}/anomalies", params={"limit": 50}
        ).json()

        assert body["total"] > 0
        ranks = [item["rank"] for item in body["items"]]
        assert ranks == sorted(ranks)
        scores = [item["anomaly_score"] for item in body["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_each_anomaly_shows_the_values_the_model_saw(
        self, authed_client: TestClient, anomalous_dataset: str
    ) -> None:
        item = authed_client.get(f"/api/v1/datasets/{anomalous_dataset}/anomalies").json()["items"][
            0
        ]

        assert item["feature_values"]
        assert item["top_contributors"]
        contributor = item["top_contributors"][0]
        assert set(contributor) == {"feature", "value", "deviation_iqr"}
        assert 0 <= item["anomaly_score"] <= 100

    def test_the_overview_explains_the_method_and_its_limits(
        self, authed_client: TestClient, anomalous_dataset: str
    ) -> None:
        body = authed_client.get(f"/api/v1/datasets/{anomalous_dataset}/anomalies/overview").json()

        assert body["ran"] is True
        assert body["algorithm"] == "isolation_forest"
        assert len(body["features"]) >= 2
        assert body["anomaly_count"] > 0
        assert "not a probability" in body["method_note"]
        assert "does not know why" in body["method_note"]

    def test_the_overview_reports_a_deliberate_skip_as_such(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        """One numeric column cannot support multivariate detection; saying so
        is more useful than a confident-looking empty result."""
        csv = b"label,amount\n" + b"".join(f"row{index},{index}\n".encode() for index in range(120))
        dataset_id = authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("thin.csv", io.BytesIO(csv), "text/csv")},
        ).json()["id"]

        body = authed_client.get(f"/api/v1/datasets/{dataset_id}/anomalies/overview").json()

        assert body["ran"] is False
        assert body["skipped_reason"]
        assert body["anomaly_count"] == 0

    def test_the_ml_finding_appears_in_the_anomaly_category(
        self, authed_client: TestClient, anomalous_dataset: str
    ) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{anomalous_dataset}/findings", params={"category": "anomaly"}
        ).json()

        assert body["total"] == 1
        finding = body["items"][0]
        assert finding["type"] == "ml_anomaly"
        assert finding["detection_method_label"].startswith("Isolation Forest")

    def test_no_rule_finding_fires_on_the_anomaly_fixture(
        self, authed_client: TestClient, anomalous_dataset: str
    ) -> None:
        body = authed_client.get(
            f"/api/v1/datasets/{anomalous_dataset}/findings", params={"category": "rule"}
        ).json()
        assert body["total"] == 0


class TestQualityScore:
    def test_returns_the_score_with_its_full_derivation(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload_sample(authed_client, project_id, "invalid_values.csv")

        body = authed_client.get(f"/api/v1/datasets/{dataset_id}/score").json()

        assert 0 <= body["score"] <= 100
        assert body["grade_label"]
        assert body["summary"]
        assert len(body["dimensions"]) == 6
        assert body["top_contributors"]

    def test_the_derivation_reconciles_with_the_headline(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload_sample(authed_client, project_id, "missing_values.csv")

        body = authed_client.get(f"/api/v1/datasets/{dataset_id}/score").json()

        total = sum(dimension["penalty"] for dimension in body["dimensions"])
        assert body["total_penalty"] == pytest.approx(total, abs=0.05)
        assert body["score"] == pytest.approx(100 - total, abs=0.05)

    def test_a_clean_dataset_scores_excellent(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload_sample(authed_client, project_id, "clean_transactions.csv")

        body = authed_client.get(f"/api/v1/datasets/{dataset_id}/score").json()

        assert body["score"] >= 95
        assert body["grade"] == "excellent"

    def test_the_score_appears_on_the_dataset_payload(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset_id = upload_sample(authed_client, project_id, "invalid_values.csv")

        analysis = authed_client.get(f"/api/v1/datasets/{dataset_id}").json()["latest_analysis"]

        assert analysis["quality_score"] is not None
        assert analysis["quality_grade"]
        assert analysis["finding_count"] > 0
        assert analysis["anomaly_count"] >= 0

    def test_the_project_list_reports_the_latest_score(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        upload_sample(authed_client, project_id, "invalid_values.csv")

        project = authed_client.get("/api/v1/projects").json()["items"][0]

        assert project["latest_quality_score"] is not None
        assert project["last_analysed_at"] is not None


class TestAuthorization:
    def test_cannot_read_another_users_anomalies_or_score(
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
        dataset_id = upload_sample(
            client, project, "anomalous_transactions.csv", headers=auth_headers(other)
        )

        for path in ("/anomalies", "/anomalies/overview", "/score"):
            response = client.get(
                f"/api/v1/datasets/{dataset_id}{path}", headers=auth_headers(user)
            )
            assert response.status_code == 404, path


def test_deleting_a_dataset_removes_its_anomalies(
    authed_client: TestClient, anomalous_dataset: str, db
) -> None:
    from app.models.anomaly import Anomaly

    assert db.query(Anomaly).count() > 0
    authed_client.delete(f"/api/v1/datasets/{anomalous_dataset}")
    assert db.query(Anomaly).count() == 0
