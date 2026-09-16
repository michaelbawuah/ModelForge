"""Prometheus metrics endpoint."""

from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Expose ModelForge metrics in Prometheus text format."""

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )