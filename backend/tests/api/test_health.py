"""Health endpoints and the global error envelope."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"


def test_readiness_checks_the_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"]


def test_root_advertises_the_product(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["name"] == "Obseil"
    assert "hidden" in body["tagline"]
