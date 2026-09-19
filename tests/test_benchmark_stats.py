"""Tests for deterministic benchmark aggregation helpers."""

from benchmarks.load_test import RequestSample, percentile, summarize


def test_percentile_interpolates_values() -> None:
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 50) == 25.0
    assert percentile(values, 95) == 38.5


def test_summary_reports_latency_and_serving_metadata() -> None:
    samples = [
        RequestSample(10.0, 200, True, "stable", False),
        RequestSample(20.0, 200, True, "canary", False),
        RequestSample(30.0, 503, False, None, False),
        RequestSample(40.0, 200, True, "stable", True),
    ]

    summary = summarize(samples, elapsed_seconds=2.0)

    assert summary["requests"] == 4
    assert summary["successes"] == 3
    assert summary["failures"] == 1
    assert summary["error_rate"] == 0.25
    assert summary["requests_per_second"] == 2.0
    assert summary["latency_ms"]["p50"] == 25.0
    assert summary["traffic_lanes"] == {
        "canary": 1,
        "stable": 2,
    }
    assert summary["canary_fallbacks"] == 1
    assert summary["status_codes"] == {
        "200": 3,
        "503": 1,
    }
