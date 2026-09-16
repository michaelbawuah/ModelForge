"""Tests for ModelForge serving observability."""

from __future__ import annotations

import pytest

from modelforge.services.observability import (
    ServingLabels,
    ServingMetrics,
)


def _labels() -> ServingLabels:
    return ServingLabels(
        environment="observability-test",
        framework="test-runtime",
        model_version_id=900001,
        deployment_id=900002,
    )


def test_observe_prediction_preserves_success() -> None:
    """Successful operations pass through instrumentation."""

    metrics = ServingMetrics()

    with metrics.observe_prediction(_labels()):
        result = 42

    assert result == 42


def test_observe_prediction_reraises_failure() -> None:
    """Instrumentation must never swallow inference failures."""

    metrics = ServingMetrics()

    with (
        pytest.raises(RuntimeError, match="runtime exploded"),
        metrics.observe_prediction(_labels()),
    ):
        raise RuntimeError("runtime exploded")


def test_cache_metrics_accept_hit_and_miss() -> None:
    """Both cache outcomes can be recorded."""

    metrics = ServingMetrics()
    labels = _labels()

    metrics.record_cache_event(
        labels,
        cache_hit=True,
    )
    metrics.record_cache_event(
        labels,
        cache_hit=False,
    )