"""Tests for the ModelForge API."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_health() -> None:
    """The service exposes a basic liveness endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "modelforge-api",
    }


def test_model_registry_workflow() -> None:
    """A model and one version can be persisted and retrieved."""

    model_name = "fluxion-integration-test"

    create_response = client.post(
        "/models",
        json={
            "name": model_name,
            "description": "Fluxion model used for registry integration testing.",
        },
    )

    # Repeated local test runs may encounter the model created by an earlier run.
    if create_response.status_code == 409:
        models_response = client.get("/models")
        assert models_response.status_code == 200

        model = next(
            item
            for item in models_response.json()
            if item["name"] == model_name
        )
    else:
        assert create_response.status_code == 201
        model = create_response.json()

    model_id = model["id"]

    assert model["name"] == model_name

    get_response = client.get(f"/models/{model_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == model_name

    version_response = client.post(
        f"/models/{model_id}/versions",
        json={
            "version": "1.0.0",
            "framework": "fluxion",
            "artifact_uri": "s3://modelforge-test/fluxion/1.0.0/model.bin",
            "checksum": "integration-test-checksum",
        },
    )

    assert version_response.status_code in {201, 409}

    versions_response = client.get(f"/models/{model_id}/versions")

    assert versions_response.status_code == 200
    versions = versions_response.json()

    assert any(
        version["version"] == "1.0.0"
        and version["framework"] == "fluxion"
        for version in versions
    )