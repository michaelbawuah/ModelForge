"""Tests for the bundled ModelForge public site and browser console."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_root_serves_public_landing_page() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Deploy any model." in response.text
    assert "Framework-neutral ML infrastructure" in response.text
    assert "/dashboard" in response.text


def test_app_redirects_to_console() -> None:
    response = client.get("/app", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard"


def test_dashboard_is_bundled_and_operational() -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Production overview" in response.text
    assert "Deployment fleet" in response.text
    assert "Runtime fleet" in response.text
    assert "Live inference" in response.text
    assert "API keys" in response.text
    assert "X-ModelForge-Workspace" in response.text
    assert "X-ModelForge-CSRF" in response.text
    assert "/deployments/" in response.text
    assert "/predict" in response.text


def test_dashboard_assets_are_external_and_allowlisted() -> None:
    dashboard = client.get("/dashboard")
    landing = client.get("/")
    script = client.get("/assets/dashboard.js")
    dashboard_css = client.get("/assets/dashboard.css")
    landing_css = client.get("/assets/landing.css")

    assert "<style>" not in dashboard.text
    assert "<script>" not in dashboard.text
    assert "/assets/dashboard.js" in dashboard.text
    assert "/assets/dashboard.css" in dashboard.text
    assert "<style>" not in landing.text
    assert "/assets/landing.css" in landing.text

    assert script.status_code == 200
    assert "application/javascript" in script.headers["content-type"]
    assert dashboard_css.status_code == 200
    assert "text/css" in dashboard_css.headers["content-type"]
    assert landing_css.status_code == 200

    missing = client.get("/assets/not-allowed.txt")
    assert missing.status_code == 404
