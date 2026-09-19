"""API schemas for ModelForge deployment targets."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeploymentTargetRead(BaseModel):
    """Public representation of an environment's serving target."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: int
    environment: str
    active_deployment_id: int
    canary_deployment_id: int | None = None
    canary_weight: int = Field(ge=0, le=100)
    updated_at: datetime
