"""API schemas for the ModelForge model registry."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelCreate(BaseModel):
    """Payload used to register a new model."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ModelRead(BaseModel):
    """Public representation of a registered model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class ModelVersionCreate(BaseModel):
    """Metadata used to register an existing immutable model artifact."""

    version: str = Field(min_length=1, max_length=64)
    framework: str = Field(min_length=1, max_length=64)
    artifact_uri: str = Field(min_length=1, max_length=2048)
    checksum: str = Field(min_length=1, max_length=128)


class ModelArtifactCreate(BaseModel):
    """Metadata accompanying an artifact uploaded to ModelForge."""

    version: str = Field(min_length=1, max_length=64)
    framework: str = Field(min_length=1, max_length=64)


class ModelVersionRead(BaseModel):
    """Public representation of a registered model version."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    version: str
    framework: str
    artifact_uri: str
    checksum: str
    status: str
    created_at: datetime