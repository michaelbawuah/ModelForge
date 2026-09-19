"""Prometheus metrics for ModelForge serving."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

PREDICTION_REQUESTS = Counter(
    "modelforge_prediction_requests_total",
    "Total prediction requests handled by ModelForge.",
    ("environment", "framework", "model_version_id", "deployment_id", "status"),
)

PREDICTION_LATENCY = Histogram(
    "modelforge_prediction_latency_seconds",
    "End-to-end prediction latency in seconds.",
    ("environment", "framework", "model_version_id", "deployment_id"),
)

MODEL_CACHE_EVENTS = Counter(
    "modelforge_model_cache_events_total",
    "Model cache hits and misses during inference.",
    ("environment", "framework", "model_version_id", "deployment_id", "result"),
)

EXTERNAL_RUNTIME_REQUESTS = Counter(
    "modelforge_external_runtime_requests_total",
    "External runtime transport requests by outcome.",
    ("runtime", "operation", "outcome"),
)

EXTERNAL_RUNTIME_RETRIES = Counter(
    "modelforge_external_runtime_retries_total",
    "Retries performed against external runtimes.",
    ("runtime", "operation"),
)

EXTERNAL_RUNTIME_CIRCUIT_OPEN = Counter(
    "modelforge_external_runtime_circuit_open_total",
    "Requests rejected because an external runtime circuit is open.",
    ("runtime",),
)
