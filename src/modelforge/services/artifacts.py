"""Artifact storage and integrity utilities for ModelForge."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

DEFAULT_ARTIFACT_ROOT = Path(
    os.getenv("MODEL_ARTIFACT_ROOT", ".modelforge/artifacts")
)

CHUNK_SIZE = 1024 * 1024
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


class ArtifactError(Exception):
    """Base exception for artifact-storage failures."""


class ArtifactAlreadyExistsError(ArtifactError):
    """Raised when an immutable artifact already exists."""


class ArtifactNotFoundError(ArtifactError):
    """Raised when an artifact cannot be found."""


class ArtifactIntegrityError(ArtifactError):
    """Raised when an artifact no longer matches its expected checksum."""


@dataclass(frozen=True)
class StoredArtifact:
    """Metadata produced after an artifact is persisted."""

    uri: str
    checksum: str
    size_bytes: int


class ArtifactStore(Protocol):
    """Storage contract implemented by ModelForge artifact backends."""

    def store(
        self,
        source: BinaryIO,
        *,
        model_name: str,
        version: str,
        filename: str,
    ) -> StoredArtifact:
        """Persist an immutable artifact."""

    def verify(self, uri: str, expected_checksum: str) -> bool:
        """Verify that a stored artifact still has the expected content."""

    def delete(self, uri: str) -> None:
        """Delete an artifact."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 checksum of a file using bounded memory."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _validate_component(value: str, label: str) -> str:
    """Reject unsafe or ambiguous path components."""

    if not value or not SAFE_COMPONENT.fullmatch(value):
        raise ValueError(
            f"{label} must contain only letters, numbers, '.', '_' or '-'."
        )

    if value in {".", ".."}:
        raise ValueError(f"{label} cannot be '.' or '..'.")

    return value


class LocalArtifactStore:
    """Filesystem implementation of the ModelForge artifact-store contract."""

    def __init__(self, root: Path = DEFAULT_ARTIFACT_ROOT) -> None:
        self.root = Path(root).resolve()

    def store(
        self,
        source: BinaryIO,
        *,
        model_name: str,
        version: str,
        filename: str,
    ) -> StoredArtifact:
        """Atomically persist an immutable artifact and calculate its checksum."""

        model_name = _validate_component(model_name, "model_name")
        version = _validate_component(version, "version")

        # Path.name strips any directory supplied by a client. Validation then
        # rejects suspicious filenames rather than allowing path traversal.
        safe_filename = Path(filename).name
        _validate_component(safe_filename, "filename")

        destination_dir = self.root / model_name / version
        destination_dir.mkdir(parents=True, exist_ok=True)

        destination = destination_dir / safe_filename

        if destination.exists():
            raise ArtifactAlreadyExistsError(
                f"Artifact already exists: {destination}"
            )

        digest = hashlib.sha256()
        size_bytes = 0

        # Write into the destination directory first, then atomically publish
        # the completed file with os.replace(). Readers never observe a
        # partially written model artifact.
        fd, temporary_name = tempfile.mkstemp(
            prefix=".upload-",
            dir=destination_dir,
        )
        temporary_path = Path(temporary_name)

        try:
            with os.fdopen(fd, "wb") as output:
                while chunk := source.read(CHUNK_SIZE):
                    output.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)

                output.flush()
                os.fsync(output.fileno())

            # Re-check immediately before publication. This protects normal
            # concurrent callers from silently replacing an immutable file.
            if destination.exists():
                raise ArtifactAlreadyExistsError(
                    f"Artifact already exists: {destination}"
                )

            os.replace(temporary_path, destination)

        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        return StoredArtifact(
            uri=str(destination),
            checksum=digest.hexdigest(),
            size_bytes=size_bytes,
        )

    def verify(self, uri: str, expected_checksum: str) -> bool:
        """Verify a stored artifact against its expected SHA-256 checksum."""

        path = self._managed_path(uri)

        if not path.is_file():
            raise ArtifactNotFoundError(f"Artifact not found: {path}")

        actual_checksum = sha256_file(path)

        if actual_checksum != expected_checksum:
            raise ArtifactIntegrityError(
                f"Checksum mismatch for artifact: {path}"
            )

        return True

    def delete(self, uri: str) -> None:
        """Delete an artifact owned by this store."""

        path = self._managed_path(uri)

        if not path.exists():
            return

        path.unlink()
        self._remove_empty_parents(path.parent)

    def _managed_path(self, uri: str) -> Path:
        """Resolve a URI while preventing operations outside the store root."""

        path = Path(uri).resolve()

        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(
                f"Artifact path is outside configured storage root: {path}"
            ) from exc

        return path

    def _remove_empty_parents(self, directory: Path) -> None:
        """Remove empty artifact directories without escaping the store root."""

        current = directory

        while current != self.root:
            try:
                current.rmdir()
            except OSError:
                break

            current = current.parent

        try:
            self.root.rmdir()
        except OSError:
            pass