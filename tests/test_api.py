"""Tests for the ModelForge API."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_health_endpoint() -> None:
    """The API should expose a basic liveness endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "modelforge-api",
    }
