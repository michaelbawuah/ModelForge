"""Prometheus metrics for ModelForge serving."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

PREDICTION_REQUESTS = Counter(
    "modelforge_prediction_requests_total",
    "Total prediction requests handled by ModelForge.",
    (
        "environment",
        "framework",
        "model_version_id",
        "deployment_id",
        "status",
    ),
)

PREDICTION_LATENCY = Histogram(
    "modelforge_prediction_latency_seconds",
    "End-to-end prediction latency in seconds.",
    (
        "environment",
        "framework",
        "model_version_id",
        "deployment_id",
    ),
)

MODEL_CACHE_EVENTS = Counter(
    "modelforge_model_cache_events_total",
    "Model cache hits and misses during inference.",
    (
        "environment",
        "framework",
        "model_version_id",
        "deployment_id",
        "result",
    ),
)