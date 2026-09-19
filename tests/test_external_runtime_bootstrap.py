"""Tests for configuration-driven external runtime bootstrap."""

from __future__ import annotations

import pytest

from modelforge.services.external_runtime_bootstrap import (
    EXTERNAL_RUNTIMES_ENV,
    create_external_runtime_registry,
)


def test_empty_configuration_creates_empty_registry() -> None:
    registry = create_external_runtime_registry("")
    assert registry.frameworks() == ()


def test_configuration_registers_framework_agnostic_runtimes() -> None:
    registry = create_external_runtime_registry(
        """
        {
          "future-ai": {
            "name": "runtime-2036",
            "base_url": "http://runtime-2036:9000",
            "timeout_seconds": 3.5,
            "max_retries": 4,
            "circuit_failure_threshold": 5
          },
          "fluxion": {
            "base_url": "http://fluxion-runtime:9100"
          }
        }
        """
    )

    assert registry.frameworks() == ("fluxion", "future-ai")
    assert registry.get("FUTURE-AI").spec.name == "runtime-2036"
    assert registry.get("future-ai").spec.timeout_seconds == 3.5
    assert registry.get("future-ai").spec.max_retries == 4
    assert registry.get("future-ai").spec.circuit_failure_threshold == 5
    assert registry.get("fluxion").spec.name == "fluxion"
    assert registry.get("fluxion").spec.timeout_seconds == 10.0


def test_bootstrap_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        EXTERNAL_RUNTIMES_ENV,
        '{"go-linear":{"base_url":"http://go-runtime:8090"}}',
    )

    registry = create_external_runtime_registry()
    assert registry.frameworks() == ("go-linear",)
    assert registry.get("go-linear").spec.base_url == "http://go-runtime:8090"


@pytest.mark.parametrize(
    ("configuration", "message"),
    [
        ("not-json", "valid JSON"),
        ("[]", "JSON object"),
        ('{"future-ai":[]}', "must be an object"),
        ('{"future-ai":{"name":"x"}}', "base_url"),
        (
            '{"future-ai":{"base_url":"http://runtime","unknown":1}}',
            "unsupported fields",
        ),
        (
            '{"future-ai":{"base_url":"http://runtime","timeout_seconds":"fast"}}',
            "must be numeric",
        ),
        (
            '{"future-ai":{"base_url":"http://runtime","max_retries":1.5}}',
            "must be an integer",
        ),
    ],
)
def test_bootstrap_rejects_invalid_configuration(
    configuration: str,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        create_external_runtime_registry(configuration)
