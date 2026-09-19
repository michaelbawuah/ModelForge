"""Tests for runtime fleet inspection endpoints."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_runtime_inventory_lists_in_process_frameworks() -> None:
    response = client.get("/runtimes")

    assert response.status_code == 200
    payload = response.json()
    frameworks = {
        runtime["framework"]
        for runtime in payload["in_process"]
    }

    assert {"modelforge-json", "pytorch", "onnx"} <= frameworks
    assert isinstance(payload["external"], list)


def test_runtime_health_endpoint_is_observable() -> None:
    response = client.get("/runtimes/health")

    assert response.status_code == 200
    assert "external" in response.json()
