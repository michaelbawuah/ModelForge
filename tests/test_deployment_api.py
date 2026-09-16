"""Integration tests for the ModelForge deployment API."""

from uuid import uuid4

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def _create_model_version() -> int:
    """Create an isolated model and model version for deployment tests."""

    suffix = uuid4().hex[:10]

    model_response = client.post(
        "/models",
        json={
            "name": f"deployment-test-{suffix}",
            "description": "Deployment lifecycle integration test.",
        },
    )

    assert model_response.status_code == 201
    model_id = model_response.json()["id"]

    version_response = client.post(
        f"/models/{model_id}/versions",
        json={
            "version": "1.0.0",
            "framework": "fluxion",
            "artifact_uri": f"/tmp/modelforge/{suffix}/model.bin",
            "checksum": f"checksum-{suffix}",
        },
    )

    assert version_response.status_code == 201

    return version_response.json()["id"]


def _create_deployment(
    model_version_id: int,
    environment: str,
) -> dict:
    response = client.post(
        "/deployments",
        json={
            "model_version_id": model_version_id,
            "environment": environment,
        },
    )

    assert response.status_code == 201
    return response.json()


def test_create_and_promote_deployment() -> None:
    model_version_id = _create_model_version()

    deployment = _create_deployment(
        model_version_id,
        "staging",
    )

    assert deployment["state"] == "DEPLOYING"

    response = client.post(
        f"/deployments/{deployment['id']}/promote"
    )

    assert response.status_code == 200
    assert response.json()["state"] == "ACTIVE"


def test_second_promotion_supersedes_current_active() -> None:
    first_version = _create_model_version()
    second_version = _create_model_version()

    first = _create_deployment(first_version, "production")
    second = _create_deployment(second_version, "production")

    assert client.post(
        f"/deployments/{first['id']}/promote"
    ).status_code == 200

    response = client.post(
        f"/deployments/{second['id']}/promote"
    )

    assert response.status_code == 200
    assert response.json()["state"] == "ACTIVE"

    first_after = client.get(
        f"/deployments/{first['id']}"
    ).json()

    assert first_after["state"] == "SUPERSEDED"


def test_rollback_restores_superseded_deployment() -> None:
    first_version = _create_model_version()
    second_version = _create_model_version()

    first = _create_deployment(first_version, "production")
    second = _create_deployment(second_version, "production")

    client.post(f"/deployments/{first['id']}/promote")
    client.post(f"/deployments/{second['id']}/promote")

    rollback = client.post(
        f"/deployments/{first['id']}/rollback"
    )

    assert rollback.status_code == 200
    assert rollback.json()["state"] == "ACTIVE"

    second_after = client.get(
        f"/deployments/{second['id']}"
    ).json()

    assert second_after["state"] == "SUPERSEDED"


def test_failed_deployment_records_reason() -> None:
    model_version_id = _create_model_version()
    deployment = _create_deployment(
        model_version_id,
        "staging",
    )

    response = client.post(
        f"/deployments/{deployment['id']}/fail",
        json={
            "reason": "Readiness probe failed.",
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "FAILED"
    assert (
        response.json()["failure_reason"]
        == "Readiness probe failed."
    )


def test_invalid_promotion_returns_conflict() -> None:
    model_version_id = _create_model_version()
    deployment = _create_deployment(
        model_version_id,
        "staging",
    )

    client.post(
        f"/deployments/{deployment['id']}/promote"
    )

    response = client.post(
        f"/deployments/{deployment['id']}/promote"
    )

    assert response.status_code == 409


def test_unknown_model_version_returns_not_found() -> None:
    response = client.post(
        "/deployments",
        json={
            "model_version_id": 999999999,
            "environment": "production",
        },
    )

    assert response.status_code == 404

def test_promotion_updates_authoritative_environment_target() -> None:
    model_version_id = _create_model_version()
    deployment = _create_deployment(
        model_version_id,
        "production",
    )

    promotion = client.post(
        f"/deployments/{deployment['id']}/promote"
    )

    assert promotion.status_code == 200

    target = client.get(
        "/deployment-targets/production"
    )

    assert target.status_code == 200
    assert (
        target.json()["active_deployment_id"]
        == deployment["id"]
    )


def test_new_promotion_replaces_environment_target() -> None:
    first_version = _create_model_version()
    second_version = _create_model_version()

    first = _create_deployment(first_version, "staging")
    second = _create_deployment(second_version, "staging")

    client.post(f"/deployments/{first['id']}/promote")
    client.post(f"/deployments/{second['id']}/promote")

    target = client.get("/deployment-targets/staging")

    assert target.status_code == 200
    assert target.json()["active_deployment_id"] == second["id"]


def test_rollback_restores_previous_environment_target() -> None:
    first_version = _create_model_version()
    second_version = _create_model_version()

    first = _create_deployment(first_version, "rollback-test")
    second = _create_deployment(second_version, "rollback-test")

    client.post(f"/deployments/{first['id']}/promote")
    client.post(f"/deployments/{second['id']}/promote")

    rollback = client.post(
        f"/deployments/{first['id']}/rollback"
    )

    assert rollback.status_code == 200

    target = client.get(
        "/deployment-targets/rollback-test"
    )

    assert target.status_code == 200
    assert target.json()["active_deployment_id"] == first["id"]


def test_unknown_environment_target_returns_not_found() -> None:
    response = client.get(
        "/deployment-targets/environment-that-does-not-exist"
    )

    assert response.status_code == 404