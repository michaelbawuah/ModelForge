"""Tests for ModelForge HTTP security middleware."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_security_headers_and_request_id_are_added() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-request-id"]


def test_request_id_is_preserved() -> None:
    response = client.get(
        "/health",
        headers={"X-Request-ID": "trace-123"},
    )

    assert response.headers["x-request-id"] == "trace-123"
