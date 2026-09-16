"""HTTP entry point for the ModelForge control plane."""

from fastapi import FastAPI

from modelforge.api.deployment_targets import router as deployment_target_router
from modelforge.api.deployments import router as deployment_router
from modelforge.api.inference import router as inference_router
from modelforge.api.registry import router as registry_router


def create_app() -> FastAPI:
    """Create and configure the ModelForge API application."""

    app = FastAPI(
        title="ModelForge",
        version="0.1.0",
        description="Reliability-aware ML deployment platform.",
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Report whether the API process is alive."""

        return {
            "status": "healthy",
            "service": "modelforge-api",
        }

    app.include_router(registry_router)
    app.include_router(deployment_router)
    app.include_router(deployment_target_router)
    app.include_router(inference_router)
    return app


app = create_app()