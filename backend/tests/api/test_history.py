"""Analysis history, trend and comparison."""

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


def upload(client: TestClient, project_id: str, sample: str, **kwargs) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        files={"file": (sample, io.BytesIO(sample_bytes(sample)), "text/csv")},
        **kwargs,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def two_analyses(authed_client: TestClient, project_id: str) -> tuple[dict, dict]:
    """A worse dataset followed by a better one, in that order."""
    worse = upload(authed_client, project_id, "invalid_values.csv")
    better = upload(authed_client, project_id, "clean_transactions.csv")
    return worse, better


class TestProjectHistory:
    def test_lists_completed_analyses_newest_first(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        body = authed_client.get(f"/api/v1/projects/{project_id}/history").json()

        assert body["total"] == 2
        names = [item["dataset_name"] for item in body["items"]]
        assert names == ["clean_transactions.csv", "invalid_values.csv"]

    def test_numbers_each_run_within_the_project(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        items = authed_client.get(f"/api/v1/projects/{project_id}/history").json()["items"]

        # Newest first, so the newest carries the highest version.
        assert [item["version"] for item in items] == [2, 1]

    def test_carries_the_score_and_finding_counts(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        newest = authed_client.get(f"/api/v1/projects/{project_id}/history").json()["items"][0]

        assert newest["quality_score"] is not None
        assert newest["quality_grade"]
        assert "finding_count" in newest and "anomaly_count" in newest

    def test_is_empty_for_a_project_with_no_analyses(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        body = authed_client.get(f"/api/v1/projects/{project_id}/history").json()
        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}


class TestDatasetHistory:
    def test_lists_every_run_for_one_dataset(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        dataset = upload(authed_client, project_id, "clean_transactions.csv")
        authed_client.post(f"/api/v1/datasets/{dataset['id']}/analyze")

        body = authed_client.get(f"/api/v1/datasets/{dataset['id']}/history").json()

        assert body["total"] == 2

    def test_includes_failed_runs(self, authed_client: TestClient, project_id: str) -> None:
        """A history that silently omits failures would misrepresent what happened."""
        dataset = authed_client.post(
            f"/api/v1/projects/{project_id}/datasets",
            files={"file": ("broken.csv", io.BytesIO(b"id,amount\n"), "text/csv")},
        )
        assert dataset.status_code == 422

        datasets = authed_client.get(f"/api/v1/projects/{project_id}/datasets").json()["items"]
        body = authed_client.get(f"/api/v1/datasets/{datasets[0]['id']}/history").json()

        assert body["total"] == 1
        assert body["items"][0]["status"] == "failed"


class TestTrend:
    def test_returns_a_compact_series_oldest_first(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        series = authed_client.get(f"/api/v1/projects/{project_id}/history/trend").json()

        assert len(series) == 2
        assert set(series[0]) == {"analysis_id", "score", "at", "finding_count", "dataset_name"}
        assert series[0]["dataset_name"] == "invalid_values.csv"
        assert series[1]["dataset_name"] == "clean_transactions.csv"


class TestComparison:
    def analysis_ids(self, client: TestClient, project_id: str) -> list[str]:
        items = client.get(f"/api/v1/projects/{project_id}/history").json()["items"]
        return [item["id"] for item in items]

    def test_compares_against_the_previous_run_by_default(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        newest, oldest = self.analysis_ids(authed_client, project_id)

        body = authed_client.get(f"/api/v1/analyses/{newest}/compare").json()

        assert body["baseline_id"] == oldest
        assert body["current_id"] == newest

    def test_reports_an_improvement_in_plain_language(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        newest, _ = self.analysis_ids(authed_client, project_id)

        body = authed_client.get(f"/api/v1/analyses/{newest}/compare").json()

        assert body["score_delta"] > 0
        assert "improved" in body["headline"].lower()

    def test_the_older_run_is_always_the_baseline(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        """Argument order must never flip the sign of the answer."""
        newest, oldest = self.analysis_ids(authed_client, project_id)

        forward = authed_client.get(
            f"/api/v1/analyses/{newest}/compare", params={"baseline": oldest}
        ).json()
        reversed_ = authed_client.get(
            f"/api/v1/analyses/{oldest}/compare", params={"baseline": newest}
        ).json()

        assert forward["baseline_id"] == reversed_["baseline_id"] == oldest
        assert forward["score_delta"] == reversed_["score_delta"]

    def test_labels_each_metric_with_what_improvement_means(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        newest, _ = self.analysis_ids(authed_client, project_id)

        metrics = {
            metric["key"]: metric
            for metric in authed_client.get(f"/api/v1/analyses/{newest}/compare").json()["metrics"]
        }

        assert metrics["quality_score"]["polarity"] == "higher_is_better"
        assert metrics["missing_percentage"]["polarity"] == "lower_is_better"
        # More rows is neither good nor bad; colouring it green would be a lie.
        assert metrics["row_count"]["polarity"] == "neutral"
        assert metrics["row_count"]["direction"] in {"changed", "unchanged"}

    def test_names_the_finding_types_that_were_resolved(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        newest, _ = self.analysis_ids(authed_client, project_id)

        body = authed_client.get(f"/api/v1/analyses/{newest}/compare").json()

        assert "negative_values" in body["resolved_types"]
        assert "constant_column" in body["resolved_types"]
        resolved = next(
            change for change in body["finding_types"] if change["type"] == "negative_values"
        )
        assert resolved["baseline_count"] > 0
        assert resolved["current_count"] == 0

    def test_reports_per_dimension_movement(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        newest, _ = self.analysis_ids(authed_client, project_id)

        dimensions = {
            entry["key"]: entry
            for entry in authed_client.get(f"/api/v1/analyses/{newest}/compare").json()[
                "dimensions"
            ]
        }

        assert dimensions["validity"]["delta"] < 0, "validity penalties fell"
        assert dimensions["validity"]["direction"] == "improved"

    def test_rejects_comparing_an_analysis_with_itself(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        newest, _ = self.analysis_ids(authed_client, project_id)

        response = authed_client.get(
            f"/api/v1/analyses/{newest}/compare", params={"baseline": newest}
        )
        assert response.status_code == 422

    def test_rejects_comparing_across_projects(
        self, authed_client: TestClient, project_id: str, two_analyses: tuple[dict, dict]
    ) -> None:
        other_project = authed_client.post("/api/v1/projects", json={"name": "Other"}).json()["id"]
        upload(authed_client, other_project, "clean_transactions.csv")

        newest, _ = self.analysis_ids(authed_client, project_id)
        elsewhere = authed_client.get(f"/api/v1/projects/{other_project}/history").json()["items"][
            0
        ]["id"]

        response = authed_client.get(
            f"/api/v1/analyses/{newest}/compare", params={"baseline": elsewhere}
        )
        assert response.status_code == 422

    def test_says_so_when_there_is_nothing_to_compare_against(
        self, authed_client: TestClient, project_id: str
    ) -> None:
        upload(authed_client, project_id, "clean_transactions.csv")
        (only,) = self.analysis_ids(authed_client, project_id)

        response = authed_client.get(f"/api/v1/analyses/{only}/compare")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "no_baseline"


class TestAuthorization:
    def test_cannot_read_another_users_history_or_comparison(
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
        client.post(
            f"/api/v1/projects/{project}/datasets",
            files={
                "file": (
                    "clean.csv",
                    io.BytesIO(sample_bytes("clean_transactions.csv")),
                    "text/csv",
                )
            },
            headers=auth_headers(other),
        )
        analysis_id = client.get(
            f"/api/v1/projects/{project}/history", headers=auth_headers(other)
        ).json()["items"][0]["id"]

        assert (
            client.get(
                f"/api/v1/projects/{project}/history", headers=auth_headers(user)
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/analyses/{analysis_id}/compare", headers=auth_headers(user)
            ).status_code
            == 404
        )
