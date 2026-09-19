"""HTTP routes for the workspace-scoped ModelForge model registry."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from modelforge.db.session import get_db
from modelforge.models.registry import Model, ModelVersion
from modelforge.schemas.registry import (
    ModelCreate,
    ModelRead,
    ModelVersionCreate,
    ModelVersionRead,
)
from modelforge.services.artifacts import ArtifactAlreadyExistsError, ArtifactStore, LocalArtifactStore
from modelforge.services.auth import Principal, get_principal, require_role
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
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def get_artifact_store() -> ArtifactStore:
    return LocalArtifactStore()


ArtifactStorage = Annotated[ArtifactStore, Depends(get_artifact_store)]


@router.post("", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def register_model(
    payload: ModelCreate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Model:
    require_role(principal, "developer")
    try:
        return create_model(
            session,
            payload,
            workspace_id=principal.workspace_id,
        )
    except ModelAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model '{payload.name}' already exists in this workspace.",
        ) from exc


@router.get("", response_model=list[ModelRead])
def get_models(
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> list[Model]:
    return list_models(session, workspace_id=principal.workspace_id)


@router.get("/{model_id}", response_model=ModelRead)
def get_registered_model(
    model_id: int,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Model:
    try:
        return get_model(
            session,
            model_id,
            workspace_id=principal.workspace_id,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Model {model_id} was not found.") from exc


@router.post(
    "/{model_id}/versions",
    response_model=ModelVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def register_model_version(
    model_id: int,
    payload: ModelVersionCreate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> ModelVersion:
    require_role(principal, "developer")
    try:
        return create_model_version(
            session,
            model_id,
            payload,
            workspace_id=principal.workspace_id,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Model {model_id} was not found.") from exc
    except ModelVersionAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Version '{payload.version}' already exists.") from exc


@router.post(
    "/{model_id}/artifacts",
    response_model=ModelVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_model_artifact(
    model_id: int,
    session: DatabaseSession,
    principal: CurrentPrincipal,
    artifact_store: ArtifactStorage,
    version: Annotated[str, Form(min_length=1, max_length=64)],
    framework: Annotated[str, Form(min_length=1, max_length=64)],
    artifact: Annotated[UploadFile, File()],
) -> ModelVersion:
    require_role(principal, "developer")
    if not artifact.filename:
        raise HTTPException(status_code=400, detail="Uploaded artifact must have a filename.")

    try:
        return create_model_version_from_artifact(
            session,
            model_id=model_id,
            version=version,
            framework=framework,
            filename=artifact.filename,
            source=artifact.file,
            artifact_store=artifact_store,
            workspace_id=principal.workspace_id,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Model {model_id} was not found.") from exc
    except (ModelVersionAlreadyExistsError, ArtifactAlreadyExistsError) as exc:
        raise HTTPException(status_code=409, detail="Version or artifact already exists.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        artifact.file.close()


@router.get("/{model_id}/versions", response_model=list[ModelVersionRead])
def get_model_versions(
    model_id: int,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> list[ModelVersion]:
    try:
        return list_model_versions(
            session,
            model_id,
            workspace_id=principal.workspace_id,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Model {model_id} was not found.") from exc
