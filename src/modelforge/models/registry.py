"""Database entities for the ModelForge model registry."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modelforge.db.base import Base


class Model(Base):
    """A logical machine-learning model tracked by ModelForge."""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    versions: Mapped[list["ModelVersion"]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
    )


class ModelVersion(Base):
    """One immutable registered version of a machine-learning model."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "version",
            name="uq_model_versions_model_id_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    model_id: Mapped[int] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version: Mapped[str] = mapped_column(String(64), nullable=False)
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="REGISTERED",
        server_default="REGISTERED",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    model: Mapped["Model"] = relationship(back_populates="versions")
