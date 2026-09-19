"""End-to-end inference orchestration for ModelForge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from secrets import randbelow
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.deployment_target import DeploymentTarget
from modelforge.models.registry import ModelVersion
from modelforge.services.artifacts import sha256_file
from modelforge.services.canaries import abort_canary
from modelforge.services.deployment_targets import get_deployment_target
from modelforge.services.external_runtimes import (
    ExternalRuntimeClient,
    ExternalRuntimeError,
)
from modelforge.services.metrics import (
    CANARY_AUTOMATIC_ROLLBACKS,
    CANARY_TRAFFIC,
)
from modelforge.services.model_cache import ModelCache
from modelforge.services.runtime_resolver import RuntimeResolver
from modelforge.services.runtimes import (
    ModelRuntime,
    RuntimeNotFoundError,
)

TrafficLane = Literal["stable", "canary"]


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
    traffic_lane: TrafficLane
    canary_fallback: bool


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
        """Run inference using weighted stable/canary routing."""

        target = get_deployment_target(session, environment)
        deployment, lane = self._select_deployment(session, target)

        try:
            result = self._predict_deployment(
                session,
                target_environment=target.environment,
                deployment=deployment,
                inputs=inputs,
                traffic_lane=lane,
                canary_fallback=False,
            )
        except (
            ArtifactUnavailableError,
            ArtifactIntegrityError,
            RuntimeNotFoundError,
            InferenceConfigurationError,
            ExternalRuntimeError,
        ) as exc:
            if lane != "canary":
                raise

            abort_canary(
                session,
                deployment_id=deployment.id,
                reason=(
                    "Automatic rollback after canary serving failure: "
                    f"{type(exc).__name__}."
                ),
            )
            CANARY_AUTOMATIC_ROLLBACKS.labels(target.environment).inc()

            stable = session.get(Deployment, target.active_deployment_id)
            if stable is None:
                raise InferenceConfigurationError(
                    "Stable deployment disappeared during canary fallback."
                ) from exc

            result = self._predict_deployment(
                session,
                target_environment=target.environment,
                deployment=stable,
                inputs=inputs,
                traffic_lane="stable",
                canary_fallback=True,
            )

        CANARY_TRAFFIC.labels(
            result.environment,
            result.traffic_lane,
        ).inc()
        return result

    def _select_deployment(
        self,
        session: Session,
        target: DeploymentTarget,
    ) -> tuple[Deployment, TrafficLane]:
        """Select stable or canary traffic based on configured weight."""

        use_canary = (
            target.canary_deployment_id is not None
            and target.canary_weight > 0
            and randbelow(100) < target.canary_weight
        )

        if use_canary:
            deployment_id = target.canary_deployment_id
            lane: TrafficLane = "canary"
            expected_state = DeploymentState.CANARY
        else:
            deployment_id = target.active_deployment_id
            lane = "stable"
            expected_state = DeploymentState.ACTIVE

        deployment = session.get(Deployment, deployment_id)
        if deployment is None:
            raise InferenceConfigurationError(
                f"{lane.capitalize()} target references a missing deployment."
            )

        if DeploymentState(deployment.state) is not expected_state:
            raise InferenceConfigurationError(
                f"{lane.capitalize()} deployment has invalid state "
                f"'{deployment.state}'."
            )

        if deployment.environment != target.environment:
            raise InferenceConfigurationError(
                "Deployment target environment does not match deployment."
            )

        return deployment, lane

    def _predict_deployment(
        self,
        session: Session,
        *,
        target_environment: str,
        deployment: Deployment,
        inputs: Any,
        traffic_lane: TrafficLane,
        canary_fallback: bool,
    ) -> PredictionResult:
        """Execute one already-selected deployment."""

        model_version = session.get(ModelVersion, deployment.model_version_id)
        if model_version is None:
            raise InferenceConfigurationError(
                "Serving deployment references a missing model version."
            )

        resolved = self._resolver.resolve(model_version.framework)

        if resolved.mode == "external":
            runtime = cast(ExternalRuntimeClient, resolved.runtime)
            prediction = runtime.predict(
                inputs=inputs,
                model=self._external_model_metadata(model_version),
            )
            return self._result(
                prediction=prediction,
                target_environment=target_environment,
                deployment=deployment,
                model_version=model_version,
                cache_hit=False,
                traffic_lane=traffic_lane,
                canary_fallback=canary_fallback,
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

        prediction = runtime.predict(loaded_model, inputs)

        return self._result(
            prediction=prediction,
            target_environment=target_environment,
            deployment=deployment,
            model_version=model_version,
            cache_hit=cache_hit,
            traffic_lane=traffic_lane,
            canary_fallback=canary_fallback,
        )

    @staticmethod
    def _result(
        *,
        prediction: Any,
        target_environment: str,
        deployment: Deployment,
        model_version: ModelVersion,
        cache_hit: bool,
        traffic_lane: TrafficLane,
        canary_fallback: bool,
    ) -> PredictionResult:
        return PredictionResult(
            prediction=prediction,
            environment=target_environment,
            deployment_id=deployment.id,
            model_version_id=model_version.id,
            model_version=model_version.version,
            framework=model_version.framework,
            cache_hit=cache_hit,
            traffic_lane=traffic_lane,
            canary_fallback=canary_fallback,
        )

    @staticmethod
    def _external_model_metadata(
        model_version: ModelVersion,
    ) -> dict[str, Any]:
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
        prefix = "file://"
        if artifact_uri.startswith(prefix):
            return Path(artifact_uri[len(prefix):])
        return Path(artifact_uri)
