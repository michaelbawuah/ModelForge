"""HTTP routes for workspace-scoped authoritative deployment targets."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.deployment_target import DeploymentTarget
from modelforge.schemas.deployment_targets import DeploymentTargetRead
from modelforge.services.auth import Principal, get_principal
from modelforge.services.deployment_targets import (
    DeploymentTargetNotFoundError,
    get_deployment_target,
)

router = APIRouter(prefix="/deployment-targets", tags=["deployment-targets"])
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


@router.get("/{environment}", response_model=DeploymentTargetRead)
def get_environment_target(
    environment: str,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> DeploymentTarget:
    try:
        return get_deployment_target(
            session,
            environment,
            workspace_id=principal.workspace_id,
        )
    except DeploymentTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment '{environment}' has no active deployment.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
