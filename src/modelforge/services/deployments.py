"""Deployment lifecycle orchestration for ModelForge."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.registry import ModelVersion
from modelforge.services.deployment_targets import set_deployment_target


class DeploymentNotFoundError(Exception):
    """Raised when a deployment does not exist."""


class ModelVersionNotFoundError(Exception):
    """Raised when a model version does not exist."""


class DeploymentAlreadyExistsError(Exception):
    """Raised when a version already has a deployment in an environment."""


class InvalidDeploymentTransitionError(Exception):
    """Raised when a deployment attempts an illegal lifecycle transition."""


class ActiveDeploymentNotFoundError(Exception):
    """Raised when an environment has no active deployment to replace."""


VALID_TRANSITIONS: dict[DeploymentState, frozenset[DeploymentState]] = {
    DeploymentState.DEPLOYING: frozenset(
        {
            DeploymentState.CANARY,
            DeploymentState.ACTIVE,
            DeploymentState.FAILED,
        }
    ),
    DeploymentState.CANARY: frozenset(
        {
            DeploymentState.ACTIVE,
            DeploymentState.FAILED,
            DeploymentState.SUPERSEDED,
        }
    ),
    DeploymentState.ACTIVE: frozenset(
        {
            DeploymentState.SUPERSEDED,
            DeploymentState.FAILED,
        }
    ),
    DeploymentState.FAILED: frozenset(),
    DeploymentState.SUPERSEDED: frozenset(
        {
            DeploymentState.ACTIVE,
        }
    ),
}


def _normalize_environment(environment: str) -> str:
    """Normalize environment names used as deployment identities."""

    normalized = environment.strip().lower()
    if not normalized:
        raise ValueError("environment cannot be empty.")
    return normalized


def create_deployment(
    session: Session,
    *,
    model_version_id: int,
    environment: str,
) -> Deployment:
    """Create a deployment in the DEPLOYING state."""

    model_version = session.get(ModelVersion, model_version_id)
    if model_version is None:
        raise ModelVersionNotFoundError(model_version_id)

    normalized_environment = _normalize_environment(environment)

    deployment = Deployment(
        model_version_id=model_version_id,
        environment=normalized_environment,
        state=DeploymentState.DEPLOYING.value,
    )
    session.add(deployment)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DeploymentAlreadyExistsError(
            (model_version_id, normalized_environment)
        ) from exc

    session.refresh(deployment)
    return deployment


def get_deployment(session: Session, deployment_id: int) -> Deployment:
    """Return a deployment or raise when it does not exist."""

    deployment = session.get(Deployment, deployment_id)
    if deployment is None:
        raise DeploymentNotFoundError(deployment_id)
    return deployment


def list_deployments(
    session: Session,
    *,
    environment: str | None = None,
) -> list[Deployment]:
    """Return deployments in deterministic ID order."""

    statement = select(Deployment)

    if environment is not None:
        statement = statement.where(
            Deployment.environment == _normalize_environment(environment)
        )

    statement = statement.order_by(Deployment.id)
    return list(session.scalars(statement))


def transition_deployment(
    session: Session,
    *,
    deployment_id: int,
    target_state: DeploymentState,
    failure_reason: str | None = None,
) -> Deployment:
    """Apply one validated deployment lifecycle transition."""

    deployment = get_deployment(session, deployment_id)
    current_state = DeploymentState(deployment.state)

    if target_state not in VALID_TRANSITIONS[current_state]:
        raise InvalidDeploymentTransitionError(
            f"Cannot transition deployment {deployment_id} "
            f"from {current_state.value} to {target_state.value}."
        )

    if target_state is DeploymentState.FAILED:
        if failure_reason is None or not failure_reason.strip():
            raise ValueError(
                "A failure reason is required when marking a deployment FAILED."
            )
        deployment.failure_reason = failure_reason.strip()
    elif failure_reason is not None:
        raise ValueError(
            "failure_reason may only be supplied for a FAILED deployment."
        )
    else:
        deployment.failure_reason = None

    deployment.state = target_state.value
    session.commit()
    session.refresh(deployment)
    return deployment


def promote_deployment(
    session: Session,
    *,
    deployment_id: int,
) -> Deployment:
    """Atomically make a DEPLOYING deployment active in its environment."""

    try:
        target = session.scalar(
            select(Deployment)
            .where(Deployment.id == deployment_id)
            .with_for_update()
        )

        if target is None:
            raise DeploymentNotFoundError(deployment_id)

        if DeploymentState(target.state) is not DeploymentState.DEPLOYING:
            raise InvalidDeploymentTransitionError(
                f"Deployment {deployment_id} must be DEPLOYING before promotion."
            )

        current_active = session.scalar(
            select(Deployment)
            .where(
                Deployment.environment == target.environment,
                Deployment.state == DeploymentState.ACTIVE.value,
                Deployment.id != target.id,
            )
            .with_for_update()
        )

        if current_active is not None:
            current_active.state = DeploymentState.SUPERSEDED.value

        target.state = DeploymentState.ACTIVE.value
        target.failure_reason = None
        session.flush()

        set_deployment_target(
            session,
            environment=target.environment,
            deployment_id=target.id,
        )

        session.commit()
        session.refresh(target)
        return target

    except Exception:
        session.rollback()
        raise


def rollback_deployment(
    session: Session,
    *,
    deployment_id: int,
) -> Deployment:
    """Atomically restore a superseded deployment to ACTIVE."""

    try:
        target = session.scalar(
            select(Deployment)
            .where(Deployment.id == deployment_id)
            .with_for_update()
        )

        if target is None:
            raise DeploymentNotFoundError(deployment_id)

        if DeploymentState(target.state) is not DeploymentState.SUPERSEDED:
            raise InvalidDeploymentTransitionError(
                f"Deployment {deployment_id} must be SUPERSEDED before rollback."
            )

        current_active = session.scalar(
            select(Deployment)
            .where(
                Deployment.environment == target.environment,
                Deployment.state == DeploymentState.ACTIVE.value,
                Deployment.id != target.id,
            )
            .with_for_update()
        )

        if current_active is None:
            raise ActiveDeploymentNotFoundError(target.environment)

        current_active.state = DeploymentState.SUPERSEDED.value
        target.state = DeploymentState.ACTIVE.value
        target.failure_reason = None
        session.flush()

        set_deployment_target(
            session,
            environment=target.environment,
            deployment_id=target.id,
        )

        session.commit()
        session.refresh(target)
        return target

    except Exception:
        session.rollback()
        raise
