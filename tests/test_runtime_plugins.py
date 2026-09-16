"""Tests for third-party ModelForge runtime plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

from modelforge.services.runtimes import (
    RuntimeAlreadyRegisteredError,
    RuntimePlugin,
    RuntimePluginError,
    RuntimeRegistry,
)


class FutureAIRuntime:
    """Pretend runtime from a framework ModelForge does not know."""

    def load(self, artifact_path: Path) -> object:
        return {
            "artifact": str(artifact_path),
        }

    def predict(
        self,
        model: object,
        inputs: object,
    ) -> object:
        return {
            "framework": "future-ai",
            "inputs": inputs,
        }


class InvalidRuntime:
    """Object that deliberately violates the runtime contract."""


class FakeEntryPoint:
    """Minimal stand-in for an installed Python entry point."""

    def __init__(
        self,
        *,
        name: str,
        factory,
    ) -> None:
        self.name = name
        self._factory = factory

    def load(self):
        return self._factory


def test_unknown_future_framework_can_be_added_by_plugin() -> None:
    registry = RuntimeRegistry()

    entry_point = FakeEntryPoint(
        name="future-ai",
        factory=lambda: RuntimePlugin(
            framework="future-ai",
            runtime=FutureAIRuntime(),
        ),
    )

    framework = registry._load_plugin(entry_point)

    assert framework == "future-ai"
    assert registry.frameworks() == ("future-ai",)

    runtime = registry.get("future-ai")
    model = runtime.load(Path("future.model"))

    assert runtime.predict(
        model,
        {"prompt": "hello"},
    ) == {
        "framework": "future-ai",
        "inputs": {"prompt": "hello"},
    }


def test_plugin_framework_names_are_normalized() -> None:
    registry = RuntimeRegistry()

    entry_point = FakeEntryPoint(
        name="future-ai",
        factory=lambda: RuntimePlugin(
            framework="  Future-AI  ",
            runtime=FutureAIRuntime(),
        ),
    )

    registry._load_plugin(entry_point)

    assert registry.frameworks() == ("future-ai",)


def test_invalid_runtime_plugin_is_rejected() -> None:
    registry = RuntimeRegistry()

    entry_point = FakeEntryPoint(
        name="broken-runtime",
        factory=lambda: RuntimePlugin(
            framework="broken",
            runtime=InvalidRuntime(),
        ),
    )

    with pytest.raises(
        RuntimePluginError,
        match="invalid",
    ):
        registry._load_plugin(entry_point)


def test_plugin_must_return_runtime_plugin() -> None:
    registry = RuntimeRegistry()

    entry_point = FakeEntryPoint(
        name="bad-shape",
        factory=lambda: FutureAIRuntime(),
    )

    with pytest.raises(
        RuntimePluginError,
        match="RuntimePlugin",
    ):
        registry._load_plugin(entry_point)


def test_plugin_cannot_replace_existing_framework() -> None:
    registry = RuntimeRegistry()
    registry.register(
        "future-ai",
        FutureAIRuntime(),
    )

    entry_point = FakeEntryPoint(
        name="duplicate-future-ai",
        factory=lambda: RuntimePlugin(
            framework="future-ai",
            runtime=FutureAIRuntime(),
        ),
    )

    with pytest.raises(RuntimeAlreadyRegisteredError):
        registry._load_plugin(entry_point)