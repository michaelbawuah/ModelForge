"""API schemas for ModelForge deployment targets."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeploymentTargetRead(BaseModel):
    """Public representation of an environment's active deployment."""

    model_config = ConfigDict(from_attributes=True)

    environment: str
    active_deployment_id: int
    updated_at: datetime