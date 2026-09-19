"""Integration tests for ModelForge canary deployment lifecycle."""

from uuid import uuid4

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def _create_model_version() -> int:
    suffix = uuid4().hex[:10]

    model = client.post(
        "/models",
        json={
            "name": f"canary-model-{suffix}",
            "description": "Canary lifecycle integration test.",
        },
    )
    assert model.status_code == 201

    version = client.post(
        f"/models/{model.json()['id']}/versions",
        json={
            "version": "1.0.0",
            "framework": "future-framework",
            "artifact_uri": f"/tmp/modelforge/{suffix}/model.bin",
            "checksum": f"checksum-{suffix}",
        },
    )
    assert version.status_code == 201
    return version.json()["id"]


def _deployment(model_version_id: int, environment: str) -> dict:
    response = client.post(
        "/deployments",
        json={
            "model_version_id": model_version_id,
            "environment": environment,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_canary_can_be_started_reweighted_and_promoted() -> None:
    environment = f"canary-{uuid4().hex[:10]}"
    stable = _deployment(_create_model_version(), environment)
    candidate = _deployment(_create_model_version(), environment)

    assert client.post(
        f"/deployments/{stable['id']}/promote"
    ).status_code == 200

    start = client.post(
        f"/deployments/{candidate['id']}/canary",
        json={"weight": 25},
    )
    assert start.status_code == 200
    assert start.json()["state"] == "CANARY"

    target = client.get(f"/deployment-targets/{environment}")
    assert target.status_code == 200
    assert target.json()["active_deployment_id"] == stable["id"]
    assert target.json()["canary_deployment_id"] == candidate["id"]
    assert target.json()["canary_weight"] == 25

    reweight = client.patch(
        f"/deployments/{candidate['id']}/canary",
        json={"weight": 40},
    )
    assert reweight.status_code == 200
    assert reweight.json()["canary_weight"] == 40

    promote = client.post(
        f"/deployments/{candidate['id']}/canary/promote"
    )
    assert promote.status_code == 200
    assert promote.json()["state"] == "ACTIVE"

    stable_after = client.get(f"/deployments/{stable['id']}")
    assert stable_after.json()["state"] == "SUPERSEDED"

    target_after = client.get(f"/deployment-targets/{environment}")
    assert target_after.json()["active_deployment_id"] == candidate["id"]
    assert target_after.json()["canary_deployment_id"] is None
    assert target_after.json()["canary_weight"] == 0


def test_canary_abort_keeps_stable_deployment_active() -> None:
    environment = f"abort-{uuid4().hex[:10]}"
    stable = _deployment(_create_model_version(), environment)
    candidate = _deployment(_create_model_version(), environment)

    client.post(f"/deployments/{stable['id']}/promote")
    client.post(
        f"/deployments/{candidate['id']}/canary",
        json={"weight": 15},
    )

    abort = client.post(
        f"/deployments/{candidate['id']}/canary/abort",
        json={"reason": "Canary latency exceeded the release budget."},
    )

    assert abort.status_code == 200
    assert abort.json()["state"] == "FAILED"
    assert "latency" in abort.json()["failure_reason"]

    target = client.get(f"/deployment-targets/{environment}").json()
    assert target["active_deployment_id"] == stable["id"]
    assert target["canary_deployment_id"] is None
    assert target["canary_weight"] == 0


def test_canary_requires_existing_stable_deployment() -> None:
    environment = f"no-stable-{uuid4().hex[:10]}"
    candidate = _deployment(_create_model_version(), environment)

    response = client.post(
        f"/deployments/{candidate['id']}/canary",
        json={"weight": 10},
    )

    assert response.status_code == 409
