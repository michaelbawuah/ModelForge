"""Transactional workspace-scoped canary-release lifecycle management."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.models.deployment_target import DeploymentTarget
from modelforge.services.deployment_targets import DeploymentTargetNotFoundError
from modelforge.services.deployments import (
    DeploymentNotFoundError,
    InvalidDeploymentTransitionError,
)

DEFAULT_WORKSPACE_ID = 1


class CanaryAlreadyExistsError(Exception):
    pass


class CanaryNotConfiguredError(Exception):
    pass


def _validate_weight(weight: int) -> int:
    if isinstance(weight, bool) or not isinstance(weight, int):
        raise TypeError("Canary weight must be an integer.")
    if weight < 1 or weight > 99:
        raise ValueError("Canary weight must be between 1 and 99.")
    return weight


def _locked_deployment(
    session: Session,
    deployment_id: int,
    workspace_id: int,
) -> Deployment:
    deployment = session.scalar(
        select(Deployment)
        .where(
            Deployment.id == deployment_id,
            Deployment.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if deployment is None:
        raise DeploymentNotFoundError(deployment_id)
    return deployment


def _locked_target(
    session: Session,
    environment: str,
    workspace_id: int,
) -> DeploymentTarget:
    target = session.scalar(
        select(DeploymentTarget)
        .where(
            DeploymentTarget.workspace_id == workspace_id,
            DeploymentTarget.environment == environment,
        )
        .with_for_update()
    )
    if target is None:
        raise DeploymentTargetNotFoundError(environment)
    return target


def start_canary(
    session: Session,
    *,
    deployment_id: int,
    weight: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    weight = _validate_weight(weight)
    try:
        deployment = _locked_deployment(session, deployment_id, workspace_id)
        if DeploymentState(deployment.state) is not DeploymentState.DEPLOYING:
            raise InvalidDeploymentTransitionError(
                f"Deployment {deployment_id} must be DEPLOYING to start a canary."
            )

        target = _locked_target(session, deployment.environment, workspace_id)
        if target.canary_deployment_id is not None:
            raise CanaryAlreadyExistsError(deployment.environment)

        active = _locked_deployment(
            session,
            target.active_deployment_id,
            workspace_id,
        )
        if (
            active.environment != deployment.environment
            or DeploymentState(active.state) is not DeploymentState.ACTIVE
        ):
            raise InvalidDeploymentTransitionError(
                "Canary releases require a valid ACTIVE stable deployment."
            )

        deployment.state = DeploymentState.CANARY.value
        deployment.failure_reason = None
        target.canary_deployment_id = deployment.id
        target.canary_weight = weight
        session.commit()
        session.refresh(deployment)
        return deployment
    except Exception:
        session.rollback()
        raise


def update_canary_weight(
    session: Session,
    *,
    deployment_id: int,
    weight: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> DeploymentTarget:
    weight = _validate_weight(weight)
    try:
        deployment = _locked_deployment(session, deployment_id, workspace_id)
        target = _locked_target(session, deployment.environment, workspace_id)
        if (
            target.canary_deployment_id != deployment.id
            or DeploymentState(deployment.state) is not DeploymentState.CANARY
        ):
            raise CanaryNotConfiguredError(deployment_id)

        target.canary_weight = weight
        session.commit()
        session.refresh(target)
        return target
    except Exception:
        session.rollback()
        raise


def promote_canary(
    session: Session,
    *,
    deployment_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    try:
        canary = _locked_deployment(session, deployment_id, workspace_id)
        target = _locked_target(session, canary.environment, workspace_id)
        if (
            target.canary_deployment_id != canary.id
            or DeploymentState(canary.state) is not DeploymentState.CANARY
        ):
            raise CanaryNotConfiguredError(deployment_id)

        stable = _locked_deployment(
            session,
            target.active_deployment_id,
            workspace_id,
        )
        if DeploymentState(stable.state) is not DeploymentState.ACTIVE:
            raise InvalidDeploymentTransitionError(
                "Stable deployment must be ACTIVE before canary promotion."
            )

        stable.state = DeploymentState.SUPERSEDED.value
        canary.state = DeploymentState.ACTIVE.value
        canary.failure_reason = None
        target.active_deployment_id = canary.id
        target.canary_deployment_id = None
        target.canary_weight = 0
        session.commit()
        session.refresh(canary)
        return canary
    except Exception:
        session.rollback()
        raise


def abort_canary(
    session: Session,
    *,
    deployment_id: int,
    reason: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Deployment:
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("A reason is required when aborting a canary.")

    try:
        canary = _locked_deployment(session, deployment_id, workspace_id)
        target = _locked_target(session, canary.environment, workspace_id)
        if (
            target.canary_deployment_id != canary.id
            or DeploymentState(canary.state) is not DeploymentState.CANARY
        ):
            raise CanaryNotConfiguredError(deployment_id)

        canary.state = DeploymentState.FAILED.value
        canary.failure_reason = clean_reason
        target.canary_deployment_id = None
        target.canary_weight = 0
        session.commit()
        session.refresh(canary)
        return canary
    except Exception:
        session.rollback()
        raise
