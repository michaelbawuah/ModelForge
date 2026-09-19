"""SaaS identity, workspace, and API-key routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.identity import ApiKey, Workspace
from modelforge.schemas.identity import (
    ApiKeyCreate,
    ApiKeyCreatedRead,
    ApiKeyRead,
    CurrentPrincipalRead,
    WorkspaceCreate,
    WorkspaceRead,
)
from modelforge.services.auth import Principal, get_principal, require_role
from modelforge.services.identity import (
    ApiKeyNotFoundError,
    WorkspaceAlreadyExistsError,
    create_api_key,
    create_workspace,
    list_api_keys,
    list_user_workspaces,
    revoke_api_key,
)

router = APIRouter(tags=["saas"])
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


@router.get("/auth/me", response_model=CurrentPrincipalRead)
def current_identity(principal: CurrentPrincipal) -> CurrentPrincipalRead:
    """Return the current identity and selected tenant workspace."""

    return CurrentPrincipalRead(
        auth_type=principal.auth_type,
        user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        workspace_slug=principal.workspace_slug,
        role=principal.role,
        email=principal.email,
        display_name=principal.display_name,
    )


@router.get("/workspaces", response_model=list[WorkspaceRead])
def get_workspaces(
    principal: CurrentPrincipal,
    session: DatabaseSession,
) -> list[Workspace]:
    """List workspaces accessible to the current human identity."""

    if principal.user_id is None:
        workspace = session.get(Workspace, principal.workspace_id)
        return [workspace] if workspace is not None else []

    return list_user_workspaces(session, principal.user_id)


@router.post(
    "/workspaces",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_new_workspace(
    payload: WorkspaceCreate,
    principal: CurrentPrincipal,
    session: DatabaseSession,
) -> Workspace:
    """Create a tenant workspace owned by the current OIDC user."""

    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace creation requires a signed-in user.",
        )

    try:
        return create_workspace(
            session,
            name=payload.name,
            slug=payload.slug,
            owner_user_id=principal.user_id,
        )
    except WorkspaceAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workspace slug '{payload.slug}' already exists.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/api-keys", response_model=list[ApiKeyRead])
def get_api_keys(
    principal: CurrentPrincipal,
    session: DatabaseSession,
) -> list[ApiKey]:
    """List API-key metadata for the selected workspace."""

    require_role(principal, "admin")
    return list_api_keys(session, principal.workspace_id)


@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace_api_key(
    payload: ApiKeyCreate,
    principal: CurrentPrincipal,
    session: DatabaseSession,
) -> ApiKeyCreatedRead:
    """Create an API key and return its raw secret exactly once."""

    require_role(principal, "admin")

    try:
        api_key, secret = create_api_key(
            session,
            workspace_id=principal.workspace_id,
            name=payload.name,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    metadata = ApiKeyRead.model_validate(api_key)
    return ApiKeyCreatedRead(
        **metadata.model_dump(),
        secret=secret,
    )


@router.delete(
    "/api-keys/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_workspace_api_key(
    api_key_id: int,
    principal: CurrentPrincipal,
    session: DatabaseSession,
) -> Response:
    """Revoke a workspace API key without deleting its audit metadata."""

    require_role(principal, "admin")

    try:
        revoke_api_key(
            session,
            workspace_id=principal.workspace_id,
            api_key_id=api_key_id,
        )
    except ApiKeyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {api_key_id} was not found.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
