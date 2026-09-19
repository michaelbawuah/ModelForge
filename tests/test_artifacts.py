"""Tests for ModelForge artifact storage."""

import hashlib
import io
from pathlib import Path

import pytest

from modelforge.services.artifacts import (
    ArtifactAlreadyExistsError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    LocalArtifactStore,
    sha256_file,
)


def test_store_artifact_with_sha256(tmp_path: Path) -> None:
    payload = b"pretend-this-is-a-trained-model"
    store = LocalArtifactStore(tmp_path)

    artifact = store.store(
        io.BytesIO(payload),
        model_name="fluxion-gpt",
        version="1.0.0",
        filename="model.bin",
    )

    expected_checksum = hashlib.sha256(payload).hexdigest()
    stored_path = tmp_path / "fluxion-gpt" / "1.0.0" / "model.bin"

    assert artifact.checksum == expected_checksum
    assert artifact.size_bytes == len(payload)
    assert Path(artifact.uri) == stored_path.resolve()
    assert stored_path.read_bytes() == payload
    assert sha256_file(stored_path) == expected_checksum


def test_artifact_is_immutable(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    store.store(
        io.BytesIO(b"version-one"),
        model_name="demo-model",
        version="1.0.0",
        filename="model.bin",
    )

    with pytest.raises(ArtifactAlreadyExistsError):
        store.store(
            io.BytesIO(b"replacement"),
            model_name="demo-model",
            version="1.0.0",
            filename="model.bin",
        )

    assert (
        tmp_path / "demo-model" / "1.0.0" / "model.bin"
    ).read_bytes() == b"version-one"


def test_verify_detects_corruption(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    artifact = store.store(
        io.BytesIO(b"trusted-model"),
        model_name="fraud-detector",
        version="2.1.0",
        filename="weights.bin",
    )

    assert store.verify(artifact.uri, artifact.checksum)

    Path(artifact.uri).write_bytes(b"corrupted-model")

    with pytest.raises(ArtifactIntegrityError):
        store.verify(artifact.uri, artifact.checksum)


def test_verify_detects_missing_artifact(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    missing = tmp_path / "missing" / "1.0.0" / "model.bin"

    with pytest.raises(ArtifactNotFoundError):
        store.verify(str(missing), "deadbeef")


def test_delete_artifact(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    artifact = store.store(
        io.BytesIO(b"temporary-model"),
        model_name="demo-model",
        version="2.0.0",
        filename="weights.bin",
    )

    store.delete(artifact.uri)

    assert not Path(artifact.uri).exists()


@pytest.mark.parametrize(
    ("model_name", "version"),
    [
        ("../escape", "1.0.0"),
        ("safe-model", "../escape"),
        ("safe/model", "1.0.0"),
    ],
)
def test_rejects_unsafe_storage_components(
    tmp_path: Path,
    model_name: str,
    version: str,
) -> None:
    store = LocalArtifactStore(tmp_path)

    with pytest.raises(ValueError):
        store.store(
            io.BytesIO(b"model"),
            model_name=model_name,
            version=version,
            filename="model.bin",
        )


def test_delete_rejects_path_outside_storage_root(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    outside = tmp_path / "important.txt"
    outside.write_text("do not delete")

    with pytest.raises(ValueError):
        store.delete(str(outside))

    assert outside.read_text() == "do not delete"

def test_registry_failure_cleans_up_stored_artifact(tmp_path) -> None:
    """A database failure after storage must not leave an orphan artifact."""

    from unittest.mock import MagicMock

    from modelforge.models.registry import Model
    from modelforge.services.artifacts import LocalArtifactStore
    from modelforge.services.registry import create_model_version_from_artifact

    store = LocalArtifactStore(tmp_path / "artifacts")

    session = MagicMock()
    model = Model(
        id=42,
        workspace_id=1,
        name="cleanup-test-model",
        description=None,
    )

    session.get.return_value = model
    session.scalar.return_value = None
    session.commit.side_effect = RuntimeError("simulated database failure")

    with pytest.raises(RuntimeError, match="simulated database failure"):
        create_model_version_from_artifact(
            session,
            model_id=42,
            version="1.0.0",
            framework="fluxion",
            filename="model.bin",
            source=io.BytesIO(b"artifact-that-must-be-cleaned-up"),
            artifact_store=store,
        )

    expected_artifact = (
        tmp_path
        / "artifacts"
        / "cleanup-test-model"
        / "1.0.0"
        / "model.bin"
    )

    assert not expected_artifact.exists()
    session.rollback.assert_called_once()