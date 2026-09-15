"""HTTP entry point for the ModelForge control plane."""

from fastapi import FastAPI


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

    return app


app = create_app()
