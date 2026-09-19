"""Tests for the seeded demo contract."""

import json
from pathlib import Path

from demo.bootstrap_demo import MODEL_DIR


def test_demo_artifacts_are_distinct_linear_models() -> None:
    stable = json.loads((MODEL_DIR / "stable.json").read_text())
    canary = json.loads((MODEL_DIR / "canary.json").read_text())

    assert stable["operation"] == "linear"
    assert canary["operation"] == "linear"
    assert stable != canary

    input_value = 10
    stable_output = stable["weight"] * input_value + stable["bias"]
    canary_output = canary["weight"] * input_value + canary["bias"]

    assert stable_output == 21.0
    assert canary_output == 24.5
