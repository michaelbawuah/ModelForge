"""HTTP routes for the ModelForge model registry."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.registry import Model, ModelVersion
from modelforge.schemas.registry import (
    ModelCreate,
    ModelRead,
    ModelVersionCreate,
    ModelVersionRead,
)
from modelforge.services.artifacts import (
    ArtifactAlreadyExistsError,
    LocalArtifactStore,
)
from modelforge.services.registry import (
    ModelAlreadyExistsError,
    ModelNotFoundError,
    ModelVersionAlreadyExistsError,
    create_model,
    create_model_version,
    create_model_version_from_artifact,
    get_model,
    list_model_versions,
    list_models,
)

router = APIRouter(prefix="/models", tags=["model-registry"])

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_artifact_store() -> LocalArtifactStore:
    """Provide the configured artifact store."""

    return LocalArtifactStore()


ArtifactStorage = Annotated[LocalArtifactStore, Depends(get_artifact_store)]


@router.post("", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def register_model(
    payload: ModelCreate,
    session: DatabaseSession,
) -> Model:
    """Register a new model."""

    try:
        return create_model(session, payload)
    except ModelAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model '{payload.name}' already exists.",
        ) from exc


@router.get("", response_model=list[ModelRead])
def get_models(session: DatabaseSession) -> list[Model]:
    """List registered models."""

    return list_models(session)


@router.get("/{model_id}", response_model=ModelRead)
def get_registered_model(
    model_id: int,
    session: DatabaseSession,
) -> Model:
    """Retrieve one registered model."""

    try:
        return get_model(session, model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} was not found.",
        ) from exc


@router.post(
    "/{model_id}/versions",
    response_model=ModelVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def register_model_version(
    model_id: int,
    payload: ModelVersionCreate,
    session: DatabaseSession,
) -> ModelVersion:
    """Register metadata for an existing immutable model artifact."""

    try:
        return create_model_version(session, model_id, payload)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} was not found.",
        ) from exc
    except ModelVersionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Version '{payload.version}' is already registered "
                f"for model {model_id}."
            ),
        ) from exc


@router.post(
    "/{model_id}/artifacts",
    response_model=ModelVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_model_artifact(
    model_id: int,
    session: DatabaseSession,
    artifact_store: ArtifactStorage,
    version: Annotated[str, Form(min_length=1, max_length=64)],
    framework: Annotated[str, Form(min_length=1, max_length=64)],
    artifact: Annotated[UploadFile, File()],
) -> ModelVersion:
    """Upload an artifact and register its immutable model version."""

    if not artifact.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded artifact must have a filename.",
        )

    try:
        return create_model_version_from_artifact(
            session,
            model_id=model_id,
            version=version,
            framework=framework,
            filename=artifact.filename,
            source=artifact.file,
            artifact_store=artifact_store,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} was not found.",
        ) from exc
    except (ModelVersionAlreadyExistsError, ArtifactAlreadyExistsError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Version '{version}' or its artifact already exists "
                f"for model {model_id}."
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    finally:
        artifact.file.close()


@router.get("/{model_id}/versions", response_model=list[ModelVersionRead])
def get_model_versions(
    model_id: int,
    session: DatabaseSession,
) -> list[ModelVersion]:
    """List versions belonging to a model."""

    try:
        return list_model_versions(session, model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} was not found.",
        ) from exc