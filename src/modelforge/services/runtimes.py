"""Framework-independent model runtime abstractions and plugin discovery."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

RUNTIME_ENTRY_POINT_GROUP = "modelforge.runtimes"


class LoadedModel(Protocol):
    """Marker protocol for a model loaded into memory."""


@runtime_checkable
class ModelRuntime(Protocol):
    """Contract implemented by every ModelForge inference runtime."""

    def load(self, artifact_path: Path) -> LoadedModel:
        """Load an immutable model artifact into memory."""
        ...

    def predict(
        self,
        model: LoadedModel,
        inputs: Any,
    ) -> Any:
        """Run one inference request using a loaded model."""
        ...


@dataclass(frozen=True)
class RuntimePlugin:
    """Runtime implementation exported by a ModelForge plugin."""

    framework: str
    runtime: ModelRuntime


class RuntimeNotFoundError(Exception):
    """Raised when no runtime supports a model framework."""


class RuntimeAlreadyRegisteredError(Exception):
    """Raised when a framework already has a registered runtime."""


class RuntimePluginError(Exception):
    """Raised when an installed runtime plugin violates the plugin contract."""


class RuntimeRegistry:
    """Map normalized framework names to runtime implementations."""

    def __init__(self) -> None:
        self._runtimes: dict[str, ModelRuntime] = {}

    def register(
        self,
        framework: str,
        runtime: ModelRuntime,
    ) -> None:
        """Register one validated runtime without silently replacing another."""

        normalized = self._normalize(framework)
        self._validate_runtime(runtime)

        if normalized in self._runtimes:
            raise RuntimeAlreadyRegisteredError(
                f"An inference runtime is already registered for "
                f"framework '{normalized}'."
            )

        self._runtimes[normalized] = runtime

    def get(self, framework: str) -> ModelRuntime:
        """Return the runtime registered for a framework."""

        normalized = self._normalize(framework)

        try:
            return self._runtimes[normalized]
        except KeyError as exc:
            raise RuntimeNotFoundError(
                f"No inference runtime is registered for framework "
                f"'{framework}'."
            ) from exc

    def frameworks(self) -> tuple[str, ...]:
        """Return registered framework names in deterministic order."""

        return tuple(sorted(self._runtimes))

    def discover_plugins(self) -> tuple[str, ...]:
        """Discover and register installed third-party runtime plugins."""

        discovered: list[str] = []

        for entry_point in entry_points(
            group=RUNTIME_ENTRY_POINT_GROUP
        ):
            framework = self._load_plugin(entry_point)
            discovered.append(framework)

        return tuple(sorted(discovered))

    def _load_plugin(self, entry_point: EntryPoint) -> str:
        """Load and register one runtime plugin entry point."""

        try:
            plugin_factory = entry_point.load()
            plugin = plugin_factory()
        except Exception as exc:
            raise RuntimePluginError(
                f"Failed to load runtime plugin '{entry_point.name}'."
            ) from exc

        if not isinstance(plugin, RuntimePlugin):
            raise RuntimePluginError(
                f"Runtime plugin '{entry_point.name}' must return "
                "a RuntimePlugin instance."
            )

        try:
            self.register(
                plugin.framework,
                plugin.runtime,
            )
        except (ValueError, TypeError) as exc:
            raise RuntimePluginError(
                f"Runtime plugin '{entry_point.name}' is invalid."
            ) from exc

        return self._normalize(plugin.framework)

    @staticmethod
    def _validate_runtime(runtime: object) -> None:
        """Ensure a runtime implements the required serving contract."""

        if not isinstance(runtime, ModelRuntime):
            raise TypeError(
                "runtime must implement load() and predict()."
            )

    @staticmethod
    def _normalize(framework: str) -> str:
        normalized = framework.strip().lower()

        if not normalized:
            raise ValueError("framework cannot be empty.")

        return normalized