"""Tests for ModelForge operational endpoints."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_health_reports_process_alive(monkeypatch) -> None:
    monkeypatch.setenv("MODELFORGE_BUILD_SHA", "a" * 40)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["build_sha"] == "a" * 40


def test_readiness_checks_database() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "reachable",
    }


def test_metrics_endpoint_exposes_prometheus_data() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "modelforge_prediction_requests_total" in response.text
    assert "modelforge_prediction_latency_seconds" in response.text
    assert "modelforge_model_cache_events_total" in response.text
    assert "modelforge_external_runtime_requests_total" in response.text
    assert "modelforge_external_runtime_retries_total" in response.text
    assert "modelforge_external_runtime_circuit_open_total" in response.text


def test_metrics_can_be_protected_with_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("MODELFORGE_METRICS_TOKEN", "metrics-secret")

    unauthorized = client.get("/metrics")
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/metrics",
        headers={"Authorization": "Bearer metrics-secret"},
    )
    assert authorized.status_code == 200
