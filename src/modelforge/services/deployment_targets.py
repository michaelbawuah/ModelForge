"""Authoritative workspace-scoped environment-target management."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.deployment_target import DeploymentTarget

DEFAULT_WORKSPACE_ID = 1


class DeploymentTargetNotFoundError(Exception):
    pass


def get_deployment_target(
    session: Session,
    environment: str,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> DeploymentTarget:
    normalized = environment.strip().lower()
    if not normalized:
        raise ValueError("environment cannot be empty.")

    target = session.scalar(
        select(DeploymentTarget).where(
            DeploymentTarget.workspace_id == workspace_id,
            DeploymentTarget.environment == normalized,
        )
    )
    if target is None:
        raise DeploymentTargetNotFoundError(normalized)
    return target


def set_deployment_target(
    session: Session,
    *,
    environment: str,
    deployment_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> DeploymentTarget:
    normalized = environment.strip().lower()

    deployment = session.scalar(
        select(Deployment).where(
            Deployment.id == deployment_id,
            Deployment.workspace_id == workspace_id,
        )
    )
    if deployment is None:
        raise ValueError(f"Deployment {deployment_id} does not exist.")

    if deployment.environment != normalized:
        raise ValueError("Deployment environment does not match deployment target.")
    if deployment.state != DeploymentState.ACTIVE.value:
        raise ValueError("Only an ACTIVE deployment may become an environment target.")

    target = session.scalar(
        select(DeploymentTarget)
        .where(
            DeploymentTarget.workspace_id == workspace_id,
            DeploymentTarget.environment == normalized,
        )
        .with_for_update()
    )

    if target is None:
        target = DeploymentTarget(
            workspace_id=workspace_id,
            environment=normalized,
            active_deployment_id=deployment_id,
        )
        session.add(target)
    else:
        target.active_deployment_id = deployment_id

    return target
