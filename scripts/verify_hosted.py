"""Verify that a public ModelForge deployment is production-ready."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


def _expect_status(
    response: httpx.Response,
    expected: int,
    *,
    label: str,
) -> Any:
    if response.status_code != expected:
        raise RuntimeError(
            f"{label} returned HTTP {response.status_code}: {response.text}"
        )
    if not response.content:
        return None
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    return response.text


def _require_header(
    response: httpx.Response,
    name: str,
    expected: str | None = None,
) -> str:
    value = response.headers.get(name)
    if not value:
        raise RuntimeError(f"Missing required security header: {name}.")
    if expected is not None and value != expected:
        raise RuntimeError(
            f"Security header {name} was {value!r}; expected {expected!r}."
        )
    return value


def verify_hosted_release(
    *,
    base_url: str,
    api_key: str,
    workspace: str,
    timeout_seconds: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Verify public security, auth, tenancy, runtime health, and readiness."""

    normalized_url = base_url.rstrip("/")
    parsed = httpx.URL(normalized_url)
    if parsed.scheme != "https":
        raise ValueError("Hosted ModelForge verification requires an HTTPS URL.")
    if not parsed.host:
        raise ValueError("Hosted ModelForge verification requires a public host.")
    if not api_key.startswith("mf_live_"):
        raise ValueError("Hosted verification requires a ModelForge API key.")
    if not workspace.strip():
        raise ValueError("Hosted verification requires a workspace selector.")

    started_at = datetime.now(UTC)
    common = {
        "base_url": normalized_url,
        "timeout": timeout_seconds,
        "transport": transport,
        "follow_redirects": False,
    }

    with httpx.Client(**common) as public_client:
        health = _expect_status(public_client.get("/health"), 200, label="health")
        readiness = _expect_status(
            public_client.get("/ready"), 200, label="readiness"
        )
        auth_config = _expect_status(
            public_client.get("/auth/config"), 200, label="auth config"
        )
        landing_response = public_client.get("/")
        landing = _expect_status(
            landing_response, 200, label="public landing page"
        )
        unauthenticated_identity = public_client.get("/auth/me")
        metrics_without_token = public_client.get("/metrics")

    if health.get("status") != "healthy":
        raise RuntimeError(f"Unexpected health payload: {health!r}")
    if readiness.get("status") != "ready":
        raise RuntimeError(f"Unexpected readiness payload: {readiness!r}")
    if auth_config.get("mode") != "oidc":
        raise RuntimeError("Hosted deployment is not running in OIDC auth mode.")
    if auth_config.get("browser_login_enabled") is not True:
        raise RuntimeError("Hosted browser login is not enabled.")
    if "ModelForge" not in landing:
        raise RuntimeError("Public landing page did not identify ModelForge.")
    if unauthenticated_identity.status_code != 401:
        raise RuntimeError(
            "/auth/me must reject unauthenticated hosted requests with HTTP 401."
        )
    if metrics_without_token.status_code != 401:
        raise RuntimeError("/metrics must require a bearer token in production.")

    hsts = _require_header(landing_response, "strict-transport-security")
    if "max-age=31536000" not in hsts or "includeSubDomains" not in hsts:
        raise RuntimeError("Hosted HSTS policy is weaker than the production baseline.")
    _require_header(landing_response, "x-content-type-options", "nosniff")
    _require_header(landing_response, "x-frame-options", "DENY")
    csp = _require_header(landing_response, "content-security-policy")
    if "script-src 'self'" not in csp or "style-src 'self'" not in csp:
        raise RuntimeError("Hosted CSP does not restrict scripts/styles to self.")
    if "'unsafe-inline'" in csp:
        raise RuntimeError("Hosted product CSP unexpectedly permits unsafe inline code.")

    authenticated_headers = {
        "Authorization": f"Bearer {api_key}",
        "X-ModelForge-Workspace": workspace,
    }
    with httpx.Client(**common, headers=authenticated_headers) as authenticated_client:
        identity = _expect_status(
            authenticated_client.get("/auth/me"),
            200,
            label="authenticated identity",
        )
        models = _expect_status(
            authenticated_client.get("/models"), 200, label="model registry"
        )
        deployments = _expect_status(
            authenticated_client.get("/deployments"), 200, label="deployments"
        )
        runtimes = _expect_status(
            authenticated_client.get("/runtimes"), 200, label="runtime inventory"
        )
        runtime_health = _expect_status(
            authenticated_client.get("/runtimes/health"),
            200,
            label="runtime health",
        )

    if identity.get("auth_type") != "api_key":
        raise RuntimeError("Hosted API-key request did not authenticate as api_key.")
    if identity.get("workspace_slug") != workspace:
        raise RuntimeError(
            "Hosted API key resolved to a different workspace than requested."
        )

    external_inventory = runtimes.get("external") or []
    if not external_inventory:
        raise RuntimeError("Hosted deployment exposes no external runtime.")
    external_health = runtime_health.get("external") or []
    if not external_health:
        raise RuntimeError("Hosted deployment returned no external runtime health.")

    unhealthy = [
        runtime
        for runtime in external_health
        if runtime.get("status") != "healthy"
    ]
    if unhealthy:
        raise RuntimeError(
            "Hosted external runtime health is not fully green: "
            + json.dumps(unhealthy, sort_keys=True)
        )

    finished_at = datetime.now(UTC)
    return {
        "status": "PASS",
        "base_url": normalized_url,
        "workspace": workspace,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "checks": {
            "health": health.get("status"),
            "readiness": readiness.get("status"),
            "auth_mode": auth_config.get("mode"),
            "browser_login_enabled": auth_config.get("browser_login_enabled"),
            "unauthenticated_identity_status": unauthenticated_identity.status_code,
            "unauthenticated_metrics_status": metrics_without_token.status_code,
            "hsts": hsts,
            "content_security_policy": csp,
            "identity": {
                "auth_type": identity.get("auth_type"),
                "workspace_slug": identity.get("workspace_slug"),
                "role": identity.get("role"),
            },
            "models_visible": len(models),
            "deployments_visible": len(deployments),
            "runtime_inventory": {
                "in_process": len(runtimes.get("in_process") or []),
                "external": len(external_inventory),
            },
            "external_runtime_health": external_health,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a hosted ModelForge production deployment.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("MODELFORGE_URL"),
        required=os.getenv("MODELFORGE_URL") is None,
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MODELFORGE_API_KEY"),
        required=os.getenv("MODELFORGE_API_KEY") is None,
    )
    parser.add_argument(
        "--workspace",
        default=os.getenv("MODELFORGE_WORKSPACE"),
        required=os.getenv("MODELFORGE_WORKSPACE") is None,
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("hosted-release-evidence.json"),
    )
    args = parser.parse_args()

    report = verify_hosted_release(
        base_url=args.base_url,
        api_key=args.api_key,
        workspace=args.workspace,
        timeout_seconds=args.timeout_seconds,
    )
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
