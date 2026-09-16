"""Tests for the deterministic JSON inference runtime."""

import json

import pytest

from modelforge.services.json_runtime import JsonModelRuntime


def test_json_runtime_loads_and_predicts(tmp_path) -> None:
    artifact = tmp_path / "model.json"
    artifact.write_text(
        json.dumps(
            {
                "operation": "linear",
                "weight": 2.0,
                "bias": 1.0,
            }
        ),
        encoding="utf-8",
    )

    runtime = JsonModelRuntime()
    model = runtime.load(artifact)

    assert runtime.predict(model, 3.0) == 7.0
    assert runtime.predict(model, [1.0, 2.0]) == [3.0, 5.0]


def test_json_runtime_rejects_unknown_operation(tmp_path) -> None:
    artifact = tmp_path / "model.json"
    artifact.write_text(
        json.dumps(
            {
                "operation": "mystery",
                "weight": 2.0,
                "bias": 1.0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported"):
        JsonModelRuntime().load(artifact)


def test_json_runtime_rejects_invalid_inputs(tmp_path) -> None:
    artifact = tmp_path / "model.json"
    artifact.write_text(
        json.dumps(
            {
                "operation": "linear",
                "weight": 2.0,
                "bias": 1.0,
            }
        ),
        encoding="utf-8",
    )

    runtime = JsonModelRuntime()
    model = runtime.load(artifact)

    with pytest.raises(ValueError, match="number"):
        runtime.predict(model, {"bad": "input"})