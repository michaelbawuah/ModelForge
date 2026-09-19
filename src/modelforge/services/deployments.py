"""Workspace-scoped deployment lifecycle orchestration."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.registry import Model, ModelVersion
from modelforge.services.deployment_targets import set_deployment_target

DEFAULT_WORKSPACE_ID = 1


class DeploymentNotFoundError(Exception):
    pass


class ModelVersionNotFoundError(Exception):
    pass


class DeploymentAlreadyExistsError(Exception):
    pass


class InvalidDeploymentTransitionError(Exception):
    pass


class ActiveDeploymentNotFoundError(Exception):
    pass


VALID_TRANSITIONS: dict[DeploymentState, frozenset[DeploymentState]] = {
    DeploymentState.DEPLOYING: frozenset(
        {DeploymentState.CANARY, DeploymentState.ACTIVE, DeploymentState.FAILED}
    ),
    DeploymentState.CANARY: frozenset(
        {
            DeploymentState.ACTIVE,
            DeploymentState.FAILED,
            DeploymentState.SUPERSEDED,
        }
    ),
    DeploymentState.ACTIVE: frozenset(
        {DeploymentState.SUPERSEDED, DeploymentState.FAILED}
    ),
    DeploymentState.FAILED: frozenset(),
    DeploymentState.SUPERSEDED: frozenset({DeploymentState.ACTIVE}),
}


def _normalize_environment(environment: str) -> str:
    normalized = environment.strip().lower()
    if not normalized:
        raise ValueError("environment cannot be empty.")
    return normalized


def _get_model_version(
    session: Session,
    model_version_id: int,
    workspace_id: int,
) -> ModelVersion:
    model_version = session.scalar(
        select(ModelVersion)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(
            ModelVersion.id == model_version_id,
            Model.workspace_id == workspace_id,
        )
    )
    if model_version is None:
        raise ModelVersionNotFoundError(model_version_id)
    return model_version


def create_deployment(
    session: Session,
    *,
    model_version_id: int,
    environment: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    _get_model_version(session, model_version_id, workspace_id)
    normalized = _normalize_environment(environment)

    deployment = Deployment(
        workspace_id=workspace_id,
        model_version_id=model_version_id,
        environment=normalized,
        state=DeploymentState.DEPLOYING.value,
    )
    session.add(deployment)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DeploymentAlreadyExistsError(
            (workspace_id, model_version_id, normalized)
        ) from exc

    session.refresh(deployment)
    return deployment


def get_deployment(
    session: Session,
    deployment_id: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    deployment = session.get(Deployment, deployment_id)
    if deployment is None or deployment.workspace_id != workspace_id:
        raise DeploymentNotFoundError(deployment_id)
    return deployment


def list_deployments(
    session: Session,
    *,
    environment: str | None = None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> list[Deployment]:
    statement = select(Deployment).where(Deployment.workspace_id == workspace_id)
    if environment is not None:
        statement = statement.where(
            Deployment.environment == _normalize_environment(environment)
        )
    return list(session.scalars(statement.order_by(Deployment.id)))


def transition_deployment(
    session: Session,
    *,
    deployment_id: int,
    target_state: DeploymentState,
    failure_reason: str | None = None,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    deployment = get_deployment(
        session,
        deployment_id,
        workspace_id=workspace_id,
    )
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
        raise ValueError("failure_reason may only be supplied for a FAILED deployment.")
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
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    try:
        target = session.scalar(
            select(Deployment)
            .where(
                Deployment.id == deployment_id,
                Deployment.workspace_id == workspace_id,
            )
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
                Deployment.workspace_id == workspace_id,
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
            workspace_id=workspace_id,
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
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    try:
        target = session.scalar(
            select(Deployment)
            .where(
                Deployment.id == deployment_id,
                Deployment.workspace_id == workspace_id,
            )
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
                Deployment.workspace_id == workspace_id,
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
            workspace_id=workspace_id,
            environment=target.environment,
            deployment_id=target.id,
        )
        session.commit()
        session.refresh(target)
        return target
    except Exception:
        session.rollback()
        raise
