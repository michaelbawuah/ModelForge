"""HTTP entry point for the ModelForge control plane."""

import os

from fastapi import FastAPI

from modelforge.api.browser_auth import router as browser_auth_router
from modelforge.api.dashboard import router as dashboard_router
from modelforge.api.deployment_targets import router as deployment_target_router
from modelforge.api.deployments import router as deployment_router
from modelforge.api.identity import router as identity_router
from modelforge.api.inference import router as inference_router
from modelforge.api.metrics import router as metrics_router
from modelforge.api.registry import router as registry_router
from modelforge.api.runtimes import router as runtime_router
from modelforge.api.system import router as system_router
from modelforge.core.config import validate_deployment_config
from modelforge.services.security import configure_security


def create_app() -> FastAPI:
    """Create and configure the ModelForge API application."""

    validate_deployment_config()

    app = FastAPI(
        title="ModelForge",
        version="0.1.0",
        description="Reliability-aware ML deployment platform.",
    )
    configure_security(app)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Report whether the API process is alive."""

        return {
            "status": "healthy",
            "service": "modelforge-api",
            "build_sha": os.getenv("MODELFORGE_BUILD_SHA", "unknown"),
        }

    app.include_router(dashboard_router)
    app.include_router(browser_auth_router)
    app.include_router(identity_router)
    app.include_router(registry_router)
    app.include_router(deployment_router)
    app.include_router(deployment_target_router)
    app.include_router(inference_router)
    app.include_router(metrics_router)
    app.include_router(runtime_router)
    app.include_router(system_router)
    return app


app = create_app()
