"""Bounded database readiness probe used before startup migrations."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from time import sleep

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from modelforge.core.config import resolve_database_url

DEFAULT_ATTEMPTS = 30
DEFAULT_DELAY_SECONDS = 1.0


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return parsed


def _non_negative_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if parsed < 0:
        raise ValueError(f"{name} cannot be negative.")
    return parsed


def wait_for_database(
    database_url: str | None = None,
    *,
    attempts: int | None = None,
    delay_seconds: float | None = None,
    engine_factory: Callable[..., Engine] = create_engine,
    sleep_fn: Callable[[float], None] = sleep,
) -> int:
    """Wait until MySQL accepts a real query, returning the successful attempt."""

    resolved_url = database_url or resolve_database_url()

    resolved_attempts = attempts
    if resolved_attempts is None:
        resolved_attempts = _positive_int(
            os.getenv(
                "MODELFORGE_DB_STARTUP_ATTEMPTS",
                str(DEFAULT_ATTEMPTS),
            ),
            "MODELFORGE_DB_STARTUP_ATTEMPTS",
        )
    elif resolved_attempts <= 0:
        raise ValueError("attempts must be greater than zero.")

    resolved_delay = delay_seconds
    if resolved_delay is None:
        resolved_delay = _non_negative_float(
            os.getenv(
                "MODELFORGE_DB_STARTUP_DELAY_SECONDS",
                str(DEFAULT_DELAY_SECONDS),
            ),
            "MODELFORGE_DB_STARTUP_DELAY_SECONDS",
        )
    elif resolved_delay < 0:
        raise ValueError("delay_seconds cannot be negative.")

    engine = engine_factory(
        resolved_url,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    last_error: SQLAlchemyError | None = None

    try:
        for attempt in range(1, resolved_attempts + 1):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                return attempt
            except SQLAlchemyError as exc:
                last_error = exc
                if attempt < resolved_attempts and resolved_delay > 0:
                    sleep_fn(resolved_delay)
    finally:
        engine.dispose()

    raise RuntimeError(
        "Database did not become reachable before the startup deadline."
    ) from last_error


def main() -> int:
    """Run the bounded readiness probe without printing connection secrets."""

    try:
        attempt = wait_for_database()
    except (RuntimeError, ValueError) as exc:
        print(f"ModelForge database readiness failed: {exc}", file=sys.stderr)
        return 1

    print(f"ModelForge database ready after {attempt} attempt(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
