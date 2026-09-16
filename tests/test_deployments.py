"""Tests for ModelForge deployment lifecycle rules."""

from unittest.mock import MagicMock

import pytest

from modelforge.models.deployment import Deployment, DeploymentState
from modelforge.services.deployments import (
    InvalidDeploymentTransitionError,
    transition_deployment,
)


def _session_with_deployment(
    state: DeploymentState,
) -> tuple[MagicMock, Deployment]:
    """Create a mocked session containing one deployment."""

    session = MagicMock()

    deployment = Deployment(
        id=1,
        model_version_id=10,
        environment="production",
        state=state.value,
    )

    session.get.return_value = deployment

    return session, deployment


def test_deploying_can_become_active() -> None:
    session, deployment = _session_with_deployment(
        DeploymentState.DEPLOYING
    )

    result = transition_deployment(
        session,
        deployment_id=1,
        target_state=DeploymentState.ACTIVE,
    )

    assert result.state == DeploymentState.ACTIVE.value
    assert deployment.failure_reason is None
    session.commit.assert_called_once()


def test_deploying_can_fail_with_reason() -> None:
    session, deployment = _session_with_deployment(
        DeploymentState.DEPLOYING
    )

    transition_deployment(
        session,
        deployment_id=1,
        target_state=DeploymentState.FAILED,
        failure_reason="Container failed its readiness probe.",
    )

    assert deployment.state == DeploymentState.FAILED.value
    assert (
        deployment.failure_reason
        == "Container failed its readiness probe."
    )


def test_failure_requires_reason() -> None:
    session, _ = _session_with_deployment(
        DeploymentState.DEPLOYING
    )

    with pytest.raises(ValueError, match="failure reason"):
        transition_deployment(
            session,
            deployment_id=1,
            target_state=DeploymentState.FAILED,
        )

    session.commit.assert_not_called()


def test_active_can_be_superseded() -> None:
    session, deployment = _session_with_deployment(
        DeploymentState.ACTIVE
    )

    transition_deployment(
        session,
        deployment_id=1,
        target_state=DeploymentState.SUPERSEDED,
    )

    assert deployment.state == DeploymentState.SUPERSEDED.value


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DeploymentState.DEPLOYING, DeploymentState.SUPERSEDED),
        (DeploymentState.ACTIVE, DeploymentState.DEPLOYING),
        (DeploymentState.FAILED, DeploymentState.ACTIVE),
        
        (DeploymentState.ACTIVE, DeploymentState.ACTIVE),
    ],
)
def test_invalid_state_transitions_are_rejected(
    current: DeploymentState,
    target: DeploymentState,
) -> None:
    session, deployment = _session_with_deployment(current)

    with pytest.raises(InvalidDeploymentTransitionError):
        transition_deployment(
            session,
            deployment_id=1,
            target_state=target,
        )

    assert deployment.state == current.value
    session.commit.assert_not_called()


def test_failure_reason_rejected_for_non_failure_transition() -> None:
    session, _ = _session_with_deployment(
        DeploymentState.DEPLOYING
    )

    with pytest.raises(ValueError, match="only be supplied"):
        transition_deployment(
            session,
            deployment_id=1,
            target_state=DeploymentState.ACTIVE,
            failure_reason="This should not be accepted.",
        )

    session.commit.assert_not_called()

def test_superseded_can_be_reactivated_for_rollback() -> None:
    session, deployment = _session_with_deployment(
        DeploymentState.SUPERSEDED
    )

    transition_deployment(
        session,
        deployment_id=1,
        target_state=DeploymentState.ACTIVE,
    )

    assert deployment.state == DeploymentState.ACTIVE.value