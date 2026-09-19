"""HTTP routes for ModelForge deployment lifecycle management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.deployment_target import DeploymentTarget
from modelforge.schemas.deployment_targets import DeploymentTargetRead
from modelforge.schemas.deployments import (
    CanaryAbort,
    CanaryStart,
    CanaryWeightUpdate,
    DeploymentCreate,
    DeploymentFailure,
    DeploymentRead,
)
from modelforge.services.auth import Principal, get_principal, require_role
from modelforge.services.canaries import (
    CanaryAlreadyExistsError,
    CanaryNotConfiguredError,
    abort_canary,
    promote_canary,
    start_canary,
    update_canary_weight,
)
from modelforge.services.deployment_targets import DeploymentTargetNotFoundError
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
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


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
    principal: CurrentPrincipal,
) -> Deployment:
    require_role(principal, "developer")
    try:
        return create_deployment(
            session,
            model_version_id=payload.model_version_id,
            environment=payload.environment,
            workspace_id=principal.workspace_id,
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
    principal: CurrentPrincipal,
    environment: Annotated[str | None, Query()] = None,
) -> list[Deployment]:
    try:
        return list_deployments(session, environment=environment, workspace_id=principal.workspace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/{deployment_id}", response_model=DeploymentRead)
def get_registered_deployment(
    deployment_id: int,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Deployment:
    try:
        return get_deployment(session, deployment_id, workspace_id=principal.workspace_id)
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc


@router.post("/{deployment_id}/promote", response_model=DeploymentRead)
def promote_registered_deployment(
    deployment_id: int,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Deployment:
    require_role(principal, "developer")
    try:
        return promote_deployment(session, deployment_id=deployment_id, workspace_id=principal.workspace_id)
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except InvalidDeploymentTransitionError as exc:
        raise _conflict(str(exc)) from exc


@router.post("/{deployment_id}/fail", response_model=DeploymentRead)
def fail_registered_deployment(
    deployment_id: int,
    payload: DeploymentFailure,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Deployment:
    require_role(principal, "developer")
    try:
        return transition_deployment(
            session,
            deployment_id=deployment_id,
            target_state=DeploymentState.FAILED,
            failure_reason=payload.reason,
            workspace_id=principal.workspace_id,
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
    principal: CurrentPrincipal,
) -> Deployment:
    require_role(principal, "developer")
    try:
        return rollback_deployment(session, deployment_id=deployment_id, workspace_id=principal.workspace_id)
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except (
        ActiveDeploymentNotFoundError,
        InvalidDeploymentTransitionError,
    ) as exc:
        raise _conflict(str(exc)) from exc


@router.post("/{deployment_id}/canary", response_model=DeploymentRead)
def start_registered_canary(
    deployment_id: int,
    payload: CanaryStart,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Deployment:
    require_role(principal, "developer")
    try:
        return start_canary(
            session,
            deployment_id=deployment_id,
            weight=payload.weight,
            workspace_id=principal.workspace_id,
        )
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except (
        CanaryAlreadyExistsError,
        DeploymentTargetNotFoundError,
        InvalidDeploymentTransitionError,
    ) as exc:
        raise _conflict(str(exc)) from exc


@router.patch(
    "/{deployment_id}/canary",
    response_model=DeploymentTargetRead,
)
def change_registered_canary_weight(
    deployment_id: int,
    payload: CanaryWeightUpdate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> DeploymentTarget:
    require_role(principal, "developer")
    try:
        return update_canary_weight(
            session,
            deployment_id=deployment_id,
            weight=payload.weight,
            workspace_id=principal.workspace_id,
        )
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except (
        CanaryNotConfiguredError,
        DeploymentTargetNotFoundError,
    ) as exc:
        raise _conflict(str(exc)) from exc


@router.post(
    "/{deployment_id}/canary/promote",
    response_model=DeploymentRead,
)
def promote_registered_canary(
    deployment_id: int,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Deployment:
    require_role(principal, "developer")
    try:
        return promote_canary(session, deployment_id=deployment_id, workspace_id=principal.workspace_id)
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except (
        CanaryNotConfiguredError,
        DeploymentTargetNotFoundError,
        InvalidDeploymentTransitionError,
    ) as exc:
        raise _conflict(str(exc)) from exc


@router.post(
    "/{deployment_id}/canary/abort",
    response_model=DeploymentRead,
)
def abort_registered_canary(
    deployment_id: int,
    payload: CanaryAbort,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Deployment:
    require_role(principal, "developer")
    try:
        return abort_canary(
            session,
            deployment_id=deployment_id,
            reason=payload.reason,
            workspace_id=principal.workspace_id,
        )
    except DeploymentNotFoundError as exc:
        raise _not_found(deployment_id) from exc
    except (
        CanaryNotConfiguredError,
        DeploymentTargetNotFoundError,
    ) as exc:
        raise _conflict(str(exc)) from exc
