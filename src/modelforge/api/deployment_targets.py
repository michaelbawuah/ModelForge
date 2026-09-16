"""HTTP routes for authoritative deployment targets."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.deployment_target import DeploymentTarget
from modelforge.schemas.deployment_targets import DeploymentTargetRead
from modelforge.services.deployment_targets import (
    DeploymentTargetNotFoundError,
    get_deployment_target,
)

router = APIRouter(
    prefix="/deployment-targets",
    tags=["deployment-targets"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/{environment}",
    response_model=DeploymentTargetRead,
)
def get_environment_target(
    environment: str,
    session: DatabaseSession,
) -> DeploymentTarget:
    """Return the deployment currently selected for an environment."""

    try:
        return get_deployment_target(session, environment)
    except DeploymentTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Environment '{environment}' has no active deployment."
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc