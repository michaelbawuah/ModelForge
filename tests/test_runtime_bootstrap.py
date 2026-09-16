"""Tests for ModelForge runtime bootstrap."""

from modelforge.services.runtime_bootstrap import (
    create_runtime_registry,
)


def test_builtin_runtimes_are_registered() -> None:
    registry = create_runtime_registry(
        discover_plugins=False,
    )

    assert registry.frameworks() == (
        "modelforge-json",
        "onnx",
        "pytorch",
    )