"""Resilience tests for external runtime communication."""

from __future__ import annotations

import httpx
import pytest

from modelforge.services.external_runtimes import (
    ExternalRuntimeCircuitOpenError,
    ExternalRuntimeClient,
    ExternalRuntimeSpec,
    ExternalRuntimeUnavailableError,
)


def test_external_runtime_retries_transient_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            request = httpx.Request("POST", url)
            raise httpx.ConnectError("temporary failure", request=request)
        return httpx.Response(200, json={"prediction": 42})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="future-runtime",
            base_url="http://future-runtime",
            max_retries=1,
            retry_backoff_seconds=0,
        )
    )

    assert client.predict(inputs=1, model={"version": "1"}) == 42
    assert calls == 2
    assert client.circuit_snapshot().state == "closed"


def test_external_runtime_opens_circuit_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1
        request = httpx.Request("POST", url)
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr(httpx, "post", fail_post)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="offline-runtime",
            base_url="http://offline-runtime",
            max_retries=0,
            circuit_failure_threshold=2,
            circuit_reset_seconds=60,
        )
    )

    for _ in range(2):
        with pytest.raises(ExternalRuntimeUnavailableError):
            client.predict(inputs=1, model={"version": "1"})

    assert calls == 2
    assert client.circuit_snapshot().state == "open"

    with pytest.raises(ExternalRuntimeCircuitOpenError):
        client.predict(inputs=1, model={"version": "1"})

    assert calls == 2


def test_success_resets_consecutive_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_post(
        url: str,
        *,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            request = httpx.Request("POST", url)
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, json={"prediction": 7})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = ExternalRuntimeClient(
        ExternalRuntimeSpec(
            name="runtime",
            base_url="http://runtime",
            max_retries=0,
            circuit_failure_threshold=3,
        )
    )

    with pytest.raises(ExternalRuntimeUnavailableError):
        client.predict(inputs=1, model={"version": "1"})

    assert client.circuit_snapshot().consecutive_failures == 1
    assert client.predict(inputs=1, model={"version": "1"}) == 7
    assert client.circuit_snapshot().consecutive_failures == 0
