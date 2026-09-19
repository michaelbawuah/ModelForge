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
    BrowserSessionAuthenticationError,
    WorkspaceNotFoundError,
    authenticate_api_key,
    authenticate_browser_session,
    ensure_default_workspace,
    ensure_personal_workspace,
    has_minimum_role,
    resolve_user_workspace,
    upsert_user,
    verify_browser_csrf,
)

WORKSPACE_HEADER = "X-ModelForge-Workspace"
SESSION_COOKIE = "mf_session"
CSRF_COOKIE = "mf_csrf"
CSRF_HEADER = "X-ModelForge-CSRF"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


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


def auth_mode() -> str:
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


def verify_oidc_token(
    token: str,
    *,
    audience: str | None = None,
) -> dict[str, Any]:
    """Verify an OIDC JWT against the configured issuer/JWKS."""

    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError(
            "OIDC mode requires the PyJWT crypto dependency."
        ) from exc

    issuer = os.getenv("MODELFORGE_OIDC_ISSUER", "").strip()
    resolved_audience = (
        audience
        or os.getenv("MODELFORGE_OIDC_AUDIENCE", "").strip()
    )
    jwks_url = os.getenv("MODELFORGE_OIDC_JWKS_URL", "").strip()

    if not issuer or not resolved_audience or not jwks_url:
        raise RuntimeError(
            "OIDC verification requires issuer, audience, and JWKS URL."
        )

    signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=resolved_audience,
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


def _principal_for_user(
    request: Request,
    session: Session,
    user: User,
    *,
    auth_type: str,
) -> Principal:
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
        auth_type=auth_type,
        user_id=user.id,
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        role=role,
        email=user.email,
        display_name=user.display_name,
    )


def _principal_for_oidc(
    request: Request,
    session: Session,
    token: str,
) -> Principal:
    try:
        claims = verify_oidc_token(token)
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
    return _principal_for_user(
        request,
        session,
        user,
        auth_type="oidc",
    )


def _principal_for_browser_session(
    request: Request,
    session: Session,
    raw_session: str,
) -> Principal:
    try:
        browser_session = authenticate_browser_session(session, raw_session)
    except BrowserSessionAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Browser session is invalid or expired.",
        ) from exc

    if request.method.upper() in UNSAFE_METHODS and not verify_browser_csrf(
        browser_session,
        cookie_secret=request.cookies.get(CSRF_COOKIE),
        header_secret=request.headers.get(CSRF_HEADER),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed.",
        )

    user = session.get(User, browser_session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Browser session references a missing user.",
        )

    return _principal_for_user(
        request,
        session,
        user,
        auth_type="browser",
    )


def get_principal(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> Principal:
    """Authenticate API key, OIDC, browser-session, or self-hosted callers."""

    token = _bearer_token(request)

    if token and token.startswith("mf_live_"):
        return _principal_for_api_key(session, token)

    if auth_mode() == "disabled":
        workspace = ensure_default_workspace(session)
        return Principal(
            auth_type="self_hosted",
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            role="owner",
        )

    if token is not None:
        return _principal_for_oidc(request, session, token)

    raw_session = request.cookies.get(SESSION_COOKIE)
    if raw_session:
        return _principal_for_browser_session(request, session, raw_session)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(principal: Principal, minimum_role: str) -> None:
    """Enforce workspace role ordering."""

    if not has_minimum_role(principal.role, minimum_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This operation requires the '{minimum_role}' role.",
        )
