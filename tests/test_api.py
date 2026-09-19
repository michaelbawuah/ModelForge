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
        "build_sha": "unknown",
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

def test_upload_model_artifact(tmp_path) -> None:
    """An uploaded artifact is stored and registered with derived metadata."""

    from pathlib import Path

    from modelforge.api.app import app
    from modelforge.api.registry import get_artifact_store
    from modelforge.services.artifacts import LocalArtifactStore

    model_name = "artifact-integration-test"

    create_response = client.post(
        "/models",
        json={
            "name": model_name,
            "description": "Artifact upload integration test.",
        },
    )

    if create_response.status_code == 409:
        models_response = client.get("/models")
        model = next(
            item
            for item in models_response.json()
            if item["name"] == model_name
        )
    else:
        assert create_response.status_code == 201
        model = create_response.json()

    model_id = model["id"]
    store = LocalArtifactStore(tmp_path / "artifacts")

    app.dependency_overrides[get_artifact_store] = lambda: store

    try:
        response = client.post(
            f"/models/{model_id}/artifacts",
            data={
                "version": "artifact-test-v1",
                "framework": "fluxion",
            },
            files={
                "artifact": (
                    "model.bin",
                    b"real-model-artifact-bytes",
                    "application/octet-stream",
                )
            },
        )

        assert response.status_code in {201, 409}

        if response.status_code == 201:
            registered = response.json()

            artifact_path = Path(registered["artifact_uri"])

            assert artifact_path.exists()
            assert artifact_path.read_bytes() == b"real-model-artifact-bytes"
            assert registered["framework"] == "fluxion"
            assert registered["checksum"]
            assert registered["status"] == "REGISTERED"
    finally:
        app.dependency_overrides.pop(get_artifact_store, None)


def test_upload_artifact_for_missing_model(tmp_path) -> None:
    """Uploading to an unknown model fails without writing an artifact."""

    from modelforge.api.app import app
    from modelforge.api.registry import get_artifact_store
    from modelforge.services.artifacts import LocalArtifactStore

    store = LocalArtifactStore(tmp_path / "artifacts")
    app.dependency_overrides[get_artifact_store] = lambda: store

    try:
        response = client.post(
            "/models/999999999/artifacts",
            data={
                "version": "1.0.0",
                "framework": "fluxion",
            },
            files={
                "artifact": (
                    "model.bin",
                    b"should-not-be-stored",
                    "application/octet-stream",
                )
            },
        )

        assert response.status_code == 404
        assert not (tmp_path / "artifacts").exists()
    finally:
        app.dependency_overrides.pop(get_artifact_store, None)
