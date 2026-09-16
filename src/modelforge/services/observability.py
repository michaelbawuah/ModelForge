"""Serving observability helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

from modelforge.services.metrics import (
    MODEL_CACHE_EVENTS,
    PREDICTION_LATENCY,
    PREDICTION_REQUESTS,
)


@dataclass(frozen=True)
class ServingLabels:
    """Stable operational identity for one serving target."""

    environment: str
    framework: str
    model_version_id: int
    deployment_id: int

    def prometheus_values(self) -> tuple[str, str, str, str]:
        """Return labels in the order expected by serving metrics."""

        return (
            self.environment,
            self.framework,
            str(self.model_version_id),
            str(self.deployment_id),
        )


class ServingMetrics:
    """Record metrics for successful and failed inference operations."""

    def record_cache_event(
        self,
        labels: ServingLabels,
        *,
        cache_hit: bool,
    ) -> None:
        """Record whether model execution reused an in-memory model."""

        MODEL_CACHE_EVENTS.labels(
            *labels.prometheus_values(),
            "hit" if cache_hit else "miss",
        ).inc()

    @contextmanager
    def observe_prediction(
        self,
        labels: ServingLabels,
    ) -> Iterator[None]:
        """Measure one prediction and classify its outcome."""

        started_at = perf_counter()
        status = "success"

        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = perf_counter() - started_at

            PREDICTION_LATENCY.labels(
                *labels.prometheus_values(),
            ).observe(elapsed)

            PREDICTION_REQUESTS.labels(
                *labels.prometheus_values(),
                status,
            ).inc()