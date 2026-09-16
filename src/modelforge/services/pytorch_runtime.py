"""PyTorch inference runtime for ModelForge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from torch import nn


class PyTorchArtifactError(ValueError):
    """Raised when a PyTorch artifact violates the runtime contract."""


class LinearModel(nn.Module):
    """Simple linear network used by the first PyTorch artifact contract."""

    def __init__(self, input_features: int, output_features: int) -> None:
        super().__init__()
        self.linear = nn.Linear(input_features, output_features)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.linear(inputs)


class PyTorchRuntime:
    """Load and execute ModelForge-compatible PyTorch artifacts."""

    def __init__(self, *, device: str = "cpu") -> None:
        self._device = torch.device(device)

    def load(self, artifact_path: Path) -> nn.Module:
        """Load a controlled state-dict artifact onto the configured device."""

        try:
            artifact = torch.load(
                artifact_path,
                map_location=self._device,
                weights_only=True,
            )
        except Exception as exc:
            raise PyTorchArtifactError(
                "Unable to load PyTorch artifact."
            ) from exc

        if not isinstance(artifact, dict):
            raise PyTorchArtifactError(
                "PyTorch artifact must contain a dictionary."
            )

        format_version = artifact.get("format_version")
        architecture = artifact.get("architecture")
        config = artifact.get("config")
        state_dict = artifact.get("state_dict")

        if format_version != 1:
            raise PyTorchArtifactError(
                f"Unsupported PyTorch artifact format version: "
                f"{format_version!r}."
            )

        if architecture != "linear":
            raise PyTorchArtifactError(
                f"Unsupported PyTorch architecture: {architecture!r}."
            )

        if not isinstance(config, dict):
            raise PyTorchArtifactError(
                "PyTorch artifact config must be a dictionary."
            )

        if not isinstance(state_dict, dict):
            raise PyTorchArtifactError(
                "PyTorch artifact state_dict must be a dictionary."
            )

        input_features = config.get("input_features")
        output_features = config.get("output_features")

        if (
            not isinstance(input_features, int)
            or isinstance(input_features, bool)
            or input_features <= 0
        ):
            raise PyTorchArtifactError(
                "input_features must be a positive integer."
            )

        if (
            not isinstance(output_features, int)
            or isinstance(output_features, bool)
            or output_features <= 0
        ):
            raise PyTorchArtifactError(
                "output_features must be a positive integer."
            )

        model = LinearModel(
            input_features=input_features,
            output_features=output_features,
        )

        try:
            model.load_state_dict(state_dict)
        except RuntimeError as exc:
            raise PyTorchArtifactError(
                "PyTorch state_dict does not match the declared architecture."
            ) from exc

        model.to(self._device)
        model.eval()

        return model

    def predict(
        self,
        model: nn.Module,
        inputs: Any,
    ) -> Any:
        """Convert JSON-compatible inputs to tensors and run inference."""

        try:
            tensor = torch.as_tensor(
                inputs,
                dtype=torch.float32,
                device=self._device,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "PyTorch inputs must be numeric and tensor-compatible."
            ) from exc

        if tensor.ndim == 0:
            raise ValueError(
                "PyTorch inputs must include a feature dimension."
            )

        with torch.inference_mode():
            output = model(tensor)

        result = output.detach().cpu()

        if result.numel() == 1:
            return float(result.item())

        return result.tolist()