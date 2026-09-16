"""Live end-to-end test for ModelForge serving through the Go runtime."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from modelforge.api.app import app
from modelforge.api.inference import (
    get_external_runtime_registry,
    get_inference_service,
)
from modelforge.api.registry import get_artifact_store
from modelforge.services.artifacts import LocalArtifactStore
from modelforge.services.external_runtime_registry import (
    ExternalRuntimeAlreadyRegisteredError,
)
from modelforge.services.external_runtimes import (
    ExternalRuntimeSpec,
    ExternalRuntimeUnavailableError,
)

GO_FRAMEWORK = "go-linear"
GO_RUNTIME_URL = "http://127.0.0.1:8090"


def _unique_name(prefix: str) -> str:
    """Return a collision-resistant resource name."""

    return f"{prefix}-{uuid.uuid4().hex}"


def _require_go_runtime() -> None:
    """Skip the live integration test when the Go process is unavailable."""

    from modelforge.services.external_runtimes import ExternalRuntimeClient

    runtime = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="modelforge-go-runtime",
            base_url=GO_RUNTIME_URL,
            timeout_seconds=1.0,
        )
    )

    try:
        healthy = runtime.health()
    except ExternalRuntimeUnavailableError:
        pytest.skip("ModelForge Go runtime is not running on port 8090.")

    if not healthy:
        pytest.skip("ModelForge Go runtime is not healthy.")


def _register_go_runtime() -> None:
    """Ensure the process-local external registry knows the Go runtime."""

    registry = get_external_runtime_registry()

    if registry.contains(GO_FRAMEWORK):
        return

    try:
        registry.register(
            GO_FRAMEWORK,
            ExternalRuntimeSpec(
                name="modelforge-go-runtime",
                base_url=GO_RUNTIME_URL,
                timeout_seconds=3.0,
            ),
        )
    except ExternalRuntimeAlreadyRegisteredError:
        pass


def test_modelforge_serves_deployed_model_through_go_runtime(
    tmp_path,
) -> None:
    """Serve a deployed model through the real external Go process."""

    _require_go_runtime()
    _register_go_runtime()

    artifact_store = LocalArtifactStore(
        tmp_path / "artifacts"
    )

    app.dependency_overrides[get_artifact_store] = (
        lambda: artifact_store
    )

    client = TestClient(app)

    model_name = _unique_name("go-linear-model")
    environment = _unique_name("go-production")

    artifact_path = tmp_path / "linear.model"

    artifact_path.write_text(
        json.dumps(
            {
                "format": "go-linear-v1",
                "weight": 2,
                "bias": 1,
            }
        ),
        encoding="utf-8",
    )

    try:
        create_response = client.post(
            "/models",
            json={
                "name": model_name,
                "description": (
                    "Linear model served by the external Go runtime."
                ),
            },
        )

        assert create_response.status_code == 201

        model_id = create_response.json()["id"]

        with artifact_path.open("rb") as artifact_file:
            upload_response = client.post(
                f"/models/{model_id}/artifacts",
                data={
                    "version": "1.0.0",
                    "framework": GO_FRAMEWORK,
                },
                files={
                    "artifact": (
                        "linear.model",
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
        assert promote_response.json()["state"] == "ACTIVE"

        service = get_inference_service()
        service.clear_cache()

        prediction_response = client.post(
            "/predict",
            json={
                "environment": environment,
                "inputs": 5,
            },
        )

        assert prediction_response.status_code == 200

        payload = prediction_response.json()

        assert payload["prediction"] == 11
        assert payload["environment"] == environment
        assert payload["deployment_id"] == deployment["id"]
        assert payload["model_version_id"] == model_version["id"]
        assert payload["model_version"] == "1.0.0"
        assert payload["framework"] == GO_FRAMEWORK
        assert payload["cache_hit"] is False

    finally:
        app.dependency_overrides.clear()