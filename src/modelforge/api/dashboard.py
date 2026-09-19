"""Public landing page and authenticated browser console for ModelForge."""

from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)


def _page(name: str) -> HTMLResponse:
    html = (
        files("modelforge.dashboard")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
    return HTMLResponse(html)


@router.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    """Serve the public ModelForge product landing page."""

    return _page("landing.html")


@router.get("/app", response_class=RedirectResponse)
def app_redirect() -> RedirectResponse:
    """Keep a concise product URL for the browser console."""

    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Serve the bundled ModelForge SaaS console."""

    return _page("index.html")
