"""Client and protocol definitions for external ModelForge runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ExternalRuntimeError(Exception):
    """Base error raised while communicating with an external runtime."""


class ExternalRuntimeUnavailableError(ExternalRuntimeError):
    """Raised when an external runtime cannot be reached."""


class ExternalRuntimeProtocolError(ExternalRuntimeError):
    """Raised when an external runtime violates the serving protocol."""


class ExternalRuntimePredictionError(ExternalRuntimeError):
    """Raised when an external runtime rejects or fails a prediction."""


@dataclass(frozen=True)
class ExternalRuntimeSpec:
    """Connection information for one external serving runtime."""

    name: str
    base_url: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("External runtime name cannot be empty.")

        if not self.base_url.strip():
            raise ValueError("External runtime base URL cannot be empty.")

        if self.timeout_seconds <= 0:
            raise ValueError(
                "External runtime timeout must be greater than zero."
            )


class ExternalRuntimeClient:
    """Communicate with a framework-independent external runtime."""

    def __init__(
        self,
        spec: ExternalRuntimeSpec,
    ) -> None:
        self._spec = spec

    @property
    def spec(self) -> ExternalRuntimeSpec:
        """Return the immutable runtime connection specification."""

        return self._spec

    def health(self) -> bool:
        """Return whether the external runtime reports itself healthy."""

        try:
            response = httpx.get(
                self._url("/health"),
                timeout=self._spec.timeout_seconds,
            )
        except httpx.RequestError as exc:
            raise ExternalRuntimeUnavailableError(
                f"External runtime '{self._spec.name}' is unavailable."
            ) from exc

        if response.status_code != 200:
            return False

        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalRuntimeProtocolError(
                "External runtime health response must contain JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ExternalRuntimeProtocolError(
                "External runtime health response must be an object."
            )

        return payload.get("status") == "healthy"

    def predict(
        self,
        *,
        inputs: Any,
        model: dict[str, Any],
    ) -> Any:
        """Send one prediction request to the external runtime."""

        try:
            response = httpx.post(
                self._url("/predict"),
                json={
                    "model": model,
                    "inputs": inputs,
                },
                timeout=self._spec.timeout_seconds,
            )
        except httpx.RequestError as exc:
            raise ExternalRuntimeUnavailableError(
                f"External runtime '{self._spec.name}' is unavailable."
            ) from exc

        if response.status_code >= 500:
            raise ExternalRuntimePredictionError(
                f"External runtime '{self._spec.name}' failed prediction."
            )

        if response.status_code >= 400:
            raise ExternalRuntimePredictionError(
                f"External runtime '{self._spec.name}' rejected prediction."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalRuntimeProtocolError(
                "External runtime prediction response must contain JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ExternalRuntimeProtocolError(
                "External runtime prediction response must be an object."
            )

        if "prediction" not in payload:
            raise ExternalRuntimeProtocolError(
                "External runtime response is missing 'prediction'."
            )

        return payload["prediction"]

    def _url(self, path: str) -> str:
        """Build an endpoint URL from the configured runtime base URL."""

        return f"{self._spec.base_url.rstrip('/')}{path}"