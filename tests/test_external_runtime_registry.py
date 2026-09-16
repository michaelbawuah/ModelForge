"""Tests for the external runtime registry."""

import pytest

from modelforge.services.external_runtime_registry import (
    ExternalRuntimeAlreadyRegisteredError,
    ExternalRuntimeNotFoundError,
    ExternalRuntimeRegistry,
)
from modelforge.services.external_runtimes import ExternalRuntimeSpec


def test_external_runtime_registry_registers_and_resolves() -> None:
    registry = ExternalRuntimeRegistry()

    registry.register(
        "FutureAI",
        ExternalRuntimeSpec(
            name="future-runtime",
            base_url="http://future-runtime:9000",
        ),
    )

    runtime = registry.get(" futureai ")

    assert runtime.spec.name == "future-runtime"
    assert registry.contains("FUTUREAI")
    assert registry.frameworks() == ("futureai",)


def test_external_runtime_registry_rejects_duplicates() -> None:
    registry = ExternalRuntimeRegistry()

    spec = ExternalRuntimeSpec(
        name="future-runtime",
        base_url="http://future-runtime",
    )

    registry.register("future-ai", spec)

    with pytest.raises(ExternalRuntimeAlreadyRegisteredError):
        registry.register("FUTURE-AI", spec)


def test_external_runtime_registry_rejects_unknown_framework() -> None:
    registry = ExternalRuntimeRegistry()

    with pytest.raises(ExternalRuntimeNotFoundError):
        registry.get("framework-from-2035")