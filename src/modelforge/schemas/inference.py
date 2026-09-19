"""API schemas for ModelForge inference."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    """Request inference from an environment's serving target."""

    environment: str = Field(min_length=1, max_length=64)
    inputs: Any


class PredictionResponse(BaseModel):
    """Prediction plus metadata identifying exactly what served it."""

    prediction: Any
    environment: str
    deployment_id: int
    model_version_id: int
    model_version: str
    framework: str
    cache_hit: bool
    traffic_lane: Literal["stable", "canary"]
    canary_fallback: bool
