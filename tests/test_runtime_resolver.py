"""Tests for unified runtime resolution."""

from pathlib import Path
from typing import Any

import pytest

from modelforge.services.external_runtime_registry import (
    ExternalRuntimeRegistry,
)
from modelforge.services.external_runtimes import ExternalRuntimeSpec
from modelforge.services.runtime_resolver import RuntimeResolver
from modelforge.services.runtimes import (
    RuntimeNotFoundError,
    RuntimeRegistry,
)


class FakeRuntime:
    """Minimal in-process runtime used for resolution tests."""

    def load(self, artifact_path: Path) -> object:
        return {"artifact": str(artifact_path)}

    def predict(self, model: object, inputs: Any) -> Any:
        return inputs


def test_resolver_prefers_in_process_runtime() -> None:
    runtimes = RuntimeRegistry()
    external_runtimes = ExternalRuntimeRegistry()

    runtimes.register("future-ai", FakeRuntime())

    external_runtimes.register(
        "future-ai",
        ExternalRuntimeSpec(
            name="future-external",
            base_url="http://future-runtime",
        ),
    )

    resolver = RuntimeResolver(
        runtimes=runtimes,
        external_runtimes=external_runtimes,
    )

    resolved = resolver.resolve("FUTURE-AI")

    assert resolved.mode == "in_process"
    assert isinstance(resolved.runtime, FakeRuntime)


def test_resolver_falls_back_to_external_runtime() -> None:
    runtimes = RuntimeRegistry()
    external_runtimes = ExternalRuntimeRegistry()

    external_runtimes.register(
        "framework-from-2035",
        ExternalRuntimeSpec(
            name="2035-runtime",
            base_url="http://runtime-2035:9000",
        ),
    )

    resolver = RuntimeResolver(
        runtimes=runtimes,
        external_runtimes=external_runtimes,
    )

    resolved = resolver.resolve(" FRAMEWORK-FROM-2035 ")

    assert resolved.mode == "external"
    assert resolved.runtime.spec.name == "2035-runtime"


def test_resolver_rejects_unknown_framework() -> None:
    resolver = RuntimeResolver(
        runtimes=RuntimeRegistry(),
        external_runtimes=ExternalRuntimeRegistry(),
    )

    with pytest.raises(
        RuntimeNotFoundError,
        match="unknown-framework",
    ):
        resolver.resolve("unknown-framework")