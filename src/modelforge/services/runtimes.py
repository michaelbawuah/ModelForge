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


class RuntimeRegistry:
    """Map model framework names to inference runtime implementations."""

    def __init__(self) -> None:
        self._runtimes: dict[str, ModelRuntime] = {}

    def register(
        self,
        framework: str,
        runtime: ModelRuntime,
    ) -> None:
        """Register one runtime under a normalized framework name."""

        normalized = framework.strip().lower()

        if not normalized:
            raise ValueError("framework cannot be empty.")

        self._runtimes[normalized] = runtime

    def get(self, framework: str) -> ModelRuntime:
        """Return the runtime registered for a framework."""

        normalized = framework.strip().lower()

        try:
            return self._runtimes[normalized]
        except KeyError as exc:
            raise RuntimeNotFoundError(
                f"No inference runtime is registered for framework "
                f"'{framework}'."
            ) from exc