"""Public API schemas for ModelForge SaaS identity resources."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    """Create a new tenant workspace."""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=80)


class WorkspaceRead(BaseModel):
    """Public workspace representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    created_at: datetime


class CurrentPrincipalRead(BaseModel):
    """Identity and workspace selected for the current request."""

    auth_type: str
    user_id: int | None
    workspace_id: int
    workspace_slug: str
    role: str
    email: str | None = None
    display_name: str | None = None


class ApiKeyCreate(BaseModel):
    """Create a workspace-bound API key."""

    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="developer")


class ApiKeyRead(BaseModel):
    """API-key metadata that never exposes the credential secret."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    key_prefix: str
    role: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreatedRead(ApiKeyRead):
    """API-key creation response. The raw secret is returned exactly once."""

    secret: str
