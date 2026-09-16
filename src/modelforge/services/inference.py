"""End-to-end inference orchestration for ModelForge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.registry import ModelVersion
from modelforge.services.artifacts import sha256_file
from modelforge.services.deployment_targets import get_deployment_target
from modelforge.services.external_runtimes import ExternalRuntimeClient
from modelforge.services.model_cache import ModelCache
from modelforge.services.runtime_resolver import RuntimeResolver
from modelforge.services.runtimes import ModelRuntime


class InferenceConfigurationError(Exception):
    """Raised when serving metadata is internally inconsistent."""


class ArtifactUnavailableError(Exception):
    """Raised when the registered artifact cannot be accessed."""


class ArtifactIntegrityError(Exception):
    """Raised when an artifact no longer matches its registered checksum."""


@dataclass(frozen=True)
class PredictionResult:
    """Prediction and immutable serving metadata."""

    prediction: Any
    environment: str
    deployment_id: int
    model_version_id: int
    model_version: str
    framework: str
    cache_hit: bool


class InferenceService:
    """Resolve deployments and execute models through the correct runtime."""

    def __init__(
        self,
        *,
        resolver: RuntimeResolver,
        cache: ModelCache,
    ) -> None:
        self._resolver = resolver
        self._cache = cache

    def clear_cache(self) -> None:
        """Evict all process-local loaded models."""

        self._cache.clear()

    def predict(
        self,
        session: Session,
        *,
        environment: str,
        inputs: Any,
    ) -> PredictionResult:
        """Run inference against an environment's authoritative deployment."""

        target = get_deployment_target(session, environment)

        deployment = session.get(
            Deployment,
            target.active_deployment_id,
        )

        if deployment is None:
            raise InferenceConfigurationError(
                "Deployment target references a missing deployment."
            )

        if deployment.state != DeploymentState.ACTIVE.value:
            raise InferenceConfigurationError(
                "Deployment target does not reference an ACTIVE deployment."
            )

        if deployment.environment != target.environment:
            raise InferenceConfigurationError(
                "Deployment target environment does not match deployment."
            )

        model_version = session.get(
            ModelVersion,
            deployment.model_version_id,
        )

        if model_version is None:
            raise InferenceConfigurationError(
                "Active deployment references a missing model version."
            )

        resolved = self._resolver.resolve(model_version.framework)

        if resolved.mode == "external":
            runtime = cast(
                ExternalRuntimeClient,
                resolved.runtime,
            )

            prediction = runtime.predict(
                inputs=inputs,
                model=self._external_model_metadata(model_version),
            )

            return self._result(
                prediction=prediction,
                target_environment=target.environment,
                deployment=deployment,
                model_version=model_version,
                cache_hit=False,
            )

        runtime = cast(ModelRuntime, resolved.runtime)
        artifact_path = self._artifact_path(model_version.artifact_uri)

        loaded_model, cache_hit = self._cache.get_or_load(
            model_version.id,
            lambda: self._verify_and_load(
                artifact_path=artifact_path,
                expected_checksum=model_version.checksum,
                runtime=runtime,
            ),
        )

        prediction = runtime.predict(
            loaded_model,
            inputs,
        )

        return self._result(
            prediction=prediction,
            target_environment=target.environment,
            deployment=deployment,
            model_version=model_version,
            cache_hit=cache_hit,
        )

    @staticmethod
    def _result(
        *,
        prediction: Any,
        target_environment: str,
        deployment: Deployment,
        model_version: ModelVersion,
        cache_hit: bool,
    ) -> PredictionResult:
        return PredictionResult(
            prediction=prediction,
            environment=target_environment,
            deployment_id=deployment.id,
            model_version_id=model_version.id,
            model_version=model_version.version,
            framework=model_version.framework,
            cache_hit=cache_hit,
        )

    @staticmethod
    def _external_model_metadata(
        model_version: ModelVersion,
    ) -> dict[str, Any]:
        """Describe an immutable model version to an external runtime."""

        return {
            "model_version_id": model_version.id,
            "version": model_version.version,
            "framework": model_version.framework,
            "artifact_uri": model_version.artifact_uri,
            "checksum": model_version.checksum,
        }

    @staticmethod
    def _verify_and_load(
        *,
        artifact_path: Path,
        expected_checksum: str,
        runtime: ModelRuntime,
    ) -> Any:
        """Verify an immutable artifact once before loading it into memory."""

        if not artifact_path.is_file():
            raise ArtifactUnavailableError(
                f"Artifact does not exist: {artifact_path}"
            )

        actual_checksum = sha256_file(artifact_path)

        if actual_checksum != expected_checksum:
            raise ArtifactIntegrityError(
                "Artifact checksum does not match the registered model version."
            )

        return runtime.load(artifact_path)

    @staticmethod
    def _artifact_path(artifact_uri: str) -> Path:
        """Convert a local artifact URI into a filesystem path."""

        prefix = "file://"

        if artifact_uri.startswith(prefix):
            return Path(artifact_uri[len(prefix):])

        return Path(artifact_uri)