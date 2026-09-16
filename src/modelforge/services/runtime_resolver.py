"""Unified resolution of in-process and external inference runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from modelforge.services.external_runtime_registry import (
    ExternalRuntimeRegistry,
)
from modelforge.services.external_runtimes import ExternalRuntimeClient
from modelforge.services.runtimes import (
    ModelRuntime,
    RuntimeNotFoundError,
    RuntimeRegistry,
)

ExecutionMode = Literal["in_process", "external"]


@dataclass(frozen=True)
class ResolvedRuntime:
    """A runtime selected for one model framework."""

    mode: ExecutionMode
    runtime: ModelRuntime | ExternalRuntimeClient


class RuntimeResolver:
    """Resolve frameworks across ModelForge's runtime boundaries."""

    def __init__(
        self,
        *,
        runtimes: RuntimeRegistry,
        external_runtimes: ExternalRuntimeRegistry,
    ) -> None:
        self._runtimes = runtimes
        self._external_runtimes = external_runtimes

    def resolve(self, framework: str) -> ResolvedRuntime:
        """Resolve an in-process runtime first, then an external runtime."""

        try:
            runtime = self._runtimes.get(framework)
        except RuntimeNotFoundError:
            runtime = None

        if runtime is not None:
            return ResolvedRuntime(
                mode="in_process",
                runtime=runtime,
            )

        if self._external_runtimes.contains(framework):
            return ResolvedRuntime(
                mode="external",
                runtime=self._external_runtimes.get(framework),
            )

        raise RuntimeNotFoundError(
            f"No inference runtime is registered for framework "
            f"'{framework}'."
        )