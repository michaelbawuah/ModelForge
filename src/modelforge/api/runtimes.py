"""Operational inspection endpoints for ModelForge runtimes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from modelforge.api.inference import (
    get_external_runtime_registry,
    get_runtime_registry,
)
from modelforge.services.auth import Principal, get_principal
from modelforge.services.external_runtimes import (
    ExternalRuntimeCircuitOpenError,
    ExternalRuntimeError,
)

router = APIRouter(prefix="/runtimes", tags=["runtimes"])
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


@router.get("")
def list_runtimes(
    principal: CurrentPrincipal,
) -> dict[str, list[dict[str, object]]]:
    """List configured runtime inventory for an authenticated caller."""

    _ = principal
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
def runtime_health(
    principal: CurrentPrincipal,
) -> dict[str, list[dict[str, object]]]:
    """Probe external runtimes for an authenticated caller."""

    _ = principal
    runtimes: list[dict[str, object]] = []

    for framework, client in get_external_runtime_registry().items():
        runtime_status = "unhealthy"

        try:
            if client.health():
                runtime_status = "healthy"
        except ExternalRuntimeCircuitOpenError:
            runtime_status = "circuit_open"
        except ExternalRuntimeError:
            runtime_status = "unavailable"

        snapshot = client.circuit_snapshot()
        runtimes.append(
            {
                "framework": framework,
                "runtime": client.spec.name,
                "status": runtime_status,
                "circuit_state": snapshot.state,
                "consecutive_failures": snapshot.consecutive_failures,
            }
        )

    return {"external": runtimes}
