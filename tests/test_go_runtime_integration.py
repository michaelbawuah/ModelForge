"""Live integration test for the ModelForge Go runtime."""

from __future__ import annotations

import pytest

from modelforge.services.external_runtimes import (
    ExternalRuntimeClient,
    ExternalRuntimeSpec,
    ExternalRuntimeUnavailableError,
)

GO_RUNTIME_URL = "http://127.0.0.1:8090"


@pytest.fixture
def go_runtime() -> ExternalRuntimeClient:
    """Return a client for the locally running Go runtime."""

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="modelforge-go-runtime",
            base_url=GO_RUNTIME_URL,
            timeout_seconds=2.0,
        )
    )

    try:
        healthy = client.health()
    except ExternalRuntimeUnavailableError:
        pytest.skip(
            "Go runtime is not running on localhost:8090."
        )

    if not healthy:
        pytest.fail("Go runtime reported itself unhealthy.")

    return client


def test_go_runtime_health(
    go_runtime: ExternalRuntimeClient,
) -> None:
    """Python can verify the Go process is healthy."""

    assert go_runtime.health() is True


def test_go_runtime_prediction(
    go_runtime: ExternalRuntimeClient,
) -> None:
    """Python can execute inference through the Go process."""

    prediction = go_runtime.predict(
        inputs=5,
        model={
            "model_version_id": 1,
            "version": "1.0.0",
            "framework": "go-linear",
            "artifact_uri": "/tmp/example.model",
            "checksum": "abc123",
        },
    )

    assert prediction == 11
