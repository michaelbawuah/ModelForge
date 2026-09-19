"""Database entity for authoritative deployment targets."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modelforge.db.base import Base


class DeploymentTarget(Base):
    """Stable and optional canary deployments selected for an environment."""

    __tablename__ = "deployment_targets"
    __table_args__ = (
        CheckConstraint(
            "canary_weight >= 0 AND canary_weight <= 100",
            name="ck_deployment_targets_canary_weight",
        ),
    )

    environment: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    active_deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    canary_deployment_id: Mapped[int | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )

    canary_weight: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    active_deployment = relationship(
        "Deployment",
        foreign_keys=[active_deployment_id],
    )
    canary_deployment = relationship(
        "Deployment",
        foreign_keys=[canary_deployment_id],
    )
