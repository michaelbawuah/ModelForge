"""Tests for hosted public-deployment verification."""

from __future__ import annotations

import httpx
import pytest

from demo.verify_public import (
    PublicVerificationError,
    verify_public_deployment,
)


def _response(
    request: httpx.Request,
    *,
    insecure_csp: bool = False,
) -> httpx.Response:
    common_headers = {
        "Content-Security-Policy": (
            "default-src 'self'; style-src 'self'; "
            + (
                "script-src 'self' 'unsafe-inline'; "
                if insecure_csp
                else "script-src 'self'; "
            )
            + "frame-ancestors 'none';"
        ),
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Referrer-Policy": "no-referrer",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Request-ID": "test-request-id",
    }

    if request.url.path == "/":
        return httpx.Response(
            200,
            text="<h1>Deploy any model.</h1>",
            headers=common_headers,
        )
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "healthy"})
    if request.url.path == "/ready":
        return httpx.Response(200, json={"status": "ready"})
    if request.url.path == "/auth/config":
        return httpx.Response(
            200,
            json={
                "mode": "oidc",
                "browser_login_enabled": True,
            },
        )
    return httpx.Response(404)


def test_public_verification_passes_for_hardened_hosted_product() -> None:
    transport = httpx.MockTransport(_response)

    with httpx.Client(
        base_url="https://modelforge.example/",
        transport=transport,
    ) as client:
        evidence = verify_public_deployment(
            client,
            require_https=True,
            require_oidc=True,
        )

    assert evidence["status"] == "passed"
    assert evidence["auth"]["mode"] == "oidc"
    assert evidence["security_headers"]["x-frame-options"] == "DENY"


def test_public_verification_rejects_http_when_https_is_required() -> None:
    transport = httpx.MockTransport(_response)

    with httpx.Client(
        base_url="http://modelforge.example/",
        transport=transport,
    ) as client:
        with pytest.raises(PublicVerificationError, match="HTTPS"):
            verify_public_deployment(
                client,
                require_https=True,
                require_oidc=True,
            )


def test_public_verification_rejects_unsafe_inline_csp() -> None:
    transport = httpx.MockTransport(
        lambda request: _response(request, insecure_csp=True)
    )

    with httpx.Client(
        base_url="https://modelforge.example/",
        transport=transport,
    ) as client:
        with pytest.raises(PublicVerificationError, match="unsafe inline"):
            verify_public_deployment(
                client,
                require_https=True,
                require_oidc=True,
            )
