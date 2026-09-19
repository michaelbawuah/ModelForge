"""Client and protocol definitions for external ModelForge runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
from typing import Any, Literal

import httpx

from modelforge.services.metrics import (
    EXTERNAL_RUNTIME_CIRCUIT_OPEN,
    EXTERNAL_RUNTIME_REQUESTS,
    EXTERNAL_RUNTIME_RETRIES,
)

CircuitState = Literal["closed", "open", "half_open"]


class ExternalRuntimeError(Exception):
    """Base error raised while communicating with an external runtime."""


class ExternalRuntimeUnavailableError(ExternalRuntimeError):
    """Raised when an external runtime cannot be reached."""


class ExternalRuntimeCircuitOpenError(ExternalRuntimeUnavailableError):
    """Raised when a runtime circuit breaker is rejecting requests."""


class ExternalRuntimeProtocolError(ExternalRuntimeError):
    """Raised when an external runtime violates the serving protocol."""


class ExternalRuntimePredictionError(ExternalRuntimeError):
    """Raised when an external runtime rejects or fails a prediction."""


@dataclass(frozen=True)
class ExternalRuntimeSpec:
    """Connection and resilience settings for one external serving runtime."""

    name: str
    base_url: str
    timeout_seconds: float = 10.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.05
    circuit_failure_threshold: int = 3
    circuit_reset_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("External runtime name cannot be empty.")
        if not self.base_url.strip():
            raise ValueError("External runtime base URL cannot be empty.")
        if self.timeout_seconds <= 0:
            raise ValueError("External runtime timeout must be greater than zero.")
        if (
            isinstance(self.max_retries, bool)
            or not isinstance(self.max_retries, int)
            or self.max_retries < 0
        ):
            raise ValueError("max_retries must be a non-negative integer.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative.")
        if (
            isinstance(self.circuit_failure_threshold, bool)
            or not isinstance(self.circuit_failure_threshold, int)
            or self.circuit_failure_threshold <= 0
        ):
            raise ValueError(
                "circuit_failure_threshold must be a positive integer."
            )
        if self.circuit_reset_seconds <= 0:
            raise ValueError("circuit_reset_seconds must be greater than zero.")


@dataclass(frozen=True)
class CircuitSnapshot:
    """Observable state of one external runtime circuit breaker."""

    state: CircuitState
    consecutive_failures: int


class _CircuitBreaker:
    """Small thread-safe circuit breaker for one external runtime."""

    def __init__(
        self,
        *,
        runtime_name: str,
        failure_threshold: int,
        reset_seconds: float,
    ) -> None:
        self._runtime_name = runtime_name
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    def before_request(self) -> None:
        """Reject calls while open, allowing a probe after the reset window."""

        with self._lock:
            opened_at = self._opened_at

        if opened_at is None:
            return

        if monotonic() - opened_at >= self._reset_seconds:
            return

        EXTERNAL_RUNTIME_CIRCUIT_OPEN.labels(self._runtime_name).inc()
        raise ExternalRuntimeCircuitOpenError(
            f"External runtime '{self._runtime_name}' circuit is open."
        )

    def record_success(self) -> None:
        """Close the circuit after a successful transport interaction."""

        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        """Open the circuit once consecutive logical failures cross threshold."""

        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._opened_at = monotonic()

    def snapshot(self) -> CircuitSnapshot:
        """Return current state without mutating the circuit."""

        with self._lock:
            failures = self._consecutive_failures
            opened_at = self._opened_at

        if opened_at is None:
            state: CircuitState = "closed"
        elif monotonic() - opened_at >= self._reset_seconds:
            state = "half_open"
        else:
            state = "open"

        return CircuitSnapshot(
            state=state,
            consecutive_failures=failures,
        )


class ExternalRuntimeClient:
    """Communicate with a framework-independent external runtime."""

    def __init__(self, spec: ExternalRuntimeSpec) -> None:
        self._spec = spec
        self._circuit = _CircuitBreaker(
            runtime_name=spec.name,
            failure_threshold=spec.circuit_failure_threshold,
            reset_seconds=spec.circuit_reset_seconds,
        )

    @property
    def spec(self) -> ExternalRuntimeSpec:
        """Return the immutable runtime connection specification."""

        return self._spec

    def circuit_snapshot(self) -> CircuitSnapshot:
        """Expose circuit state for operations and debugging."""

        return self._circuit.snapshot()

    def health(self) -> bool:
        """Return whether the external runtime reports itself healthy."""

        response = self._request("GET", "/health", operation="health")
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

        response = self._request(
            "POST",
            "/predict",
            operation="predict",
            json_payload={"model": model, "inputs": inputs},
        )

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

    def _request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        operation: str,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute one resilient transport operation."""

        self._circuit.before_request()
        attempts = self._spec.max_retries + 1

        for attempt in range(attempts):
            try:
                if method == "GET":
                    response = httpx.get(
                        self._url(path),
                        timeout=self._spec.timeout_seconds,
                    )
                else:
                    response = httpx.post(
                        self._url(path),
                        json=json_payload,
                        timeout=self._spec.timeout_seconds,
                    )
            except httpx.RequestError as exc:
                if attempt + 1 < attempts:
                    self._record_retry(operation, attempt)
                    continue

                self._circuit.record_failure()
                EXTERNAL_RUNTIME_REQUESTS.labels(
                    self._spec.name,
                    operation,
                    "unavailable",
                ).inc()
                raise ExternalRuntimeUnavailableError(
                    f"External runtime '{self._spec.name}' is unavailable."
                ) from exc

            if response.status_code >= 500:
                if attempt + 1 < attempts:
                    self._record_retry(operation, attempt)
                    continue

                self._circuit.record_failure()
                EXTERNAL_RUNTIME_REQUESTS.labels(
                    self._spec.name,
                    operation,
                    "server_error",
                ).inc()
                return response

            self._circuit.record_success()
            outcome = "client_error" if response.status_code >= 400 else "success"
            EXTERNAL_RUNTIME_REQUESTS.labels(
                self._spec.name,
                operation,
                outcome,
            ).inc()
            return response

        raise RuntimeError("External runtime request loop terminated unexpectedly.")

    def _record_retry(self, operation: str, attempt: int) -> None:
        """Record and back off before a retry."""

        EXTERNAL_RUNTIME_RETRIES.labels(
            self._spec.name,
            operation,
        ).inc()

        delay = self._spec.retry_backoff_seconds * (2**attempt)
        if delay > 0:
            sleep(delay)

    def _url(self, path: str) -> str:
        """Build an endpoint URL from the configured runtime base URL."""

        return f"{self._spec.base_url.rstrip('/')}{path}"
