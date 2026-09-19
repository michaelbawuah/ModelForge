"""Tests for the bounded startup database readiness probe."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy.exc import SQLAlchemyError

from modelforge.core.database_ready import wait_for_database


class FakeEngine:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.connect_calls = 0
        self.dispose_calls = 0

    @contextmanager
    def connect(self):
        self.connect_calls += 1
        if self.connect_calls <= self.failures:
            raise SQLAlchemyError("database unavailable")
        yield FakeConnection()

    def dispose(self) -> None:
        self.dispose_calls += 1


class FakeConnection:
    def execute(self, statement) -> None:
        assert str(statement) == "SELECT 1"


def test_database_readiness_retries_transient_connection_failures() -> None:
    engine = FakeEngine(failures=2)
    sleeps: list[float] = []

    attempt = wait_for_database(
        "mysql+pymysql://user:secret@db.internal/modelforge",
        attempts=5,
        delay_seconds=0.25,
        engine_factory=lambda *args, **kwargs: engine,
        sleep_fn=sleeps.append,
    )

    assert attempt == 3
    assert engine.connect_calls == 3
    assert engine.dispose_calls == 1
    assert sleeps == [0.25, 0.25]


def test_database_readiness_fails_after_bounded_attempts() -> None:
    engine = FakeEngine(failures=10)

    with pytest.raises(
        RuntimeError,
        match="startup deadline",
    ) as exc_info:
        wait_for_database(
            "mysql+pymysql://user:super-secret@db.internal/modelforge",
            attempts=3,
            delay_seconds=0,
            engine_factory=lambda *args, **kwargs: engine,
        )

    assert "super-secret" not in str(exc_info.value)
    assert engine.connect_calls == 3
    assert engine.dispose_calls == 1


@pytest.mark.parametrize(
    ("attempts", "delay_seconds"),
    [
        (0, 0),
        (-1, 0),
        (1, -0.1),
    ],
)
def test_database_readiness_rejects_invalid_bounds(
    attempts: int,
    delay_seconds: float,
) -> None:
    with pytest.raises(ValueError):
        wait_for_database(
            attempts=attempts,
            delay_seconds=delay_seconds,
        )
