"""Prometheus metrics endpoint."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, HTTPException, Request, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

router = APIRouter(tags=["observability"])


def _authorize_metrics(request: Request) -> None:
    expected = os.getenv("MODELFORGE_METRICS_TOKEN", "").strip()
    if not expected:
        return

    supplied = request.headers.get("Authorization", "")
    scheme, _, token = supplied.partition(" ")

    if (
        scheme.lower() != "bearer"
        or not token
        or not hmac.compare_digest(token, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Metrics authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    """Expose ModelForge metrics in Prometheus text format."""

    _authorize_metrics(request)
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
