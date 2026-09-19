"""Operational inspection endpoints for ModelForge runtimes."""

from __future__ import annotations

from fastapi import APIRouter

from modelforge.api.inference import (
    get_external_runtime_registry,
    get_runtime_registry,
)
from modelforge.services.external_runtimes import (
    ExternalRuntimeCircuitOpenError,
    ExternalRuntimeError,
)

router = APIRouter(prefix="/runtimes", tags=["runtimes"])


@router.get("")
def list_runtimes() -> dict[str, list[dict[str, object]]]:
    """List configured runtimes without making network calls."""

    in_process = [
        {"framework": framework, "mode": "in_process"}
        for framework in get_runtime_registry().frameworks()
    ]

    external: list[dict[str, object]] = []
    for framework, client in get_external_runtime_registry().items():
        snapshot = client.circuit_snapshot()
        external.append(
            {
                "framework": framework,
                "mode": "external",
                "runtime": client.spec.name,
                "circuit_state": snapshot.state,
                "consecutive_failures": snapshot.consecutive_failures,
            }
        )

    return {"in_process": in_process, "external": external}


@router.get("/health")
def runtime_health() -> dict[str, list[dict[str, object]]]:
    """Probe configured external runtimes and report their health."""

    runtimes: list[dict[str, object]] = []

    for framework, client in get_external_runtime_registry().items():
        status = "unhealthy"

        try:
            if client.health():
                status = "healthy"
        except ExternalRuntimeCircuitOpenError:
            status = "circuit_open"
        except ExternalRuntimeError:
            status = "unavailable"

        snapshot = client.circuit_snapshot()
        runtimes.append(
            {
                "framework": framework,
                "runtime": client.spec.name,
                "status": status,
                "circuit_state": snapshot.state,
                "consecutive_failures": snapshot.consecutive_failures,
            }
        )

    return {"external": runtimes}
