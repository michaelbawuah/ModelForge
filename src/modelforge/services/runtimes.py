"""Framework-independent model runtime abstractions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class LoadedModel(Protocol):
    """Marker protocol for a model loaded into memory."""


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


class RuntimeNotFoundError(Exception):
    """Raised when no runtime supports a model framework."""


class RuntimeAlreadyRegisteredError(Exception):
    """Raised when a framework already has a registered runtime."""


class RuntimeRegistry:
    """Map normalized framework names to runtime implementations."""

    def __init__(self) -> None:
        self._runtimes: dict[str, ModelRuntime] = {}

    def register(
        self,
        framework: str,
        runtime: ModelRuntime,
    ) -> None:
        """Register one runtime without silently replacing another."""

        normalized = self._normalize(framework)

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

    @staticmethod
    def _normalize(framework: str) -> str:
        normalized = framework.strip().lower()

        if not normalized:
            raise ValueError("framework cannot be empty.")

        return normalized