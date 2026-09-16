"""Business logic for the persistent model registry."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modelforge.models.registry import Model, ModelVersion
from modelforge.schemas.registry import ModelCreate, ModelVersionCreate


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