"""End-to-end inference orchestration for ModelForge."""

from __future__ import annotations

from dataclasses import dataclass
from secrets import randbelow
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.deployment_target import DeploymentTarget
from modelforge.models.registry import ModelVersion
from modelforge.services.artifact_factory import create_artifact_store
from modelforge.services.artifacts import (
    ArtifactIntegrityError as StorageArtifactIntegrityError,
)
from modelforge.services.artifacts import ArtifactNotFoundError, ArtifactStore
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
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self._resolver = resolver
        self._cache = cache
        self._artifact_store = artifact_store or create_artifact_store()

    def clear_cache(self) -> None:
        """Evict all process-local loaded models."""

        self._cache.clear()

    def predict(
        self,
        session: Session,
        *,
        environment: str,
        inputs: Any,
        workspace_id: int = 1,
    ) -> PredictionResult:
        """Run inference using weighted stable/canary routing."""

        target = get_deployment_target(
            session,
            environment,
            workspace_id=workspace_id,
        )
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
                workspace_id=workspace_id,
            )
            CANARY_AUTOMATIC_ROLLBACKS.labels(target.environment).inc()

            stable = session.scalar(
                select(Deployment).where(
                    Deployment.id == target.active_deployment_id,
                    Deployment.workspace_id == workspace_id,
                )
            )
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

        deployment = session.scalar(
            select(Deployment).where(
                Deployment.id == deployment_id,
                Deployment.workspace_id == target.workspace_id,
            )
        )
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
        loaded_model, cache_hit = self._cache.get_or_load(
            model_version.id,
            lambda: self._materialize_and_load(
                artifact_uri=model_version.artifact_uri,
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

    def _materialize_and_load(
        self,
        *,
        artifact_uri: str,
        expected_checksum: str,
        runtime: ModelRuntime,
    ) -> Any:
        try:
            artifact_path = self._artifact_store.materialize(
                artifact_uri,
                expected_checksum,
            )
        except ArtifactNotFoundError as exc:
            raise ArtifactUnavailableError(str(exc)) from exc
        except StorageArtifactIntegrityError as exc:
            raise ArtifactIntegrityError(str(exc)) from exc

        return runtime.load(artifact_path)
