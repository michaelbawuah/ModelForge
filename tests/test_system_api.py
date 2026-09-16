"""Tests for ModelForge operational endpoints."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_health_reports_process_alive() -> None:
    """Liveness remains independent of database readiness."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readiness_checks_database() -> None:
    """Readiness succeeds when ModelForge can reach its database."""

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "reachable",
    }


def test_metrics_endpoint_exposes_prometheus_data() -> None:
    """Prometheus can scrape ModelForge."""

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "modelforge_prediction_requests_total" in response.text
    assert "modelforge_prediction_latency_seconds" in response.text
    assert "modelforge_model_cache_events_total" in response.text