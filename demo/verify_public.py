"""Verify a hosted ModelForge deployment's public product and security edge."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"


class PublicVerificationError(RuntimeError):
    """Raised when a hosted ModelForge deployment fails a proof check."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicVerificationError(message)


def verify_public_deployment(
    client: httpx.Client,
    *,
    require_https: bool,
    require_oidc: bool,
) -> dict[str, Any]:
    """Verify public product, readiness, auth mode, and security headers."""

    origin = str(client.base_url).rstrip("/")
    parsed = urlsplit(origin)

    if require_https:
        _require(
            parsed.scheme == "https",
            "Hosted ModelForge verification requires an HTTPS public URL.",
        )

    landing = client.get("/")
    landing.raise_for_status()
    _require(
        "Deploy any model." in landing.text,
        "Public landing page did not contain the expected ModelForge product copy.",
    )

    health = client.get("/health")
    health.raise_for_status()
    health_payload = health.json()
    _require(
        health_payload.get("status") == "healthy",
        "ModelForge /health did not report healthy.",
    )

    ready = client.get("/ready")
    ready.raise_for_status()
    ready_payload = ready.json()
    _require(
        ready_payload.get("status") == "ready",
        "ModelForge /ready did not report ready.",
    )

    auth = client.get("/auth/config")
    auth.raise_for_status()
    auth_payload = auth.json()
    if require_oidc:
        _require(
            auth_payload.get("mode") == "oidc",
            "Hosted ModelForge must report OIDC authentication mode.",
        )
        _require(
            auth_payload.get("browser_login_enabled") is True,
            "Hosted ModelForge browser login must be enabled.",
        )

    headers = {key.lower(): value for key, value in landing.headers.items()}
    csp = headers.get("content-security-policy", "")

    _require(
        headers.get("x-content-type-options") == "nosniff",
        "Missing X-Content-Type-Options hardening header.",
    )
    _require(
        headers.get("x-frame-options") == "DENY",
        "Missing X-Frame-Options DENY header.",
    )
    _require(
        headers.get("referrer-policy") == "no-referrer",
        "Missing Referrer-Policy hardening header.",
    )
    _require(
        "default-src 'self'" in csp,
        "Content Security Policy does not restrict default sources to self.",
    )
    _require(
        "script-src 'self'" in csp,
        "Content Security Policy does not restrict scripts to self.",
    )
    _require(
        "'unsafe-inline'" not in csp,
        "Public product CSP unexpectedly allows unsafe inline content.",
    )
    _require(
        bool(headers.get("x-request-id")),
        "Public response is missing a request ID.",
    )

    if require_https:
        _require(
            "max-age=" in headers.get("strict-transport-security", ""),
            "HTTPS deployment is missing Strict-Transport-Security.",
        )

    security_headers = {
        name: headers[name]
        for name in (
            "content-security-policy",
            "permissions-policy",
            "referrer-policy",
            "strict-transport-security",
            "x-content-type-options",
            "x-frame-options",
            "x-request-id",
        )
        if name in headers
    }

    return {
        "status": "passed",
        "public_url": origin,
        "health": health_payload,
        "readiness": ready_payload,
        "auth": auth_payload,
        "security_headers": security_headers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.getenv("MODELFORGE_PUBLIC_URL", DEFAULT_URL),
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--allow-auth-disabled", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with httpx.Client(
        base_url=args.base_url.rstrip("/") + "/",
        timeout=args.timeout_seconds,
        follow_redirects=True,
    ) as client:
        evidence = verify_public_deployment(
            client,
            require_https=not args.allow_http,
            require_oidc=not args.allow_auth_disabled,
        )

    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
