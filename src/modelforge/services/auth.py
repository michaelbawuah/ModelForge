"""Request authentication and workspace resolution for ModelForge SaaS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.identity import User, Workspace
from modelforge.services.identity import (
    ApiKeyAuthenticationError,
    WorkspaceNotFoundError,
    authenticate_api_key,
    ensure_default_workspace,
    ensure_personal_workspace,
    has_minimum_role,
    resolve_user_workspace,
    upsert_user,
)

WORKSPACE_HEADER = "X-ModelForge-Workspace"


@dataclass(frozen=True)
class Principal:
    """Authenticated request identity and selected workspace."""

    auth_type: str
    workspace_id: int
    workspace_slug: str
    role: str
    user_id: int | None = None
    email: str | None = None
    display_name: str | None = None


def _auth_mode() -> str:
    mode = os.getenv("MODELFORGE_AUTH_MODE", "disabled").strip().lower()
    if mode not in {"disabled", "oidc"}:
        raise RuntimeError("MODELFORGE_AUTH_MODE must be 'disabled' or 'oidc'.")
    return mode


def _bearer_token(request: Request) -> str | None:
    value = request.headers.get("Authorization")
    if not value:
        return None

    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _oidc_claims(token: str) -> dict[str, Any]:
    """Verify an OIDC JWT against the configured issuer/JWKS."""

    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError(
            "OIDC mode requires the PyJWT crypto dependency."
        ) from exc

    issuer = os.getenv("MODELFORGE_OIDC_ISSUER", "").strip()
    audience = os.getenv("MODELFORGE_OIDC_AUDIENCE", "").strip()
    jwks_url = os.getenv("MODELFORGE_OIDC_JWKS_URL", "").strip()

    if not issuer or not audience or not jwks_url:
        raise RuntimeError(
            "OIDC mode requires MODELFORGE_OIDC_ISSUER, "
            "MODELFORGE_OIDC_AUDIENCE, and MODELFORGE_OIDC_JWKS_URL."
        )

    signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=audience,
        issuer=issuer,
    )


def _principal_for_api_key(session: Session, raw_key: str) -> Principal:
    try:
        api_key = authenticate_api_key(session, raw_key)
    except ApiKeyAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked ModelForge API key.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    workspace = session.get(Workspace, api_key.workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key references a missing workspace.",
        )

    return Principal(
        auth_type="api_key",
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        role=api_key.role,
    )


def _principal_for_oidc(
    request: Request,
    session: Session,
    token: str,
) -> Principal:
    try:
        claims = _oidc_claims(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OIDC access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token is missing a subject.",
        )

    user = upsert_user(
        session,
        external_subject=subject,
        email=claims.get("email"),
        display_name=claims.get("name") or claims.get("preferred_username"),
    )
    ensure_personal_workspace(session, user)

    try:
        workspace, role = resolve_user_workspace(
            session,
            user_id=user.id,
            selector=request.headers.get(WORKSPACE_HEADER),
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to the requested workspace.",
        ) from exc

    return Principal(
        auth_type="oidc",
        user_id=user.id,
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        role=role,
        email=user.email,
        display_name=user.display_name,
    )


def get_principal(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> Principal:
    """Authenticate API key/OIDC callers or select self-hosted default workspace."""

    token = _bearer_token(request)

    if token and token.startswith("mf_live_"):
        return _principal_for_api_key(session, token)

    if _auth_mode() == "disabled":
        workspace = ensure_default_workspace(session)
        return Principal(
            auth_type="self_hosted",
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            role="owner",
        )

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _principal_for_oidc(request, session, token)


def require_role(principal: Principal, minimum_role: str) -> None:
    """Enforce workspace role ordering."""

    if not has_minimum_role(principal.role, minimum_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This operation requires the '{minimum_role}' role.",
        )
