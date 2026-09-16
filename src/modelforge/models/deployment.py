"""Database entities for ModelForge deployments."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modelforge.db.base import Base


class DeploymentState(StrEnum):
    """Valid lifecycle states for a deployment."""

    DEPLOYING = "DEPLOYING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


class Deployment(Base):
    """A model version deployed into a named environment."""

    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint(
            "model_version_id",
            "environment",
            name="uq_deployments_model_version_environment",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    environment: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DeploymentState.DEPLOYING.value,
        server_default=DeploymentState.DEPLOYING.value,
        index=True,
    )

    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    model_version = relationship("ModelVersion")