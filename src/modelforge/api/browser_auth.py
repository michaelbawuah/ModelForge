"""OIDC Authorization Code + PKCE browser authentication."""

from __future__ import annotations

import base64
import hashlib
import os
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.services.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    auth_mode,
    verify_oidc_token,
)
from modelforge.services.identity import (
    LoginChallengeError,
    create_browser_session,
    create_login_challenge,
    ensure_personal_workspace,
    revoke_browser_session,
    upsert_user,
    consume_login_challenge,
)

router = APIRouter(prefix="/auth", tags=["browser-auth"])

DEFAULT_NEXT_PATH = "/dashboard"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for browser OIDC login.")
    return value


def _safe_next_path(value: str | None) -> str:
    if not value:
        return DEFAULT_NEXT_PATH

    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/"):
        return DEFAULT_NEXT_PATH
    return value


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _cookie_secure() -> bool:
    return (
        os.getenv("MODELFORGE_SESSION_COOKIE_SECURE", "true")
        .strip()
        .lower()
        not in {"0", "false", "no"}
    )


def _session_ttl() -> timedelta:
    raw = os.getenv("MODELFORGE_SESSION_TTL_HOURS", "12")
    try:
        hours = int(raw)
    except ValueError as exc:
        raise RuntimeError("MODELFORGE_SESSION_TTL_HOURS must be an integer.") from exc

    if hours < 1 or hours > 168:
        raise RuntimeError("MODELFORGE_SESSION_TTL_HOURS must be between 1 and 168.")
    return timedelta(hours=hours)


@router.get("/config")
def browser_auth_config() -> dict[str, object]:
    """Expose non-secret auth UX configuration."""

    enabled = auth_mode() == "oidc"
    return {
        "mode": auth_mode(),
        "browser_login_enabled": enabled,
        "login_url": "/auth/login" if enabled else None,
    }


@router.get("/login", response_class=RedirectResponse)
def browser_login(
    session: Session = Depends(get_db),
    next_path: str | None = Query(default=None, alias="next"),
) -> RedirectResponse:
    """Begin OIDC Authorization Code + PKCE login."""

    if auth_mode() == "disabled":
        return RedirectResponse(
            url=_safe_next_path(next_path),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    authorization_url = _required_env("MODELFORGE_OIDC_AUTHORIZATION_URL")
    client_id = _required_env("MODELFORGE_OIDC_CLIENT_ID")
    redirect_uri = _required_env("MODELFORGE_OIDC_REDIRECT_URI")
    scope = os.getenv(
        "MODELFORGE_OIDC_SCOPE",
        "openid profile email",
    ).strip()

    redirect_path = _safe_next_path(next_path)
    state_value, verifier = create_login_challenge(
        session,
        redirect_path=redirect_path,
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state_value,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    separator = "&" if "?" in authorization_url else "?"
    return RedirectResponse(
        url=f"{authorization_url}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/callback", response_class=RedirectResponse)
def browser_callback(
    code: str,
    state_value: str = Query(alias="state"),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    """Exchange the authorization code, establish user identity, and set cookies."""

    if auth_mode() != "oidc":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Browser OIDC login is disabled.",
        )

    try:
        challenge = consume_login_challenge(session, state_value)
    except LoginChallengeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    token_url = _required_env("MODELFORGE_OIDC_TOKEN_URL")
    client_id = _required_env("MODELFORGE_OIDC_CLIENT_ID")
    redirect_uri = _required_env("MODELFORGE_OIDC_REDIRECT_URI")

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": challenge.code_verifier,
    }
    client_secret = os.getenv("MODELFORGE_OIDC_CLIENT_SECRET", "").strip()
    if client_secret:
        form["client_secret"] = client_secret

    try:
        token_response = httpx.post(
            token_url,
            data=form,
            timeout=10.0,
        )
        token_response.raise_for_status()
        tokens = token_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OIDC token exchange failed.",
        ) from exc

    id_token = str(tokens.get("id_token") or "")
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OIDC provider did not return an ID token.",
        )

    try:
        claims = verify_oidc_token(id_token, audience=client_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC ID token verification failed.",
        ) from exc

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC ID token is missing a subject.",
        )

    user = upsert_user(
        session,
        external_subject=subject,
        email=claims.get("email"),
        display_name=claims.get("name") or claims.get("preferred_username"),
    )
    ensure_personal_workspace(session, user)

    ttl = _session_ttl()
    _, raw_session, csrf_secret = create_browser_session(
        session,
        user_id=user.id,
        ttl=ttl,
    )

    response = RedirectResponse(
        url=challenge.redirect_path,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    max_age = int(ttl.total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        raw_session,
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_secret,
        max_age=max_age,
        httponly=False,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def browser_logout(
    request: Request,
    session: Session = Depends(get_db),
) -> Response:
    """Revoke the current browser session and clear session cookies."""

    raw_session = request.cookies.get(SESSION_COOKIE, "")
    if raw_session:
        revoke_browser_session(session, raw_session)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response
