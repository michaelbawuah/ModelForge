"""End-to-end test for externally supplied ModelForge runtime plugins."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from modelforge.api.app import app
from modelforge.api.inference import get_inference_service
from modelforge.api.registry import get_artifact_store
from modelforge.services.artifacts import LocalArtifactStore
from modelforge.services.external_runtime_registry import (
    ExternalRuntimeRegistry,
)
from modelforge.services.inference import InferenceService
from modelforge.services.model_cache import ModelCache
from modelforge.services.runtime_bootstrap import create_runtime_registry
from modelforge.services.runtime_resolver import RuntimeResolver
from modelforge.services.runtimes import RuntimePlugin


class FutureAIRuntime:
    """Runtime supplied by a framework ModelForge core does not know."""

    def load(self, artifact_path: Path) -> dict[str, Any]:
        """Load the fake framework's artifact."""

        with artifact_path.open(encoding="utf-8") as artifact_file:
            artifact = json.load(artifact_file)

        if artifact.get("format") != "future-ai-v1":
            raise ValueError("Unsupported FutureAI artifact.")

        return artifact

    def predict(
        self,
        model: dict[str, Any],
        inputs: Any,
    ) -> Any:
        """Execute the fake framework's model."""

        multiplier = model["multiplier"]
        bias = model["bias"]

        if not isinstance(inputs, (int, float)):
            raise TypeError("FutureAI expects one numeric input.")

        return multiplier * inputs + bias


class FakeEntryPoint:
    """Stand-in for metadata from an independently installed package."""

    name = "future-ai"

    @staticmethod
    def load():
        """Return the plugin factory exported by the external package."""

        return lambda: RuntimePlugin(
            framework="future-ai",
            runtime=FutureAIRuntime(),
        )


def _unique_name(prefix: str) -> str:
    """Return a collision-resistant test resource name."""

    return f"{prefix}-{uuid.uuid4().hex}"


def test_unknown_plugin_runtime_serves_through_modelforge(
    tmp_path,
) -> None:
    """A runtime unknown to ModelForge core can serve a deployed model."""

    registry = create_runtime_registry(
        discover_plugins=False,
    )

    registry._load_plugin(FakeEntryPoint())

    assert "future-ai" in registry.frameworks()

    resolver = RuntimeResolver(
        runtimes=registry,
        external_runtimes=ExternalRuntimeRegistry(),
    )

    plugin_service = InferenceService(
    resolver=resolver,
    cache=ModelCache(),
)

    artifact_store = LocalArtifactStore(
        tmp_path / "artifacts"
    )

    app.dependency_overrides[get_artifact_store] = (
        lambda: artifact_store
    )
    app.dependency_overrides[get_inference_service] = (
        lambda: plugin_service
    )

    client = TestClient(app)

    model_name = _unique_name("future-ai-model")
    environment = _unique_name("future-ai-production")

    create_model_response = client.post(
        "/models",
        json={
            "name": model_name,
            "description": (
                "Model supplied by an external runtime plugin."
            ),
        },
    )

    assert create_model_response.status_code == 201

    model_id = create_model_response.json()["id"]

    artifact_bytes = json.dumps(
        {
            "format": "future-ai-v1",
            "multiplier": 7,
            "bias": 3,
        }
    ).encode()

    upload_response = client.post(
        f"/models/{model_id}/artifacts",
        data={
            "version": "1.0.0",
            "framework": "future-ai",
        },
        files={
            "artifact": (
                "future.model",
                io.BytesIO(artifact_bytes),
                "application/octet-stream",
            ),
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

    first_prediction = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": 5,
        },
    )

    assert first_prediction.status_code == 200

    first_payload = first_prediction.json()

    assert first_payload["prediction"] == 38
    assert first_payload["framework"] == "future-ai"
    assert first_payload["environment"] == environment
    assert first_payload["deployment_id"] == deployment["id"]
    assert first_payload["model_version_id"] == model_version["id"]
    assert first_payload["cache_hit"] is False

    second_prediction = client.post(
        "/predict",
        json={
            "environment": environment,
            "inputs": 10,
        },
    )

    assert second_prediction.status_code == 200

    second_payload = second_prediction.json()

    assert second_payload["prediction"] == 73
    assert second_payload["framework"] == "future-ai"
    assert second_payload["cache_hit"] is True

    plugin_service.clear_cache()
    app.dependency_overrides.clear()