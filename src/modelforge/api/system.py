"""Operational health endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from modelforge.db.session import get_db

router = APIRouter(tags=["system"])

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/ready")
def readiness(
    session: DatabaseSession,
) -> dict[str, str]:
    """Report whether critical dependencies are available."""

    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ModelForge is not ready.",
        ) from exc

    return {
        "status": "ready",
        "database": "reachable",
    }