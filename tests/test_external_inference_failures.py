"""Failure-path tests for BYOR external inference."""

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


def _client() -> ExternalRuntimeClient:
    return ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="external-test-runtime",
            base_url="http://external-runtime:9000",
            timeout_seconds=2.0,
        )
    )


def test_external_prediction_network_failure(
    monkeypatch,
) -> None:
    """Connection failures are classified as availability failures."""

    def fail_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        request = httpx.Request("POST", url)

        raise httpx.ConnectError(
            "connection refused",
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fail_post)

    with pytest.raises(ExternalRuntimeUnavailableError):
        _client().predict(
            inputs=[1.0],
            model={"version": "1"},
        )


def test_external_prediction_rejects_non_json_response(
    monkeypatch,
) -> None:
    """Malformed successful responses fail the protocol contract."""

    def invalid_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
        )

    monkeypatch.setattr(httpx, "post", invalid_post)

    with pytest.raises(ExternalRuntimeProtocolError):
        _client().predict(
            inputs=[1.0],
            model={"version": "1"},
        )


def test_external_prediction_rejects_client_error(
    monkeypatch,
) -> None:
    """Runtime request rejection is surfaced explicitly."""

    def reject_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": "invalid tensor shape"},
        )

    monkeypatch.setattr(httpx, "post", reject_post)

    with pytest.raises(ExternalRuntimePredictionError):
        _client().predict(
            inputs=[1.0],
            model={"version": "1"},
        )