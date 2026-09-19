"""Public landing page and authenticated browser console for ModelForge."""

from importlib.resources import files

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

router = APIRouter(include_in_schema=False)

_ASSETS = {
    "dashboard.css": "text/css",
    "dashboard.js": "application/javascript",
    "landing.css": "text/css",
}


def _page_text(name: str) -> str:
    return (
        files("modelforge.dashboard")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def _page(name: str) -> HTMLResponse:
    return HTMLResponse(_page_text(name))


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


@router.get("/assets/{asset_name}")
def dashboard_asset(asset_name: str) -> Response:
    """Serve allowlisted packaged browser assets."""

    media_type = _ASSETS.get(asset_name)
    if media_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )

    return Response(
        _page_text(asset_name),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )
