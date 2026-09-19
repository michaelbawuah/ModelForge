"""Configuration-driven bootstrap for external ModelForge runtimes."""

from __future__ import annotations

import json
import os
from typing import Any

from modelforge.services.external_runtime_registry import ExternalRuntimeRegistry
from modelforge.services.external_runtimes import ExternalRuntimeSpec

EXTERNAL_RUNTIMES_ENV = "MODELFORGE_EXTERNAL_RUNTIMES"
_ALLOWED_FIELDS = frozenset({"name", "base_url", "timeout_seconds"})


def create_external_runtime_registry(
    configuration: str | None = None,
) -> ExternalRuntimeRegistry:
    """Build an external runtime registry from JSON configuration.

    The configuration is a mapping from framework identifier to connection
    settings. Keeping this mapping outside ModelForge core lets new frameworks
    integrate without adding framework-specific branches to the control plane.

    Example::

        {
          "go-linear": {
            "name": "modelforge-go-runtime",
            "base_url": "http://go-runtime:8090",
            "timeout_seconds": 2.0
          }
        }
    """

    registry = ExternalRuntimeRegistry()
    raw = configuration

    if raw is None:
        raw = os.getenv(EXTERNAL_RUNTIMES_ENV)

    if raw is None or not raw.strip():
        return registry

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{EXTERNAL_RUNTIMES_ENV} must contain valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise TypeError(
            f"{EXTERNAL_RUNTIMES_ENV} must be a JSON object keyed by framework."
        )

    for framework, settings in payload.items():
        _register_runtime(registry, framework, settings)

    return registry


def _register_runtime(
    registry: ExternalRuntimeRegistry,
    framework: Any,
    settings: Any,
) -> None:
    """Validate and register one configured external runtime."""

    if not isinstance(framework, str) or not framework.strip():
        raise ValueError("External runtime framework names must be non-empty strings.")

    if not isinstance(settings, dict):
        raise TypeError(
            f"External runtime configuration for '{framework}' must be an object."
        )

    unknown_fields = set(settings) - _ALLOWED_FIELDS
    if unknown_fields:
        unknown = ", ".join(sorted(unknown_fields))
        raise ValueError(
            f"External runtime '{framework}' has unsupported fields: {unknown}."
        )

    base_url = settings.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError(
            f"External runtime '{framework}' requires a non-empty base_url."
        )

    name = settings.get("name", framework)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            f"External runtime '{framework}' requires a non-empty name."
        )

    timeout_seconds = settings.get("timeout_seconds", 10.0)
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
    ):
        raise TypeError(
            f"External runtime '{framework}' timeout_seconds must be numeric."
        )

    registry.register(
        framework,
        ExternalRuntimeSpec(
            name=name,
            base_url=base_url,
            timeout_seconds=float(timeout_seconds),
        ),
    )
