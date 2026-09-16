"""Database entity for authoritative deployment targets."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modelforge.db.base import Base


class DeploymentTarget(Base):
    """The deployment currently selected for an environment."""

    __tablename__ = "deployment_targets"

    environment: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    active_deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    active_deployment = relationship("Deployment")
