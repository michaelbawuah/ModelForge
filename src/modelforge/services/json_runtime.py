"""Small deterministic JSON runtime used to exercise ModelForge serving."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonModelRuntime:
    """Execute simple models described by immutable JSON artifacts."""

    def load(self, artifact_path: Path) -> dict[str, Any]:
        """Deserialize and validate a JSON model artifact."""

        with artifact_path.open(encoding="utf-8") as artifact_file:
            model = json.load(artifact_file)

        operation = model.get("operation")

        if operation != "linear":
            raise ValueError(
                f"Unsupported JSON model operation: {operation!r}."
            )

        weight = model.get("weight")
        bias = model.get("bias")

        if not isinstance(weight, (int, float)):
            raise ValueError("JSON model weight must be numeric.")

        if not isinstance(bias, (int, float)):
            raise ValueError("JSON model bias must be numeric.")

        return model

    def predict(
        self,
        model: dict[str, Any],
        inputs: Any,
    ) -> float | list[float]:
        """Execute y = weight * x + bias."""

        weight = float(model["weight"])
        bias = float(model["bias"])

        if isinstance(inputs, (int, float)):
            return weight * float(inputs) + bias

        if isinstance(inputs, list) and all(
            isinstance(value, (int, float))
            for value in inputs
        ):
            return [
                weight * float(value) + bias
                for value in inputs
            ]

        raise ValueError(
            "Linear JSON models require a number or a list of numbers."
        )