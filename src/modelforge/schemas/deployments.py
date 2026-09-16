"""API schemas for ModelForge deployments."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from modelforge.models.deployment import DeploymentState


class DeploymentCreate(BaseModel):
    """Request to deploy a registered model version."""

    model_version_id: int = Field(gt=0)
    environment: str = Field(min_length=1, max_length=64)


class DeploymentFailure(BaseModel):
    """Failure information for an unsuccessful deployment."""

    reason: str = Field(min_length=1, max_length=2048)


class DeploymentRead(BaseModel):
    """Public representation of a deployment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    model_version_id: int
    environment: str
    state: DeploymentState
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime