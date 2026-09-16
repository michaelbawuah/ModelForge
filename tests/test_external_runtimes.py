"""Tests for framework-independent external runtime communication."""

from __future__ import annotations

import httpx
import pytest

from modelforge.services.external_runtimes import (
    ExternalRuntimeClient,
    ExternalRuntimePredictionError,
    ExternalRuntimeProtocolError,
    ExternalRuntimeSpec,
    ExternalRuntimeUnavailableError,
)


def test_external_runtime_spec_validates_configuration() -> None:
    """Invalid runtime connection settings are rejected."""

    with pytest.raises(ValueError, match="name"):
        ExternalRuntimeSpec(
            name="",
            base_url="http://runtime",
        )

    with pytest.raises(ValueError, match="base URL"):
        ExternalRuntimeSpec(
            name="future-ai",
            base_url="",
        )

    with pytest.raises(ValueError, match="greater than zero"):
        ExternalRuntimeSpec(
            name="future-ai",
            base_url="http://runtime",
            timeout_seconds=0,
        )


def test_external_runtime_health(monkeypatch) -> None:
    """A protocol-compatible runtime can report readiness."""

    def fake_get(
        url: str,
        *,
        timeout: float,
    ) -> httpx.Response:
        assert url == "http://future-runtime:9000/health"
        assert timeout == 3.0

        return httpx.Response(
            200,
            json={"status": "healthy"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="future-ai",
            base_url="http://future-runtime:9000",
            timeout_seconds=3.0,
        )
    )

    assert client.health() is True


def test_external_runtime_prediction(monkeypatch) -> None:
    """ModelForge can invoke a framework it does not understand."""

    def fake_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        assert url == "http://future-runtime:9000/predict"
        assert timeout == 5.0

        assert json["model"] == {
            "artifact_uri": "/models/future.model",
            "version": "7.0.0",
        }

        assert json["inputs"] == [2.0, 4.0]

        return httpx.Response(
            200,
            json={
                "prediction": [200.0, 400.0],
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="future-ai",
            base_url="http://future-runtime:9000",
            timeout_seconds=5.0,
        )
    )

    prediction = client.predict(
        model={
            "artifact_uri": "/models/future.model",
            "version": "7.0.0",
        },
        inputs=[2.0, 4.0],
    )

    assert prediction == [200.0, 400.0]


def test_external_runtime_rejects_invalid_protocol(
    monkeypatch,
) -> None:
    """Malformed runtime responses fail closed."""

    def fake_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={"wrong_field": 123},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="broken-runtime",
            base_url="http://broken-runtime",
        )
    )

    with pytest.raises(
        ExternalRuntimeProtocolError,
        match="prediction",
    ):
        client.predict(
            model={"version": "1"},
            inputs=1,
        )


def test_external_runtime_surfaces_prediction_failure(
    monkeypatch,
) -> None:
    """Runtime execution failures are not mistaken for predictions."""

    def fake_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        return httpx.Response(
            500,
            json={"detail": "model execution failed"},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="failing-runtime",
            base_url="http://failing-runtime",
        )
    )

    with pytest.raises(ExternalRuntimePredictionError):
        client.predict(
            model={"version": "1"},
            inputs=1,
        )


def test_external_runtime_surfaces_network_failure(
    monkeypatch,
) -> None:
    """Network failures become explicit runtime availability errors."""

    def fake_get(
        url: str,
        *,
        timeout: float,
    ) -> httpx.Response:
        request = httpx.Request("GET", url)

        raise httpx.ConnectError(
            "connection refused",
            request=request,
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="offline-runtime",
            base_url="http://offline-runtime",
        )
    )

    with pytest.raises(ExternalRuntimeUnavailableError):
        client.health()