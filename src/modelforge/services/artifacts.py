"""Artifact storage and integrity utilities for ModelForge."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import urlparse

DEFAULT_ARTIFACT_ROOT = Path(
    os.getenv("MODEL_ARTIFACT_ROOT", ".modelforge/artifacts")
)
DEFAULT_ARTIFACT_CACHE_ROOT = Path(
    os.getenv("MODEL_ARTIFACT_CACHE_ROOT", ".modelforge/cache/artifacts")
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
        namespace: str | None = None,
    ) -> StoredArtifact:
        """Persist an immutable artifact."""

    def verify(self, uri: str, expected_checksum: str) -> bool:
        """Verify that a stored artifact still has the expected content."""

    def delete(self, uri: str) -> None:
        """Delete an artifact."""

    def materialize(self, uri: str, expected_checksum: str) -> Path:
        """Return a verified local path suitable for in-process runtimes."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_component(value: str, label: str) -> str:
    if not value or not SAFE_COMPONENT.fullmatch(value):
        raise ValueError(
            f"{label} must contain only letters, numbers, '.', '_' or '-'."
        )
    if value in {".", ".."}:
        raise ValueError(f"{label} cannot be '.' or '..'.")
    return value


def _artifact_components(
    *,
    namespace: str | None,
    model_name: str,
    version: str,
    filename: str,
) -> tuple[str, ...]:
    parts: list[str] = []

    if namespace is not None:
        parts.append(_validate_component(namespace, "namespace"))

    parts.extend(
        [
            _validate_component(model_name, "model_name"),
            _validate_component(version, "version"),
            _validate_component(Path(filename).name, "filename"),
        ]
    )
    return tuple(parts)


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
        namespace: str | None = None,
    ) -> StoredArtifact:
        components = _artifact_components(
            namespace=namespace,
            model_name=model_name,
            version=version,
            filename=filename,
        )
        destination = self.root.joinpath(*components)
        destination_dir = destination.parent
        destination_dir.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            raise ArtifactAlreadyExistsError(
                f"Artifact already exists: {destination}"
            )

        digest = hashlib.sha256()
        size_bytes = 0
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
        path = self._managed_path(uri)
        if not path.is_file():
            raise ArtifactNotFoundError(f"Artifact does not exist: {path}")

        if sha256_file(path) != expected_checksum:
            raise ArtifactIntegrityError(
                f"Checksum mismatch for artifact: {path}"
            )
        return True

    def materialize(self, uri: str, expected_checksum: str) -> Path:
        path = self._managed_path(uri)
        self.verify(uri, expected_checksum)
        return path

    def delete(self, uri: str) -> None:
        path = self._managed_path(uri)
        if not path.exists():
            return

        path.unlink()
        self._remove_empty_parents(path.parent)

    def _managed_path(self, uri: str) -> Path:
        value = uri[7:] if uri.startswith("file://") else uri
        path = Path(value).resolve()

        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(
                f"Artifact path is outside configured storage root: {path}"
            ) from exc

        return path

    def _remove_empty_parents(self, directory: Path) -> None:
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


class S3ArtifactStore:
    """S3-compatible immutable artifact storage with verified local caching."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        cache_root: Path = DEFAULT_ARTIFACT_CACHE_ROOT,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        client: object | None = None,
    ) -> None:
        if not bucket.strip():
            raise ValueError("S3 artifact bucket cannot be empty.")

        self.bucket = bucket.strip()
        self.prefix = prefix.strip("/")
        self.cache_root = Path(cache_root).resolve()

        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError(
                    "S3 artifact storage requires the 'cloud' optional dependency."
                ) from exc

            client = boto3.client(
                "s3",
                region_name=region_name,
                endpoint_url=endpoint_url,
            )

        self.client = client

    def store(
        self,
        source: BinaryIO,
        *,
        model_name: str,
        version: str,
        filename: str,
        namespace: str | None = None,
    ) -> StoredArtifact:
        components = _artifact_components(
            namespace=namespace,
            model_name=model_name,
            version=version,
            filename=filename,
        )
        key = "/".join(
            part for part in (self.prefix, *components) if part
        )

        digest = hashlib.sha256()
        size_bytes = 0

        with tempfile.TemporaryFile() as temporary:
            while chunk := source.read(CHUNK_SIZE):
                temporary.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)

            temporary.seek(0)

            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=temporary,
                    IfNoneMatch="*",
                    Metadata={"sha256": digest.hexdigest()},
                )
            except Exception as exc:
                if self._is_precondition_failure(exc):
                    raise ArtifactAlreadyExistsError(
                        f"Artifact already exists: s3://{self.bucket}/{key}"
                    ) from exc
                raise

        return StoredArtifact(
            uri=f"s3://{self.bucket}/{key}",
            checksum=digest.hexdigest(),
            size_bytes=size_bytes,
        )

    def verify(self, uri: str, expected_checksum: str) -> bool:
        _, key = self._parse_uri(uri)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._is_not_found(exc):
                raise ArtifactNotFoundError(uri) from exc
            raise

        digest = hashlib.sha256()
        body = response["Body"]

        if hasattr(body, "iter_chunks"):
            iterator = body.iter_chunks(chunk_size=CHUNK_SIZE)
        else:
            iterator = iter(lambda: body.read(CHUNK_SIZE), b"")

        for chunk in iterator:
            if chunk:
                digest.update(chunk)

        if digest.hexdigest() != expected_checksum:
            raise ArtifactIntegrityError(
                f"Checksum mismatch for artifact: {uri}"
            )
        return True

    def materialize(self, uri: str, expected_checksum: str) -> Path:
        _, key = self._parse_uri(uri)
        destination = self.cache_root / expected_checksum

        if destination.is_file() and sha256_file(destination) == expected_checksum:
            return destination

        self.cache_root.mkdir(parents=True, exist_ok=True)

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._is_not_found(exc):
                raise ArtifactNotFoundError(uri) from exc
            raise

        fd, temporary_name = tempfile.mkstemp(
            prefix=".download-",
            dir=self.cache_root,
        )
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()

        try:
            with os.fdopen(fd, "wb") as output:
                body = response["Body"]
                if hasattr(body, "iter_chunks"):
                    iterator = body.iter_chunks(chunk_size=CHUNK_SIZE)
                else:
                    iterator = iter(lambda: body.read(CHUNK_SIZE), b"")

                for chunk in iterator:
                    if not chunk:
                        continue
                    output.write(chunk)
                    digest.update(chunk)

                output.flush()
                os.fsync(output.fileno())

            if digest.hexdigest() != expected_checksum:
                raise ArtifactIntegrityError(
                    f"Checksum mismatch for artifact: {uri}"
                )

            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        return destination

    def delete(self, uri: str) -> None:
        _, key = self._parse_uri(uri)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket:
            raise ValueError(
                f"Artifact URI is not managed by bucket '{self.bucket}': {uri}"
            )

        key = parsed.path.lstrip("/")
        if not key:
            raise ValueError("S3 artifact URI is missing an object key.")
        return parsed.netloc, key

    @staticmethod
    def _error_code(exc: Exception) -> str | None:
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return None
        error = response.get("Error", {})
        if not isinstance(error, dict):
            return None
        return str(error.get("Code") or "")

    @classmethod
    def _is_not_found(cls, exc: Exception) -> bool:
        return cls._error_code(exc) in {"404", "NoSuchKey", "NotFound"}

    @classmethod
    def _is_precondition_failure(cls, exc: Exception) -> bool:
        return cls._error_code(exc) in {"412", "PreconditionFailed"}
