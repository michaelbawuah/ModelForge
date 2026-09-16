"""Tests for ModelForge inference runtime registration."""

from pathlib import Path

import pytest

from modelforge.services.runtimes import (
    RuntimeNotFoundError,
    RuntimeRegistry,
)


class FakeRuntime:
    """Minimal runtime used to test registration."""

    def load(self, artifact_path: Path) -> object:
        return {"artifact": str(artifact_path)}

    def predict(self, model: object, inputs: object) -> object:
        return inputs


def test_runtime_can_be_registered_and_retrieved() -> None:
    registry = RuntimeRegistry()
    runtime = FakeRuntime()

    registry.register("Fluxion", runtime)

    assert registry.get("fluxion") is runtime
    assert registry.get("FLUXION") is runtime


def test_framework_names_are_normalized() -> None:
    registry = RuntimeRegistry()
    runtime = FakeRuntime()

    registry.register("  PyTorch  ", runtime)

    assert registry.get("pytorch") is runtime


def test_unknown_runtime_is_rejected() -> None:
    registry = RuntimeRegistry()

    with pytest.raises(RuntimeNotFoundError, match="tensorflow"):
        registry.get("tensorflow")


def test_empty_framework_cannot_be_registered() -> None:
    registry = RuntimeRegistry()

    with pytest.raises(ValueError, match="cannot be empty"):
        registry.register("   ", FakeRuntime())