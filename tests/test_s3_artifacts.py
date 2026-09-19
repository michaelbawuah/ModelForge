"""Tests for the S3-compatible ModelForge artifact backend."""

import io
from pathlib import Path

import pytest

from modelforge.services.artifacts import (
    ArtifactAlreadyExistsError,
    S3ArtifactStore,
)


class FakeBody:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def iter_chunks(self, chunk_size: int):
        for offset in range(0, len(self._value), chunk_size):
            yield self._value[offset : offset + chunk_size]


class FakeS3Error(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch, Metadata):
        identity = (Bucket, Key)
        if identity in self.objects and IfNoneMatch == "*":
            raise FakeS3Error("PreconditionFailed")
        self.objects[identity] = Body.read()
        return {"Metadata": Metadata}

    def get_object(self, *, Bucket, Key):
        try:
            value = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise FakeS3Error("NoSuchKey") from exc
        return {"Body": FakeBody(value)}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def test_s3_store_namespaces_and_materializes_artifacts(tmp_path: Path) -> None:
    client = FakeS3()
    store = S3ArtifactStore(
        bucket="models",
        prefix="prod",
        cache_root=tmp_path / "cache",
        client=client,
    )

    artifact = store.store(
        io.BytesIO(b"model-bytes"),
        namespace="workspace-42",
        model_name="fraud",
        version="1.0.0",
        filename="model.bin",
    )

    assert artifact.uri == (
        "s3://models/prod/workspace-42/fraud/1.0.0/model.bin"
    )
    assert store.verify(artifact.uri, artifact.checksum) is True

    materialized = store.materialize(
        artifact.uri,
        artifact.checksum,
    )
    assert materialized.read_bytes() == b"model-bytes"


def test_s3_store_refuses_immutable_overwrite(tmp_path: Path) -> None:
    client = FakeS3()
    store = S3ArtifactStore(
        bucket="models",
        cache_root=tmp_path,
        client=client,
    )

    kwargs = {
        "namespace": "workspace-1",
        "model_name": "model",
        "version": "1",
        "filename": "artifact.bin",
    }
    store.store(io.BytesIO(b"first"), **kwargs)

    with pytest.raises(ArtifactAlreadyExistsError):
        store.store(io.BytesIO(b"second"), **kwargs)
