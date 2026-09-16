"""ONNX Runtime inference support for ModelForge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort


class OnnxArtifactError(ValueError):
    """Raised when an ONNX artifact cannot be loaded safely."""


class OnnxRuntime:
    """Load and execute ONNX models through ONNX Runtime."""

    def load(self, artifact_path: Path) -> ort.InferenceSession:
        """Create an inference session for an immutable ONNX artifact."""

        try:
            return ort.InferenceSession(
                str(artifact_path),
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise OnnxArtifactError(
                "Unable to load ONNX artifact."
            ) from exc

    def predict(
        self,
        model: ort.InferenceSession,
        inputs: Any,
    ) -> Any:
        """Run inference using JSON-compatible numeric inputs."""

        model_inputs = model.get_inputs()

        if len(model_inputs) != 1:
            raise ValueError(
                "ModelForge ONNX runtime currently supports "
                "single-input models."
            )

        input_name = model_inputs[0].name

        try:
            tensor = np.asarray(inputs, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ONNX inputs must be numeric and tensor-compatible."
            ) from exc

        if tensor.ndim == 0:
            raise ValueError(
                "ONNX inputs must include a feature dimension."
            )

        try:
            outputs = model.run(
                None,
                {
                    input_name: tensor,
                },
            )
        except Exception as exc:
            raise ValueError(
                "ONNX inference failed for the supplied inputs."
            ) from exc

        if len(outputs) != 1:
            raise ValueError(
                "ModelForge ONNX runtime currently supports "
                "single-output models."
            )

        output = np.asarray(outputs[0])

        if output.size == 1:
            return float(output.item())

        return output.tolist()