"""Workspace, API-key, browser-session, and login-state business logic."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modelforge.models.identity import (
    ApiKey,
    BrowserSession,
    OidcLoginChallenge,
    User,
    Workspace,
    WorkspaceMember,
)

DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_WORKSPACE_NAME = "Default Workspace"
VALID_ROLES = ("viewer", "developer", "admin", "owner")
ROLE_RANK = {role: index for index, role in enumerate(VALID_ROLES)}
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


class WorkspaceAlreadyExistsError(Exception):
    """Raised when a workspace slug already exists."""


class WorkspaceNotFoundError(Exception):
    """Raised when a workspace cannot be found for a principal."""


class ApiKeyNotFoundError(Exception):
    """Raised when an API key cannot be found."""


class ApiKeyAuthenticationError(Exception):
    """Raised when an API key is unknown or revoked."""


class BrowserSessionAuthenticationError(Exception):
    """Raised when an opaque browser session is missing, expired, or revoked."""


class LoginChallengeError(Exception):
    """Raised when OIDC login state is missing, expired, or already consumed."""


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ROLE_RANK:
        raise ValueError(
            "role must be one of: " + ", ".join(VALID_ROLES) + "."
        )
    return normalized


def has_minimum_role(role: str, minimum_role: str) -> bool:
    return ROLE_RANK[validate_role(role)] >= ROLE_RANK[validate_role(minimum_role)]


def normalize_workspace_slug(slug: str) -> str:
    normalized = slug.strip().lower()
    if not SLUG_PATTERN.fullmatch(normalized):
        raise ValueError(
            "workspace slug must use lowercase letters, numbers, and hyphens."
        )
    return normalized


def ensure_default_workspace(session: Session) -> Workspace:
    """Return the self-hosted workspace, creating it for non-migrated test DBs."""

    workspace = session.scalar(
        select(Workspace).where(Workspace.slug == DEFAULT_WORKSPACE_SLUG)
    )
    if workspace is not None:
        return workspace

    workspace = Workspace(
        slug=DEFAULT_WORKSPACE_SLUG,
        name=DEFAULT_WORKSPACE_NAME,
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


def upsert_user(
    session: Session,
    *,
    external_subject: str,
    email: str | None,
    display_name: str | None,
) -> User:
    """Synchronize a human identity from an OIDC provider."""

    user = session.scalar(
        select(User).where(User.external_subject == external_subject)
    )
    if user is None:
        user = User(
            external_subject=external_subject,
            email=email,
            display_name=display_name,
        )
        session.add(user)
    else:
        user.email = email
        user.display_name = display_name

    session.commit()
    session.refresh(user)
    return user


def create_workspace(
    session: Session,
    *,
    name: str,
    slug: str,
    owner_user_id: int,
) -> Workspace:
    """Create a workspace and its owner membership atomically."""

    normalized_slug = normalize_workspace_slug(slug)
    workspace = Workspace(name=name.strip(), slug=normalized_slug)
    session.add(workspace)

    try:
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=owner_user_id,
                role="owner",
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise WorkspaceAlreadyExistsError(normalized_slug) from exc

    session.refresh(workspace)
    return workspace


def ensure_personal_workspace(session: Session, user: User) -> Workspace:
    """Ensure an OIDC user has at least one workspace."""

    existing = session.scalar(
        select(Workspace)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.id)
    )
    if existing is not None:
        return existing

    digest = hashlib.sha256(user.external_subject.encode()).hexdigest()[:10]
    return create_workspace(
        session,
        name=(user.display_name or user.email or "My Workspace") + " Workspace",
        slug=f"user-{digest}",
        owner_user_id=user.id,
    )


def list_user_workspaces(session: Session, user_id: int) -> list[Workspace]:
    statement = (
        select(Workspace)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.id)
    )
    return list(session.scalars(statement))


def resolve_user_workspace(
    session: Session,
    *,
    user_id: int,
    selector: str | None,
) -> tuple[Workspace, str]:
    """Resolve a workspace and membership role for an authenticated user."""

    statement = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == user_id)
    )

    if selector:
        clean = selector.strip()
        if clean.isdigit():
            statement = statement.where(Workspace.id == int(clean))
        else:
            statement = statement.where(
                Workspace.slug == normalize_workspace_slug(clean)
            )

    statement = statement.order_by(Workspace.id)
    row = session.execute(statement).first()

    if row is None:
        raise WorkspaceNotFoundError(selector or "default")

    workspace, role = row
    return workspace, role


def create_api_key(
    session: Session,
    *,
    workspace_id: int,
    name: str,
    role: str,
) -> tuple[ApiKey, str]:
    """Create a high-entropy key and return its raw secret exactly once."""

    normalized_role = validate_role(role)
    raw_key = "mf_live_" + token_urlsafe(32)
    prefix = raw_key[:24]

    api_key = ApiKey(
        workspace_id=workspace_id,
        name=name.strip(),
        key_prefix=prefix,
        key_hash=_hash_secret(raw_key),
        role=normalized_role,
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return api_key, raw_key


def list_api_keys(session: Session, workspace_id: int) -> list[ApiKey]:
    statement = (
        select(ApiKey)
        .where(ApiKey.workspace_id == workspace_id)
        .order_by(ApiKey.id)
    )
    return list(session.scalars(statement))


def revoke_api_key(
    session: Session,
    *,
    workspace_id: int,
    api_key_id: int,
) -> ApiKey:
    api_key = session.scalar(
        select(ApiKey).where(
            ApiKey.id == api_key_id,
            ApiKey.workspace_id == workspace_id,
        )
    )
    if api_key is None:
        raise ApiKeyNotFoundError(api_key_id)

    if api_key.revoked_at is None:
        api_key.revoked_at = _utcnow_naive()
        session.commit()
        session.refresh(api_key)

    return api_key


def authenticate_api_key(session: Session, raw_key: str) -> ApiKey:
    """Authenticate a workspace API key without storing its raw secret."""

    if not raw_key.startswith("mf_live_") or len(raw_key) < 32:
        raise ApiKeyAuthenticationError("Invalid ModelForge API key.")

    prefix = raw_key[:24]
    api_key = session.scalar(
        select(ApiKey).where(ApiKey.key_prefix == prefix)
    )

    if (
        api_key is None
        or api_key.revoked_at is not None
        or not hmac.compare_digest(api_key.key_hash, _hash_secret(raw_key))
    ):
        raise ApiKeyAuthenticationError("Invalid ModelForge API key.")

    api_key.last_used_at = _utcnow_naive()
    session.commit()
    session.refresh(api_key)
    return api_key


def create_browser_session(
    session: Session,
    *,
    user_id: int,
    ttl: timedelta,
) -> tuple[BrowserSession, str, str]:
    """Create an opaque browser session and independent CSRF secret."""

    raw_token = "mfs_" + token_urlsafe(48)
    csrf_secret = token_urlsafe(32)
    now = _utcnow_naive()
    browser_session = BrowserSession(
        user_id=user_id,
        token_hash=_hash_secret(raw_token),
        csrf_hash=_hash_secret(csrf_secret),
        expires_at=now + ttl,
        last_seen_at=now,
    )
    session.add(browser_session)
    session.commit()
    session.refresh(browser_session)
    return browser_session, raw_token, csrf_secret


def authenticate_browser_session(
    session: Session,
    raw_token: str,
) -> BrowserSession:
    """Resolve an opaque browser session and enforce expiry/revocation."""

    if not raw_token.startswith("mfs_") or len(raw_token) < 40:
        raise BrowserSessionAuthenticationError("Invalid browser session.")

    browser_session = session.scalar(
        select(BrowserSession).where(
            BrowserSession.token_hash == _hash_secret(raw_token)
        )
    )
    now = _utcnow_naive()

    if (
        browser_session is None
        or browser_session.revoked_at is not None
        or browser_session.expires_at <= now
    ):
        raise BrowserSessionAuthenticationError("Invalid browser session.")

    if (
        browser_session.last_seen_at is None
        or now - browser_session.last_seen_at >= timedelta(minutes=5)
    ):
        browser_session.last_seen_at = now
        session.commit()
        session.refresh(browser_session)

    return browser_session


def verify_browser_csrf(
    browser_session: BrowserSession,
    *,
    cookie_secret: str | None,
    header_secret: str | None,
) -> bool:
    """Verify double-submit CSRF material against the server-side session."""

    if not cookie_secret or not header_secret:
        return False
    if not hmac.compare_digest(cookie_secret, header_secret):
        return False
    return hmac.compare_digest(
        browser_session.csrf_hash,
        _hash_secret(cookie_secret),
    )


def revoke_browser_session(
    session: Session,
    raw_token: str,
) -> None:
    """Revoke a browser session if it exists."""

    if not raw_token:
        return

    browser_session = session.scalar(
        select(BrowserSession).where(
            BrowserSession.token_hash == _hash_secret(raw_token)
        )
    )
    if browser_session is None or browser_session.revoked_at is not None:
        return

    browser_session.revoked_at = _utcnow_naive()
    session.commit()


def create_login_challenge(
    session: Session,
    *,
    redirect_path: str,
    ttl: timedelta = timedelta(minutes=10),
) -> tuple[str, str]:
    """Persist server-side OIDC state and PKCE verifier."""

    now = _utcnow_naive()
    session.execute(
        delete(OidcLoginChallenge).where(OidcLoginChallenge.expires_at <= now)
    )

    state = token_urlsafe(32)
    verifier = token_urlsafe(64)
    challenge = OidcLoginChallenge(
        state_hash=_hash_secret(state),
        code_verifier=verifier,
        redirect_path=redirect_path,
        expires_at=now + ttl,
    )
    session.add(challenge)
    session.commit()
    return state, verifier


def consume_login_challenge(
    session: Session,
    state: str,
) -> OidcLoginChallenge:
    """Consume OIDC state exactly once."""

    challenge = session.get(OidcLoginChallenge, _hash_secret(state))
    now = _utcnow_naive()

    if challenge is None or challenge.expires_at <= now:
        if challenge is not None:
            session.delete(challenge)
            session.commit()
        raise LoginChallengeError("OIDC login state is invalid or expired.")

    session.delete(challenge)
    session.commit()
    return challenge
