"""Business logic for the workspace-scoped model registry."""

from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modelforge.models.registry import Model, ModelVersion
from modelforge.schemas.registry import ModelCreate, ModelVersionCreate
from modelforge.services.artifacts import ArtifactStore

DEFAULT_WORKSPACE_ID = 1


class ModelAlreadyExistsError(Exception):
    pass


class ModelNotFoundError(Exception):
    pass


class ModelVersionAlreadyExistsError(Exception):
    pass


def create_model(
    session: Session,
    payload: ModelCreate,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Model:
    model = Model(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(model)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ModelAlreadyExistsError(payload.name) from exc

    session.refresh(model)
    return model


def list_models(
    session: Session,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> list[Model]:
    statement = (
        select(Model)
        .where(Model.workspace_id == workspace_id)
        .order_by(Model.id)
    )
    return list(session.scalars(statement))


def get_model(
    session: Session,
    model_id: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Model:
    model = session.get(Model, model_id)
    if model is None or model.workspace_id != workspace_id:
        raise ModelNotFoundError(model_id)
    return model


def create_model_version(
    session: Session,
    model_id: int,
    payload: ModelVersionCreate,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> ModelVersion:
    get_model(session, model_id, workspace_id=workspace_id)

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
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> ModelVersion:
    model = get_model(session, model_id, workspace_id=workspace_id)

    existing = session.scalar(
        select(ModelVersion).where(
            ModelVersion.model_id == model_id,
            ModelVersion.version == version,
        )
    )
    if existing is not None:
        raise ModelVersionAlreadyExistsError(version)

    artifact = artifact_store.store(
        source,
        namespace=f"workspace-{workspace_id}",
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
        artifact_store.delete(artifact.uri)
        raise

    session.refresh(model_version)
    return model_version


def list_model_versions(
    session: Session,
    model_id: int,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> list[ModelVersion]:
    get_model(session, model_id, workspace_id=workspace_id)
    statement = (
        select(ModelVersion)
        .where(ModelVersion.model_id == model_id)
        .order_by(ModelVersion.id)
    )
    return list(session.scalars(statement))
