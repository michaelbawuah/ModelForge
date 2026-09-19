"""Tests for browser OIDC sessions, PKCE, and CSRF protection."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi.testclient import TestClient

from modelforge.api.app import app
from modelforge.db.session import SessionLocal
from modelforge.services.identity import (
    create_browser_session,
    ensure_personal_workspace,
    upsert_user,
)

client = TestClient(app)


def test_browser_login_redirect_uses_pkce(monkeypatch) -> None:
    monkeypatch.setenv("MODELFORGE_AUTH_MODE", "oidc")
    monkeypatch.setenv(
        "MODELFORGE_OIDC_AUTHORIZATION_URL",
        "https://identity.example/authorize",
    )
    monkeypatch.setenv("MODELFORGE_OIDC_CLIENT_ID", "modelforge-web")
    monkeypatch.setenv(
        "MODELFORGE_OIDC_REDIRECT_URI",
        "https://app.example/auth/callback",
    )

    response = client.get(
        "/auth/login?next=/dashboard",
        follow_redirects=False,
    )

    assert response.status_code == 302
    parsed = urlsplit(response.headers["location"])
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "identity.example"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["modelforge-web"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["state"][0]) >= 32
    assert len(query["nonce"][0]) >= 32
    assert len(query["code_challenge"][0]) >= 40


def test_browser_session_auth_and_csrf(monkeypatch) -> None:
    monkeypatch.setenv("MODELFORGE_AUTH_MODE", "oidc")
    suffix = uuid4().hex

    with SessionLocal() as session:
        user = upsert_user(
            session,
            external_subject=f"browser-{suffix}",
            email=f"{suffix}@example.test",
            display_name="Browser User",
        )
        workspace = ensure_personal_workspace(session, user)
        _, raw_session, csrf_secret = create_browser_session(
            session,
            user_id=user.id,
            ttl=timedelta(hours=1),
        )
        workspace_slug = workspace.slug

    browser = TestClient(app)
    browser.cookies.set("mf_session", raw_session)
    browser.cookies.set("mf_csrf", csrf_secret)

    identity = browser.get("/auth/me")
    assert identity.status_code == 200
    assert identity.json()["auth_type"] == "browser"
    assert identity.json()["workspace_slug"] == workspace_slug
    assert identity.json()["display_name"] == "Browser User"

    rejected = browser.post(
        "/api-keys",
        json={"name": "browser-key", "role": "developer"},
    )
    assert rejected.status_code == 403

    created = browser.post(
        "/api-keys",
        headers={"X-ModelForge-CSRF": csrf_secret},
        json={"name": "browser-key", "role": "developer"},
    )
    assert created.status_code == 201
    assert created.json()["secret"].startswith("mf_live_")


def test_browser_logout_revokes_session(monkeypatch) -> None:
    monkeypatch.setenv("MODELFORGE_AUTH_MODE", "oidc")
    suffix = uuid4().hex

    with SessionLocal() as session:
        user = upsert_user(
            session,
            external_subject=f"logout-{suffix}",
            email=None,
            display_name="Logout User",
        )
        ensure_personal_workspace(session, user)
        _, raw_session, csrf_secret = create_browser_session(
            session,
            user_id=user.id,
            ttl=timedelta(hours=1),
        )

    browser = TestClient(app)
    browser.cookies.set("mf_session", raw_session)
    browser.cookies.set("mf_csrf", csrf_secret)

    rejected = browser.post("/auth/logout")
    assert rejected.status_code == 403

    response = browser.post(
        "/auth/logout",
        headers={"X-ModelForge-CSRF": csrf_secret},
    )
    assert response.status_code == 204

    identity = browser.get("/auth/me")
    assert identity.status_code == 401
