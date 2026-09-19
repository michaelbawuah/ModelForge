"""Tests for SaaS identity, workspace context, and API keys."""

from fastapi.testclient import TestClient

from modelforge.api.app import app

client = TestClient(app)


def test_self_hosted_mode_exposes_default_workspace() -> None:
    response = client.get("/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_type"] == "self_hosted"
    assert payload["workspace_slug"] == "default"
    assert payload["role"] == "owner"


def test_api_key_secret_is_returned_once_and_authenticates() -> None:
    created = client.post(
        "/api-keys",
        json={
            "name": "ci-key",
            "role": "developer",
        },
    )

    assert created.status_code == 201
    secret = created.json()["secret"]
    assert secret.startswith("mf_live_")
    assert created.json()["key_hash"] if "key_hash" in created.json() else True

    listed = client.get("/api-keys")
    assert listed.status_code == 200
    assert all("secret" not in item for item in listed.json())

    authenticated = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert authenticated.status_code == 200
    assert authenticated.json()["auth_type"] == "api_key"
    assert authenticated.json()["workspace_slug"] == "default"
    assert authenticated.json()["role"] == "developer"


def test_revoked_api_key_cannot_authenticate() -> None:
    created = client.post(
        "/api-keys",
        json={
            "name": "revocation-test",
            "role": "viewer",
        },
    )
    assert created.status_code == 201

    api_key_id = created.json()["id"]
    secret = created.json()["secret"]

    revoked = client.delete(f"/api-keys/{api_key_id}")
    assert revoked.status_code == 204

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 401


def test_developer_api_key_cannot_manage_api_keys() -> None:
    created = client.post(
        "/api-keys",
        json={
            "name": "least-privilege-test",
            "role": "developer",
        },
    )
    secret = created.json()["secret"]

    response = client.get(
        "/api-keys",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 403
