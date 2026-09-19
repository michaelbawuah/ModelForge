"""Configuration-driven bootstrap for external ModelForge runtimes."""

from __future__ import annotations

import json
import os
from typing import Any

from modelforge.services.external_runtime_registry import ExternalRuntimeRegistry
from modelforge.services.external_runtimes import ExternalRuntimeSpec

EXTERNAL_RUNTIMES_ENV = "MODELFORGE_EXTERNAL_RUNTIMES"
_ALLOWED_FIELDS = frozenset(
    {
        "name",
        "base_url",
        "auth_token_env",
        "timeout_seconds",
        "max_retries",
        "retry_backoff_seconds",
        "circuit_failure_threshold",
        "circuit_reset_seconds",
    }
)


def create_external_runtime_registry(
    configuration: str | None = None,
) -> ExternalRuntimeRegistry:
    """Build an external runtime registry from JSON configuration."""

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

    timeout_seconds = _float_setting(settings, "timeout_seconds", 10.0)

    registry.register(
        framework,
        ExternalRuntimeSpec(
            name=name,
            base_url=base_url,
            auth_token=_secret_setting(settings, framework),
            timeout_seconds=timeout_seconds,
            max_retries=_integer_setting(settings, "max_retries", 1),
            retry_backoff_seconds=_float_setting(
                settings,
                "retry_backoff_seconds",
                0.05,
            ),
            circuit_failure_threshold=_integer_setting(
                settings,
                "circuit_failure_threshold",
                3,
            ),
            circuit_reset_seconds=_float_setting(
                settings,
                "circuit_reset_seconds",
                30.0,
            ),
        ),
    )


def _integer_setting(
    settings: dict[str, Any],
    name: str,
    default: int,
) -> int:
    """Read an integer runtime setting without accepting booleans."""

    value = settings.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    return value


def _float_setting(
    settings: dict[str, Any],
    name: str,
    default: float,
) -> float:
    """Read a numeric runtime setting without accepting booleans."""

    value = settings.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    return float(value)



def _secret_setting(
    settings: dict[str, Any],
    framework: str,
) -> str | None:
    """Resolve an optional runtime bearer token from a separate environment variable."""

    environment_name = settings.get("auth_token_env")
    if environment_name is None:
        return None
    if not isinstance(environment_name, str) or not environment_name.strip():
        raise ValueError(
            f"External runtime '{framework}' auth_token_env must be a non-empty string."
        )

    secret = os.getenv(environment_name, "")
    if not secret:
        raise ValueError(
            f"External runtime '{framework}' references missing secret "
            f"environment variable '{environment_name}'."
        )
    return secret
