"""Tenant-isolation tests for workspace-scoped resource access."""

from uuid import uuid4

from fastapi.testclient import TestClient

from modelforge.api.app import app
from modelforge.db.session import SessionLocal
from modelforge.services.identity import create_api_key, create_workspace
from modelforge.services.identity import upsert_user

client = TestClient(app)


def _workspace_key(slug: str) -> str:
    with SessionLocal() as session:
        user = upsert_user(
            session,
            external_subject=f"test-{uuid4().hex}",
            email=None,
            display_name="Isolation Test",
        )
        workspace = create_workspace(
            session,
            name=slug,
            slug=slug,
            owner_user_id=user.id,
        )
        _, secret = create_api_key(
            session,
            workspace_id=workspace.id,
            name="test-key",
            role="developer",
        )
        return secret


def test_identical_model_names_are_isolated_between_workspaces() -> None:
    suffix = uuid4().hex[:8]
    key_a = _workspace_key(f"tenant-a-{suffix}")
    key_b = _workspace_key(f"tenant-b-{suffix}")
    headers_a = {"Authorization": f"Bearer {key_a}"}
    headers_b = {"Authorization": f"Bearer {key_b}"}

    model_a = client.post(
        "/models",
        headers=headers_a,
        json={"name": "shared-name", "description": "A"},
    )
    model_b = client.post(
        "/models",
        headers=headers_b,
        json={"name": "shared-name", "description": "B"},
    )

    assert model_a.status_code == 201
    assert model_b.status_code == 201
    assert model_a.json()["workspace_id"] != model_b.json()["workspace_id"]

    invisible = client.get(
        f"/models/{model_a.json()['id']}",
        headers=headers_b,
    )
    assert invisible.status_code == 404

    listed_b = client.get("/models", headers=headers_b)
    assert listed_b.status_code == 200
    assert [item["id"] for item in listed_b.json()] == [model_b.json()["id"]]


def test_api_key_cannot_deploy_another_workspaces_model_version() -> None:
    suffix = uuid4().hex[:8]
    key_a = _workspace_key(f"deploy-a-{suffix}")
    key_b = _workspace_key(f"deploy-b-{suffix}")
    headers_a = {"Authorization": f"Bearer {key_a}"}
    headers_b = {"Authorization": f"Bearer {key_b}"}

    model = client.post(
        "/models",
        headers=headers_a,
        json={"name": f"private-{suffix}", "description": None},
    ).json()
    version = client.post(
        f"/models/{model['id']}/versions",
        headers=headers_a,
        json={
            "version": "1.0.0",
            "framework": "go-linear",
            "artifact_uri": "external://private/model",
            "checksum": "private-checksum",
        },
    ).json()

    response = client.post(
        "/deployments",
        headers=headers_b,
        json={
            "model_version_id": version["id"],
            "environment": "production",
        },
    )
    assert response.status_code == 404
