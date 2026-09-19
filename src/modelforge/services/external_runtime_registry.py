"""Registry for framework-independent external serving runtimes."""

from __future__ import annotations

from modelforge.services.external_runtimes import (
    ExternalRuntimeClient,
    ExternalRuntimeSpec,
)


class ExternalRuntimeNotFoundError(Exception):
    """Raised when no external runtime supports a framework."""


class ExternalRuntimeAlreadyRegisteredError(Exception):
    """Raised when an external runtime framework already exists."""


class ExternalRuntimeRegistry:
    """Map framework identifiers to external runtime clients."""

    def __init__(self) -> None:
        self._runtimes: dict[str, ExternalRuntimeClient] = {}

    def register(
        self,
        framework: str,
        spec: ExternalRuntimeSpec,
    ) -> None:
        """Register an external runtime for one framework."""

        normalized = self._normalize(framework)

        if normalized in self._runtimes:
            raise ExternalRuntimeAlreadyRegisteredError(
                f"External runtime already registered for framework '{normalized}'."
            )

        self._runtimes[normalized] = ExternalRuntimeClient(spec)

    def get(self, framework: str) -> ExternalRuntimeClient:
        """Return the external runtime registered for a framework."""

        normalized = self._normalize(framework)

        try:
            return self._runtimes[normalized]
        except KeyError as exc:
            raise ExternalRuntimeNotFoundError(
                f"No external runtime is registered for framework '{framework}'."
            ) from exc

    def contains(self, framework: str) -> bool:
        """Return whether an external runtime supports the framework."""

        return self._normalize(framework) in self._runtimes

    def frameworks(self) -> tuple[str, ...]:
        """Return registered framework identifiers."""

        return tuple(sorted(self._runtimes))

    def items(self) -> tuple[tuple[str, ExternalRuntimeClient], ...]:
        """Return registered framework/client pairs in deterministic order."""

        return tuple(
            (framework, self._runtimes[framework])
            for framework in sorted(self._runtimes)
        )

    @staticmethod
    def _normalize(framework: str) -> str:
        normalized = framework.strip().lower()
        if not normalized:
            raise ValueError("framework cannot be empty.")
        return normalized
