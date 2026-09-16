"""Business logic for the persistent model registry."""

from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modelforge.models.registry import Model, ModelVersion
from modelforge.schemas.registry import ModelCreate, ModelVersionCreate
from modelforge.services.artifacts import ArtifactStore


class ModelAlreadyExistsError(Exception):
    """Raised when a model name is already registered."""


class ModelNotFoundError(Exception):
    """Raised when a requested model does not exist."""


class ModelVersionAlreadyExistsError(Exception):
    """Raised when a model version is already registered."""


def create_model(session: Session, payload: ModelCreate) -> Model:
    """Persist a new model."""

    model = Model(name=payload.name, description=payload.description)
    session.add(model)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ModelAlreadyExistsError(payload.name) from exc

    session.refresh(model)
    return model


def list_models(session: Session) -> list[Model]:
    """Return registered models in deterministic ID order."""

    statement = select(Model).order_by(Model.id)
    return list(session.scalars(statement))


def get_model(session: Session, model_id: int) -> Model:
    """Return one model or raise when it does not exist."""

    model = session.get(Model, model_id)

    if model is None:
        raise ModelNotFoundError(model_id)

    return model


def create_model_version(
    session: Session,
    model_id: int,
    payload: ModelVersionCreate,
) -> ModelVersion:
    """Persist a version belonging to an existing model."""

    get_model(session, model_id)

    model_version = ModelVersion(
        model_id=model_id,
        version=payload.version,
        framework=payload.framework,
        artifact_uri=payload.artifact_uri,
        checksum=payload.checksum,
    )

    session.add(model_version)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ModelVersionAlreadyExistsError(payload.version) from exc

    session.refresh(model_version)
    return model_version


def create_model_version_from_artifact(
    session: Session,
    *,
    model_id: int,
    version: str,
    framework: str,
    filename: str,
    source: BinaryIO,
    artifact_store: ArtifactStore,
) -> ModelVersion:
    """Store an artifact and register its immutable model version.

    Artifact storage and the relational database cannot participate in one
    ACID transaction. If database registration fails after the artifact has
    been written, ModelForge performs compensating cleanup.
    """

    model = get_model(session, model_id)

    existing_statement = select(ModelVersion).where(
        ModelVersion.model_id == model_id,
        ModelVersion.version == version,
    )

    if session.scalar(existing_statement) is not None:
        raise ModelVersionAlreadyExistsError(version)

    artifact = artifact_store.store(
    source,
    model_name=model.name,
    version=version,
    filename=Path(filename).name,
)

    model_version = ModelVersion(
        model_id=model_id,
        version=version,
        framework=framework,
        artifact_uri=artifact.uri,
        checksum=artifact.checksum,
    )

    session.add(model_version)

    try:
        session.commit()
    except Exception:
        session.rollback()

        # Compensating transaction: avoid leaving an orphaned artifact when
        # relational persistence fails.
        artifact_store.delete(artifact.uri)
        raise

    session.refresh(model_version)
    return model_version


def list_model_versions(
    session: Session,
    model_id: int,
) -> list[ModelVersion]:
    """Return all versions belonging to one model."""

    get_model(session, model_id)

    statement = (
        select(ModelVersion)
        .where(ModelVersion.model_id == model_id)
        .order_by(ModelVersion.id)
    )

    return list(session.scalars(statement))