"""Browser dashboard for ModelForge."""

from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=RedirectResponse)
def root() -> RedirectResponse:
    """Send humans to the operational dashboard."""

    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Serve the bundled ModelForge control-plane dashboard."""

    html = (
        files("modelforge.dashboard")
        .joinpath("index.html")
        .read_text(encoding="utf-8")
    )
    return HTMLResponse(html)
