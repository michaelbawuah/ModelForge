"""Unit tests for the recruiter-visible deployment proof harness."""

from __future__ import annotations

import math

from demo.proof_scenario import (
    auth_headers,
    relative_drift,
    render_markdown,
    summarize_traffic,
)


def test_auth_headers_support_hosted_workspace_api_keys() -> None:
    headers = auth_headers(
        api_key="mf_live_test-secret",
        workspace="team-ml",
    )

    assert headers == {
        "Authorization": "Bearer mf_live_test-secret",
        "X-ModelForge-Workspace": "team-ml",
    }


def test_relative_drift_handles_normal_and_zero_baselines() -> None:
    assert relative_drift(20.0, 30.0) == 0.5
    assert relative_drift(0.0, 0.0) == 0.0
    assert math.isinf(relative_drift(0.0, 1.0))


def test_summarize_traffic_reports_lanes_versions_and_fallbacks() -> None:
    summary = summarize_traffic(
        [
            {
                "traffic_lane": "stable",
                "model_version": "1.0.0",
                "canary_fallback": False,
            },
            {
                "traffic_lane": "canary",
                "model_version": "2.0.0",
                "canary_fallback": False,
            },
            {
                "traffic_lane": "stable",
                "model_version": "1.0.0",
                "canary_fallback": True,
            },
        ]
    )

    assert summary == {
        "requests": 3,
        "traffic_lanes": {
            "canary": 1,
            "stable": 2,
        },
        "model_versions": {
            "1.0.0": 2,
            "2.0.0": 1,
        },
        "canary_fallbacks": 1,
    }


def test_render_markdown_surfaces_progressive_delivery_evidence() -> None:
    summary = {
        "status": "PASS",
        "checks": {
            "health": "healthy",
            "readiness": "ready",
            "stable_baseline": {"prediction": 21.0},
            "candidate_canary": {
                "weight_percent": 50,
                "traffic": {
                    "requests": 12,
                    "traffic_lanes": {"stable": 6, "canary": 6},
                    "model_versions": {"1.0.0": 6, "2.0.0": 6},
                    "canary_fallbacks": 0,
                },
            },
            "promotion": {
                "state": "ACTIVE",
                "prediction": 24.5,
            },
            "rollback": {
                "restored_version": "1.0.0",
                "prediction": 21.0,
            },
            "regression_canary": {
                "relative_drift": 1.857,
                "threshold": 0.5,
                "traffic": {
                    "requests": 10,
                    "traffic_lanes": {"stable": 5, "canary": 5},
                    "model_versions": {"1.0.0": 5, "3.0.0": 5},
                    "canary_fallbacks": 0,
                },
            },
            "abort": {
                "state": "FAILED",
                "failure_reason": "Regression threshold exceeded.",
            },
            "final_target": {
                "version": "1.0.0",
            },
        },
    }

    report = render_markdown(summary)

    assert "stable → canary → promote → rollback" in report
    assert "FAILED" in report
    assert "v1.0.0" in report
