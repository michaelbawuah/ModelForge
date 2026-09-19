"""HTTP API for ModelForge inference serving."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.schemas.inference import PredictionRequest, PredictionResponse
from modelforge.services.auth import Principal, get_principal
from modelforge.services.deployment_targets import DeploymentTargetNotFoundError
from modelforge.services.external_runtime_bootstrap import (
    create_external_runtime_registry,
)
from modelforge.services.external_runtime_registry import ExternalRuntimeRegistry
from modelforge.services.external_runtimes import (
    ExternalRuntimePredictionError,
    ExternalRuntimeProtocolError,
    ExternalRuntimeUnavailableError,
)
from modelforge.services.inference import (
    ArtifactIntegrityError,
    ArtifactUnavailableError,
    InferenceConfigurationError,
    InferenceService,
)
from modelforge.services.model_cache import ModelCache
from modelforge.services.runtime_bootstrap import create_runtime_registry
from modelforge.services.runtime_resolver import RuntimeResolver
from modelforge.services.runtimes import RuntimeNotFoundError, RuntimeRegistry

router = APIRouter(tags=["inference"])

_runtime_registry = create_runtime_registry()
_external_runtime_registry = create_external_runtime_registry()
_runtime_resolver = RuntimeResolver(
    runtimes=_runtime_registry,
    external_runtimes=_external_runtime_registry,
)
_model_cache = ModelCache()
_inference_service = InferenceService(
    resolver=_runtime_resolver,
    cache=_model_cache,
)


def get_inference_service() -> InferenceService:
    return _inference_service


def get_runtime_registry() -> RuntimeRegistry:
    return _runtime_registry


def get_external_runtime_registry() -> ExternalRuntimeRegistry:
    return _external_runtime_registry


@router.post(
    "/predict",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
)
def predict(
    request: PredictionRequest,
    session: Annotated[Session, Depends(get_db)],
    service: Annotated[InferenceService, Depends(get_inference_service)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> PredictionResponse:
    try:
        result = service.predict(
            session,
            environment=request.environment,
            inputs=request.inputs,
            workspace_id=principal.workspace_id,
        )
    except DeploymentTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No active deployment exists for environment "
                f"'{request.environment}'."
            ),
        ) from exc
    except (
        ArtifactUnavailableError,
        ArtifactIntegrityError,
        RuntimeNotFoundError,
        InferenceConfigurationError,
        ExternalRuntimeUnavailableError,
        ExternalRuntimeProtocolError,
        ExternalRuntimePredictionError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return PredictionResponse(
        prediction=result.prediction,
        environment=result.environment,
        deployment_id=result.deployment_id,
        model_version_id=result.model_version_id,
        model_version=result.model_version,
        framework=result.framework,
        cache_hit=result.cache_hit,
        traffic_lane=result.traffic_lane,
        canary_fallback=result.canary_fallback,
    )
