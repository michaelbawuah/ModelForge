"""Focused tests for hosted-demo proof helpers."""

import pytest

from demo.hosted_lifecycle import (
    HostedDemoError,
    _assert_prediction,
    _render_markdown,
)


def test_prediction_proof_checks_lane_version_and_output() -> None:
    _assert_prediction(
        {
            "traffic_lane": "canary",
            "model_version": "4.0.0",
            "prediction": 21.0,
        },
        expected_lane="canary",
        expected_version="4.0.0",
        expected_output=21.0,
    )


def test_prediction_proof_rejects_wrong_model_output() -> None:
    with pytest.raises(HostedDemoError, match="Unexpected prediction"):
        _assert_prediction(
            {
                "traffic_lane": "canary",
                "model_version": "2.0.0",
                "prediction": 24.5,
            },
            expected_lane="canary",
            expected_version="2.0.0",
            expected_output=21.0,
        )


def test_markdown_evidence_contains_final_visible_canary() -> None:
    evidence = {
        "generated_at": "2026-09-19T20:00:00+00:00",
        "public_url": "https://modelforge.example",
        "dashboard_url": "https://modelforge.example/dashboard",
        "environment": "recruiter-demo",
        "identity": {"workspace_slug": "recruiter-demo"},
        "model": {"name": "proof-model"},
        "timeline": [{"step": "Rollback to v1", "result": "v1 ACTIVE"}],
        "traffic_samples": {
            key: {
                "requests": 40,
                "stable_requests": 30,
                "canary_requests": 10,
                "observed_canary_percent": 25.0,
            }
            for key in (
                "regression_canary",
                "good_canary",
                "final_visible_canary",
            )
        },
        "final_target": {
            "active_deployment_id": 11,
            "canary_deployment_id": 14,
            "canary_weight": 25,
        },
    }

    markdown = _render_markdown(evidence)

    assert "ModelForge Hosted Demo Evidence" in markdown
    assert "Rollback to v1" in markdown
    assert "Canary deployment: #14" in markdown
    assert "Canary traffic: 25%" in markdown
