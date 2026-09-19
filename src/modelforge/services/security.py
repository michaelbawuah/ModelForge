"""Production HTTP security middleware for ModelForge."""

from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, Response


class RequestSecurityMiddleware(BaseHTTPMiddleware):
    """Attach request IDs, reject oversized requests, and add security headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id

        maximum = int(
            os.getenv(
                "MODELFORGE_MAX_REQUEST_BYTES",
                str(1024 * 1024 * 1024),
            )
        )
        raw_length = request.headers.get("Content-Length")

        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                return JSONResponse(
                    {"detail": "Invalid Content-Length header."},
                    status_code=400,
                )

            if content_length > maximum:
                return JSONResponse(
                    {"detail": "Request body exceeds configured size limit."},
                    status_code=413,
                )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        if request.url.path.startswith(("/docs", "/redoc")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self';"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "style-src 'self'; "
                "script-src 'self'; "
                "connect-src 'self'; "
                "img-src 'self' data:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )

        forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
        if request.url.scheme == "https" or forwarded_proto == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response


def configure_security(app: FastAPI) -> None:
    """Configure host validation, CORS, and response hardening."""

    app.add_middleware(RequestSecurityMiddleware)

    raw_hosts = os.getenv("MODELFORGE_TRUSTED_HOSTS", "*")
    hosts = [host.strip() for host in raw_hosts.split(",") if host.strip()]
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=hosts or ["*"],
    )

    raw_origins = os.getenv("MODELFORGE_CORS_ORIGINS", "")
    origins = [
        origin.strip()
        for origin in raw_origins.split(",")
        if origin.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-ModelForge-CSRF",
                "X-ModelForge-Workspace",
                "X-Request-ID",
            ],
        )
