"""End-to-end tests for weighted canary inference and automatic rollback."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from modelforge.api.app import app
from modelforge.api.inference import get_inference_service
from modelforge.api.registry import get_artifact_store
from modelforge.services.artifacts import LocalArtifactStore

client = TestClient(app)


def _upload_json_version(
    *,
    model_id: int,
    version: str,
    weight: float,
    bias: float,
) -> dict:
    payload = json.dumps(
        {
            "operation": "linear",
            "weight": weight,
            "bias": bias,
        }
    ).encode()

    response = client.post(
        f"/models/{model_id}/artifacts",
        data={
            "version": version,
            "framework": "modelforge-json",
        },
        files={
            "artifact": (
                "model.json",
                io.BytesIO(payload),
                "application/json",
            )
        },
    )
    assert response.status_code == 201
    return response.json()


def _setup_canary(tmp_path: Path) -> dict:
    suffix = uuid.uuid4().hex[:10]
    environment = f"inference-canary-{suffix}"
    store = LocalArtifactStore(tmp_path / "artifacts")
    app.dependency_overrides[get_artifact_store] = lambda: store

    model = client.post(
        "/models",
        json={
            "name": f"inference-canary-model-{suffix}",
            "description": "Weighted canary inference test.",
        },
    )
    assert model.status_code == 201
    model_id = model.json()["id"]

    stable_version = _upload_json_version(
        model_id=model_id,
        version="1.0.0",
        weight=2.0,
        bias=1.0,
    )
    canary_version = _upload_json_version(
        model_id=model_id,
        version="2.0.0",
        weight=10.0,
        bias=0.0,
    )

    stable = client.post(
        "/deployments",
        json={
            "model_version_id": stable_version["id"],
            "environment": environment,
        },
    ).json()
    canary = client.post(
        "/deployments",
        json={
            "model_version_id": canary_version["id"],
            "environment": environment,
        },
    ).json()

    assert client.post(
        f"/deployments/{stable['id']}/promote"
    ).status_code == 200
    assert client.post(
        f"/deployments/{canary['id']}/canary",
        json={"weight": 50},
    ).status_code == 200

    get_inference_service().clear_cache()

    return {
        "environment": environment,
        "stable": stable,
        "canary": canary,
        "stable_version": stable_version,
        "canary_version": canary_version,
    }


def test_weighted_routing_can_serve_canary_and_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources = _setup_canary(tmp_path)

    monkeypatch.setattr(
        "modelforge.services.inference.randbelow",
        lambda _: 0,
    )
    canary_response = client.post(
        "/predict",
        json={
            "environment": resources["environment"],
            "inputs": 3.0,
        },
    )

    assert canary_response.status_code == 200
    assert canary_response.json()["prediction"] == 30.0
    assert canary_response.json()["traffic_lane"] == "canary"
    assert canary_response.json()["canary_fallback"] is False
    assert canary_response.json()["deployment_id"] == resources["canary"]["id"]

    monkeypatch.setattr(
        "modelforge.services.inference.randbelow",
        lambda _: 99,
    )
    stable_response = client.post(
        "/predict",
        json={
            "environment": resources["environment"],
            "inputs": 3.0,
        },
    )

    assert stable_response.status_code == 200
    assert stable_response.json()["prediction"] == 7.0
    assert stable_response.json()["traffic_lane"] == "stable"
    assert stable_response.json()["canary_fallback"] is False
    assert stable_response.json()["deployment_id"] == resources["stable"]["id"]

    app.dependency_overrides.clear()


def test_broken_canary_is_automatically_removed_and_falls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources = _setup_canary(tmp_path)

    Path(resources["canary_version"]["artifact_uri"]).unlink()
    get_inference_service().clear_cache()

    monkeypatch.setattr(
        "modelforge.services.inference.randbelow",
        lambda _: 0,
    )

    response = client.post(
        "/predict",
        json={
            "environment": resources["environment"],
            "inputs": 3.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prediction"] == 7.0
    assert payload["traffic_lane"] == "stable"
    assert payload["canary_fallback"] is True
    assert payload["deployment_id"] == resources["stable"]["id"]

    canary = client.get(
        f"/deployments/{resources['canary']['id']}"
    ).json()
    assert canary["state"] == "FAILED"
    assert "Automatic rollback" in canary["failure_reason"]

    target = client.get(
        f"/deployment-targets/{resources['environment']}"
    ).json()
    assert target["active_deployment_id"] == resources["stable"]["id"]
    assert target["canary_deployment_id"] is None
    assert target["canary_weight"] == 0

    app.dependency_overrides.clear()
