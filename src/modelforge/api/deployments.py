"""HTTP routes for ModelForge deployment lifecycle management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.schemas.deployments import (
    DeploymentCreate,
    DeploymentFailure,
    DeploymentRead,
)
from modelforge.services.deployments import (
    ActiveDeploymentNotFoundError,
    DeploymentAlreadyExistsError,
    DeploymentNotFoundError,
    InvalidDeploymentTransitionError,
    ModelVersionNotFoundError,
    create_deployment,
    get_deployment,
    list_deployments,
    promote_deployment,
    rollback_deployment,
    transition_deployment,
)

router = APIRouter(prefix="/deployments", tags=["deployments"])

DatabaseSession = Annotated[Session, Depends(get_db)]


def _not_found(deployment_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Deployment {deployment_id} was not found.",
    )


def _conflict(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=message,
    )


@router.post(
    "",
    response_model=DeploymentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_registered_deployment(
    payload: DeploymentCreate,
    session: DatabaseSession,
) -> Deployment:
    """Create a deployment for a registered model version."""

    try:
        return create_deployment(
            session,
            model_version_id=payload.model_version_id,
            environment=payload.environment,
        )
    except ModelVersionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model version {payload.model_version_id} was not found.",
        ) from exc
    except DeploymentAlreadyExistsError as exc:
        raise _conflict(
            "This model version already has a deployment "
            f"in environment '{payload.environment}'."
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[DeploymentRead])
def get_deployments(
    session: DatabaseSession,
    environment: Annotated[str | None, Query()] = None,
) -> list[Deployment]:
    """List deployments, optionally filtered by environment."""

    try:
        return list_deployments(session, environment=environment)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/{deployment_id}", response_model=DeploymentRead)
def get_registered_deployment(
    deployment_id: int,
    session: DatabaseSession,
) -> Deployment:
    """Retrieve one deployment."""

    try:
        return get_deployment(session, deployment_id)
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc


@router.post("/{deployment_id}/promote", response_model=DeploymentRead)
def promote_registered_deployment(
    deployment_id: int,
    session: DatabaseSession,
) -> Deployment:
    """Promote a DEPLOYING deployment to ACTIVE."""

    try:
        return promote_deployment(
            session,
            deployment_id=deployment_id,
        )
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except InvalidDeploymentTransitionError as exc:
        raise _conflict(str(exc)) from exc


@router.post("/{deployment_id}/fail", response_model=DeploymentRead)
def fail_registered_deployment(
    deployment_id: int,
    payload: DeploymentFailure,
    session: DatabaseSession,
) -> Deployment:
    """Mark a deployment FAILED with a diagnostic reason."""

    try:
        return transition_deployment(
            session,
            deployment_id=deployment_id,
            target_state=DeploymentState.FAILED,
            failure_reason=payload.reason,
        )
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except InvalidDeploymentTransitionError as exc:
        raise _conflict(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/{deployment_id}/rollback", response_model=DeploymentRead)
def rollback_registered_deployment(
    deployment_id: int,
    session: DatabaseSession,
) -> Deployment:
    """Restore a SUPERSEDED deployment to ACTIVE."""

    try:
        return rollback_deployment(
            session,
            deployment_id=deployment_id,
        )
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except (
        ActiveDeploymentNotFoundError,
        InvalidDeploymentTransitionError,
    ) as exc:
        raise _conflict(str(exc)) from exc