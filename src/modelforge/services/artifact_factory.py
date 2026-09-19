"""Configuration-driven artifact-store construction."""

from __future__ import annotations

import os

from modelforge.services.artifacts import ArtifactStore, LocalArtifactStore, S3ArtifactStore


def create_artifact_store() -> ArtifactStore:
    """Create the configured local or S3-compatible artifact backend."""

    backend = os.getenv("MODEL_ARTIFACT_BACKEND", "local").strip().lower()

    if backend == "local":
        return LocalArtifactStore()

    if backend == "s3":
        bucket = os.getenv("MODEL_ARTIFACT_S3_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError(
                "MODEL_ARTIFACT_S3_BUCKET is required when MODEL_ARTIFACT_BACKEND=s3."
            )

        return S3ArtifactStore(
            bucket=bucket,
            prefix=os.getenv("MODEL_ARTIFACT_S3_PREFIX", "modelforge"),
            region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
            endpoint_url=os.getenv("MODEL_ARTIFACT_S3_ENDPOINT") or None,
        )

    raise RuntimeError("MODEL_ARTIFACT_BACKEND must be 'local' or 's3'.")
