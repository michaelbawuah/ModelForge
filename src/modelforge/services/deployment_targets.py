"""Authoritative environment-target management for ModelForge."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.deployment_target import DeploymentTarget


class DeploymentTargetNotFoundError(Exception):
    """Raised when an environment has no active deployment target."""


def get_deployment_target(
    session: Session,
    environment: str,
) -> DeploymentTarget:
    """Return the authoritative deployment target for an environment."""

    normalized = environment.strip().lower()

    if not normalized:
        raise ValueError("environment cannot be empty.")

    target = session.get(DeploymentTarget, normalized)

    if target is None:
        raise DeploymentTargetNotFoundError(normalized)

    return target


def set_deployment_target(
    session: Session,
    *,
    environment: str,
    deployment_id: int,
) -> DeploymentTarget:
    """Set an environment's active deployment inside the current transaction."""

    normalized = environment.strip().lower()

    deployment = session.get(Deployment, deployment_id)

    if deployment is None:
        raise ValueError(f"Deployment {deployment_id} does not exist.")

    if deployment.environment != normalized:
        raise ValueError(
            "Deployment environment does not match deployment target."
        )

    if deployment.state != DeploymentState.ACTIVE.value:
        raise ValueError(
            "Only an ACTIVE deployment may become an environment target."
        )

    statement = (
        select(DeploymentTarget)
        .where(DeploymentTarget.environment == normalized)
        .with_for_update()
    )
    target = session.scalar(statement)

    if target is None:
        target = DeploymentTarget(
            environment=normalized,
            active_deployment_id=deployment_id,
        )
        session.add(target)
    else:
        target.active_deployment_id = deployment_id

    return target