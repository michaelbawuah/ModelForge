"""Tests for hosted production verification."""

from __future__ import annotations

import json

import httpx
import pytest

from modelforge.hosted_verify import verify_hosted_release

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self';"
    ),
}


def hosted_transport(
    *,
    runtime_status: str = "healthy",
    metrics_status: int = 401,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        authorized = request.headers.get("Authorization") == "Bearer mf_live_test"
        workspace = request.headers.get("X-ModelForge-Workspace")

        if path == "/health":
            return httpx.Response(200, json={"status": "healthy"}, request=request)
        if path == "/ready":
            return httpx.Response(200, json={"status": "ready"}, request=request)
        if path == "/auth/config":
            return httpx.Response(
                200,
                json={
                    "mode": "oidc",
                    "browser_login_enabled": True,
                    "login_url": "/auth/login",
                },
                request=request,
            )
        if path == "/":
            return httpx.Response(
                200,
                text="<html><title>ModelForge</title></html>",
                headers=SECURITY_HEADERS,
                request=request,
            )
        if path == "/metrics":
            return httpx.Response(
                metrics_status,
                json={"detail": "Metrics authentication required."},
                request=request,
            )
        if path == "/auth/me":
            if not authorized:
                return httpx.Response(
                    401,
                    json={"detail": "Authentication is required."},
                    request=request,
                )
            return httpx.Response(
                200,
                json={
                    "auth_type": "api_key",
                    "workspace_id": 9,
                    "workspace_slug": workspace,
                    "role": "developer",
                },
                request=request,
            )
        if path == "/models":
            return httpx.Response(200, json=[], request=request)
        if path == "/deployments":
            return httpx.Response(200, json=[], request=request)
        if path == "/runtimes":
            return httpx.Response(
                200,
                json={
                    "in_process": [
                        {"framework": "modelforge-json", "mode": "in_process"}
                    ],
                    "external": [
                        {
                            "framework": "go-linear",
                            "mode": "external",
                            "runtime": "modelforge-go-runtime",
                            "circuit_state": "closed",
                            "consecutive_failures": 0,
                        }
                    ],
                },
                request=request,
            )
        if path == "/runtimes/health":
            return httpx.Response(
                200,
                json={
                    "external": [
                        {
                            "framework": "go-linear",
                            "runtime": "modelforge-go-runtime",
                            "status": runtime_status,
                            "circuit_state": "closed",
                            "consecutive_failures": 0,
                        }
                    ]
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)


def test_hosted_verifier_passes_secure_production_surface() -> None:
    report = verify_hosted_release(
        base_url="https://modelforge.example",
        api_key="mf_live_test",
        workspace="demo",
        transport=hosted_transport(),
    )

    assert report["status"] == "PASS"
    assert report["workspace"] == "demo"
    assert report["checks"]["auth_mode"] == "oidc"
    assert report["checks"]["unauthenticated_metrics_status"] == 401
    assert report["checks"]["runtime_inventory"]["external"] == 1
    assert report["checks"]["external_runtime_health"][0]["status"] == "healthy"
    assert "mf_live_test" not in json.dumps(report)


def test_hosted_verifier_rejects_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        verify_hosted_release(
            base_url="http://modelforge.example",
            api_key="mf_live_test",
            workspace="demo",
            transport=hosted_transport(),
        )


def test_hosted_verifier_requires_protected_metrics() -> None:
    with pytest.raises(RuntimeError, match="/metrics"):
        verify_hosted_release(
            base_url="https://modelforge.example",
            api_key="mf_live_test",
            workspace="demo",
            transport=hosted_transport(metrics_status=200),
        )


def test_hosted_verifier_rejects_unhealthy_external_runtime() -> None:
    with pytest.raises(RuntimeError, match="runtime health"):
        verify_hosted_release(
            base_url="https://modelforge.example",
            api_key="mf_live_test",
            workspace="demo",
            transport=hosted_transport(runtime_status="unavailable"),
        )
