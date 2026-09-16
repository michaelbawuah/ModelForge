"""Tests for the ModelForge PyTorch runtime."""

from __future__ import annotations

import pytest
import torch

from modelforge.services.pytorch_runtime import (
    LinearModel,
    PyTorchArtifactError,
    PyTorchRuntime,
)


def _write_linear_artifact(
    path,
    *,
    weight: list[list[float]],
    bias: list[float],
) -> None:
    model = LinearModel(
        input_features=len(weight[0]),
        output_features=len(weight),
    )

    with torch.no_grad():
        model.linear.weight.copy_(
            torch.tensor(weight, dtype=torch.float32)
        )
        model.linear.bias.copy_(
            torch.tensor(bias, dtype=torch.float32)
        )

    torch.save(
        {
            "format_version": 1,
            "architecture": "linear",
            "config": {
                "input_features": len(weight[0]),
                "output_features": len(weight),
            },
            "state_dict": model.state_dict(),
        },
        path,
    )


def test_pytorch_runtime_loads_and_predicts(tmp_path) -> None:
    artifact = tmp_path / "model.pt"

    _write_linear_artifact(
        artifact,
        weight=[[2.0, 3.0]],
        bias=[1.0],
    )

    runtime = PyTorchRuntime()
    model = runtime.load(artifact)

    assert runtime.predict(model, [4.0, 5.0]) == pytest.approx(24.0)


def test_pytorch_runtime_supports_batched_inputs(tmp_path) -> None:
    artifact = tmp_path / "model.pt"

    _write_linear_artifact(
        artifact,
        weight=[[2.0, 3.0]],
        bias=[1.0],
    )

    runtime = PyTorchRuntime()
    model = runtime.load(artifact)

    prediction = runtime.predict(
        model,
        [
            [1.0, 2.0],
            [3.0, 4.0],
        ],
    )

    assert len(prediction) == 2
    assert prediction[0] == pytest.approx([9.0])
    assert prediction[1] == pytest.approx([19.0])


def test_pytorch_runtime_rejects_unknown_architecture(tmp_path) -> None:
    artifact = tmp_path / "bad.pt"

    torch.save(
        {
            "format_version": 1,
            "architecture": "mystery-network",
            "config": {},
            "state_dict": {},
        },
        artifact,
    )

    with pytest.raises(
        PyTorchArtifactError,
        match="Unsupported PyTorch architecture",
    ):
        PyTorchRuntime().load(artifact)


def test_pytorch_runtime_rejects_invalid_inputs(tmp_path) -> None:
    artifact = tmp_path / "model.pt"

    _write_linear_artifact(
        artifact,
        weight=[[2.0]],
        bias=[1.0],
    )

    runtime = PyTorchRuntime()
    model = runtime.load(artifact)

    with pytest.raises(ValueError, match="numeric"):
        runtime.predict(model, {"bad": "input"})