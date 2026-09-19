"""Tests for the bundled ModelForge browser dashboard."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_root_redirects_to_dashboard() -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard"


def test_dashboard_is_bundled_and_operational() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ModelForge Control Plane" in response.text
    assert "Deployment fleet" in response.text
    assert "Runtime fleet" in response.text
    assert "Live inference" in response.text
    assert "/deployments/" in response.text
    assert "/predict" in response.text
