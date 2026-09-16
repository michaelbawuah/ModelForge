"""HTTP API for ModelForge inference serving."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.schemas.inference import (
    PredictionRequest,
    PredictionResponse,
)
from modelforge.services.deployment_targets import (
    DeploymentTargetNotFoundError,
)
from modelforge.services.inference import (
    ArtifactIntegrityError,
    ArtifactUnavailableError,
    InferenceConfigurationError,
    InferenceService,
)
from modelforge.services.json_runtime import JsonModelRuntime
from modelforge.services.model_cache import ModelCache
from modelforge.services.onnx_runtime import OnnxRuntime
from modelforge.services.pytorch_runtime import PyTorchRuntime
from modelforge.services.runtimes import (
    RuntimeNotFoundError,
    RuntimeRegistry,
)

router = APIRouter(tags=["inference"])

_runtime_registry = RuntimeRegistry()
_runtime_registry.register("modelforge-json", JsonModelRuntime())
_runtime_registry.register("onnx", OnnxRuntime())
_runtime_registry.register("pytorch", PyTorchRuntime())

_model_cache = ModelCache()

_inference_service = InferenceService(
    runtimes=_runtime_registry,
    cache=_model_cache,
)


def get_inference_service() -> InferenceService:
    """Return the process-local inference service."""

    return _inference_service


@router.post(
    "/predict",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
)
def predict(
    request: PredictionRequest,
    session: Annotated[Session, Depends(get_db)],
    service: Annotated[
        InferenceService,
        Depends(get_inference_service),
    ],
) -> PredictionResponse:
    """Serve a prediction from an environment's active deployment."""

    try:
        result = service.predict(
            session,
            environment=request.environment,
            inputs=request.inputs,
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
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
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
    )