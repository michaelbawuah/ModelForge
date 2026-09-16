"""End-to-end tests for external BYOR inference."""

from __future__ import annotations

import json
import uuid

import httpx
from fastapi.testclient import TestClient

from modelforge.api.app import app
from modelforge.api.inference import (
    get_external_runtime_registry,
    get_inference_service,
)
from modelforge.api.registry import get_artifact_store
from modelforge.services.artifacts import LocalArtifactStore
from modelforge.services.external_runtimes import ExternalRuntimeSpec

client = TestClient(app)


def _unique_name(prefix: str) -> str:
    """Return a unique test resource name."""

    return f"{prefix}-{uuid.uuid4().hex}"


def test_unknown_framework_serves_through_external_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    """An unknown framework can use the complete ModelForge lifecycle."""

    framework = _unique_name("nebulaml")
    environment = _unique_name("byor-production")
    model_name = _unique_name("nebula-model")

    artifact_store = LocalArtifactStore(
        tmp_path / "artifacts"
    )

    app.dependency_overrides[get_artifact_store] = (
        lambda: artifact_store
    )

    external_registry = get_external_runtime_registry()

    external_registry.register(
        framework,
        ExternalRuntimeSpec(
            name="nebula-runtime",
            base_url="http://nebula-runtime:9100",
            timeout_seconds=4.0,
        ),
    )

    artifact_path = tmp_path / "nebula.model"

    artifact_path.write_text(
        json.dumps(
            {
                "format": "nebulaml",
                "multiplier": 100,
            }
        ),
        encoding="utf-8",
    )

    create_model_response = client.post(
        "/models",
        json={
            "name": model_name,
            "description": (
                "Model served by an external BYOR runtime."
            ),
        },
    )

    assert create_model_response.status_code == 201

    model_id = create_model_response.json()["id"]

    with artifact_path.open("rb") as artifact_file:
        upload_response = client.post(
            f"/models/{model_id}/artifacts",
            data={
                "version": "2035.1.0",
                "framework": framework,
            },
            files={
                "artifact": (
                    "nebula.model",
                    artifact_file,
                    "application/octet-stream",
                )
            },
        )

    assert upload_response.status_code == 201

    model_version = upload_response.json()

    deployment_response = client.post(
        "/deployments",
        json={
            "model_version_id": model_version["id"],
            "environment": environment,
        },
    )

    assert deployment_response.status_code == 201

    deployment = deployment_response.json()

    promote_response = client.post(
        f"/deployments/{deployment['id']}/promote"
    )

    assert promote_response.status_code == 200

    def fake_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        assert url == "http://nebula-runtime:9100/predict"
        assert timeout == 4.0

        assert json["inputs"] == [2.0, 4.0, 8.0]

        model = json["model"]

        assert model["model_version_id"] == model_version["id"]
        assert model["version"] == "2035.1.0"
        assert model["framework"] == framework
        assert model["artifact_uri"] == model_version["artifact_uri"]
        assert model["checksum"] == model_version["checksum"]

        return httpx.Response(
            200,
            json={
                "prediction": [200.0, 400.0, 800.0],
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    service = get_inference_service()
    service.clear_cache()

    prediction_response = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": [2.0, 4.0, 8.0],
        },
    )

    assert prediction_response.status_code == 200

    payload = prediction_response.json()

    assert payload["prediction"] == [
        200.0,
        400.0,
        800.0,
    ]
    assert payload["environment"] == environment
    assert payload["deployment_id"] == deployment["id"]
    assert payload["model_version_id"] == model_version["id"]
    assert payload["model_version"] == "2035.1.0"
    assert payload["framework"] == framework
    assert payload["cache_hit"] is False

    app.dependency_overrides.clear()