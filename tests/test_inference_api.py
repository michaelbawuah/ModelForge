"""End-to-end tests for ModelForge inference serving."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest
import torch
from fastapi.testclient import TestClient

from modelforge.api.app import app
from modelforge.api.inference import get_inference_service
from modelforge.api.registry import get_artifact_store
from modelforge.services.artifacts import LocalArtifactStore
from modelforge.services.pytorch_runtime import LinearModel

client = TestClient(app)


def _unique_name(prefix: str) -> str:
    """Return a model name that cannot collide with previous test runs."""

    return f"{prefix}-{uuid.uuid4().hex}"


def _create_active_json_model(
    tmp_path,
    *,
    environment: str,
    weight: float = 2.0,
    bias: float = 1.0,
):
    """Create, upload, deploy, and promote one executable JSON model."""

    model_name = _unique_name("inference-model")
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")

    app.dependency_overrides[get_artifact_store] = lambda: artifact_store

    model_response = client.post(
        "/models",
        json={
            "name": model_name,
            "description": "End-to-end inference test model.",
        },
    )

    assert model_response.status_code == 201
    model_id = model_response.json()["id"]

    artifact_payload = json.dumps(
        {
            "operation": "linear",
            "weight": weight,
            "bias": bias,
        }
    ).encode()

    version_response = client.post(
        f"/models/{model_id}/artifacts",
        data={
            "version": "1.0.0",
            "framework": "modelforge-json",
        },
        files={
            "artifact": (
                "model.json",
                io.BytesIO(artifact_payload),
                "application/json",
            )
        },
    )

    assert version_response.status_code == 201
    version = version_response.json()

    deployment_response = client.post(
        "/deployments",
        json={
            "model_version_id": version["id"],
            "environment": environment,
        },
    )

    assert deployment_response.status_code == 201
    deployment = deployment_response.json()

    promote_response = client.post(
        f"/deployments/{deployment['id']}/promote"
    )

    assert promote_response.status_code == 200
    assert promote_response.json()["state"] == "ACTIVE"

    return {
        "model_id": model_id,
        "version": version,
        "deployment": promote_response.json(),
        "artifact_store": artifact_store,
    }


def test_prediction_uses_active_deployment_and_cache(tmp_path) -> None:
    """A promoted artifact can serve predictions and is cached after loading."""

    environment = _unique_name("inference-env")

    resources = _create_active_json_model(
        tmp_path,
        environment=environment,
        weight=2.0,
        bias=1.0,
    )

    service = get_inference_service()
    service.clear_cache()

    first_response = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": 3.0,
        },
    )

    assert first_response.status_code == 200

    first = first_response.json()

    assert first["prediction"] == 7.0
    assert first["environment"] == environment
    assert first["deployment_id"] == resources["deployment"]["id"]
    assert first["model_version_id"] == resources["version"]["id"]
    assert first["model_version"] == "1.0.0"
    assert first["framework"] == "modelforge-json"
    assert first["cache_hit"] is False

    second_response = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": [1.0, 2.0, 3.0],
        },
    )

    assert second_response.status_code == 200

    second = second_response.json()

    assert second["prediction"] == [3.0, 5.0, 7.0]
    assert second["deployment_id"] == resources["deployment"]["id"]
    assert second["model_version_id"] == resources["version"]["id"]
    assert second["cache_hit"] is True

    app.dependency_overrides.clear()


def test_tampered_artifact_is_rejected(tmp_path) -> None:
    """Inference refuses to execute an artifact whose bytes have changed."""

    environment = _unique_name("tamper-env")

    resources = _create_active_json_model(
        tmp_path,
        environment=environment,
    )

    service = get_inference_service()
    service.clear_cache()

    artifact_uri = resources["version"]["artifact_uri"]

    with open(artifact_uri, "wb") as artifact_file:
        artifact_file.write(
            json.dumps(
                {
                    "operation": "linear",
                    "weight": 999.0,
                    "bias": 999.0,
                }
            ).encode()
        )

    response = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": 3.0,
        },
    )

    assert response.status_code == 503
    assert "checksum" in response.json()["detail"].lower()

    app.dependency_overrides.clear()


def test_unknown_environment_cannot_serve_predictions() -> None:
    """Inference requires an authoritative active deployment target."""

    response = client.post(
        "/predict",
        json={
            "environment": _unique_name("missing-env"),
            "inputs": 3.0,
        },
    )

    assert response.status_code == 404
    assert "no active deployment" in response.json()["detail"].lower()


def test_cached_model_survives_artifact_removal(tmp_path) -> None:
    """A verified cached model does not require rereading its artifact."""

    environment = _unique_name("cache-proof-env")

    resources = _create_active_json_model(
        tmp_path,
        environment=environment,
        weight=4.0,
        bias=2.0,
    )

    service = get_inference_service()
    service.clear_cache()

    first_response = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": 2.0,
        },
    )

    assert first_response.status_code == 200
    assert first_response.json()["prediction"] == 10.0
    assert first_response.json()["cache_hit"] is False

    artifact_uri = resources["version"]["artifact_uri"]
    Path(artifact_uri).unlink()

    second_response = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": 3.0,
        },
    )

    assert second_response.status_code == 200
    assert second_response.json()["prediction"] == 14.0
    assert second_response.json()["cache_hit"] is True

    service.clear_cache()

    third_response = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": 3.0,
        },
    )

    assert third_response.status_code == 503
    assert "does not exist" in third_response.json()["detail"].lower()

    app.dependency_overrides.clear()


def test_pytorch_model_serves_through_full_deployment_lifecycle(
    tmp_path,
) -> None:
    """A PyTorch artifact can be uploaded, deployed, cached, and served."""

    environment = _unique_name("pytorch-production")
    model_name = _unique_name("pytorch-model")

    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store

    model = LinearModel(
        input_features=2,
        output_features=1,
    )

    with torch.no_grad():
        model.linear.weight.copy_(
            torch.tensor(
                [[2.0, 3.0]],
                dtype=torch.float32,
            )
        )
        model.linear.bias.copy_(
            torch.tensor(
                [1.0],
                dtype=torch.float32,
            )
        )

    artifact_path = tmp_path / "trained-model.pt"

    torch.save(
        {
            "format_version": 1,
            "architecture": "linear",
            "config": {
                "input_features": 2,
                "output_features": 1,
            },
            "state_dict": model.state_dict(),
        },
        artifact_path,
    )

    create_model_response = client.post(
        "/models",
        json={
            "name": model_name,
            "description": "End-to-end PyTorch inference test model.",
        },
    )

    assert create_model_response.status_code == 201
    model_id = create_model_response.json()["id"]

    with artifact_path.open("rb") as artifact_file:
        upload_response = client.post(
            f"/models/{model_id}/artifacts",
            data={
                "version": "1.0.0",
                "framework": "pytorch",
            },
            files={
                "artifact": (
                    "trained-model.pt",
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

    service = get_inference_service()
    service.clear_cache()

    first_prediction = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": [4.0, 5.0],
        },
    )

    assert first_prediction.status_code == 200
    first_payload = first_prediction.json()

    assert first_payload["prediction"] == pytest.approx(24.0)
    assert first_payload["environment"] == environment
    assert first_payload["deployment_id"] == deployment["id"]
    assert first_payload["model_version_id"] == model_version["id"]
    assert first_payload["model_version"] == "1.0.0"
    assert first_payload["framework"] == "pytorch"
    assert first_payload["cache_hit"] is False

    second_prediction = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": [1.0, 2.0],
        },
    )

    assert second_prediction.status_code == 200
    second_payload = second_prediction.json()

    assert second_payload["prediction"] == pytest.approx(9.0)
    assert second_payload["model_version_id"] == model_version["id"]
    assert second_payload["cache_hit"] is True

    service.clear_cache()
    app.dependency_overrides.clear()