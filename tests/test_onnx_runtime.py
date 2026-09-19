"""Tests for the ModelForge ONNX runtime."""

from __future__ import annotations

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper

from modelforge.services.onnx_runtime import (
    OnnxArtifactError,
    OnnxRuntime,
)

TEST_ONNX_OPSET = 18


def _write_linear_onnx_model(path) -> None:
    """Write y = xW + b as a real ONNX graph."""

    input_info = helper.make_tensor_value_info(
        "input",
        TensorProto.FLOAT,
        [None, 2],
    )

    output_info = helper.make_tensor_value_info(
        "output",
        TensorProto.FLOAT,
        [None, 1],
    )

    weight = numpy_helper.from_array(
        np.array(
            [
                [2.0],
                [3.0],
            ],
            dtype=np.float32,
        ),
        name="weight",
    )

    bias = numpy_helper.from_array(
        np.array(
            [1.0],
            dtype=np.float32,
        ),
        name="bias",
    )

    matmul = helper.make_node(
        "MatMul",
        inputs=["input", "weight"],
        outputs=["weighted"],
    )

    add = helper.make_node(
        "Add",
        inputs=["weighted", "bias"],
        outputs=["output"],
    )

    graph = helper.make_graph(
        [matmul, add],
        "linear-model",
        [input_info],
        [output_info],
        initializer=[weight, bias],
    )

    model = helper.make_model(
        graph,
        producer_name="modelforge-tests",
        opset_imports=[
            helper.make_operatorsetid(
                "",
                TEST_ONNX_OPSET,
            )
        ],
    )

    model.ir_version = 13
    onnx.checker.check_model(model)
    onnx.save(model, path)


def test_onnx_runtime_loads_and_predicts(tmp_path) -> None:
    artifact = tmp_path / "model.onnx"
    _write_linear_onnx_model(artifact)

    runtime = OnnxRuntime()
    model = runtime.load(artifact)

    prediction = runtime.predict(
        model,
        [[4.0, 5.0]],
    )

    assert prediction == pytest.approx(24.0)


def test_onnx_runtime_supports_batched_inputs(tmp_path) -> None:
    artifact = tmp_path / "model.onnx"
    _write_linear_onnx_model(artifact)

    runtime = OnnxRuntime()
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


def test_onnx_runtime_rejects_invalid_artifact(tmp_path) -> None:
    artifact = tmp_path / "bad.onnx"
    artifact.write_bytes(b"this is not an ONNX model")

    with pytest.raises(
        OnnxArtifactError,
        match="Unable to load ONNX artifact",
    ):
        OnnxRuntime().load(artifact)


def test_onnx_runtime_rejects_invalid_inputs(tmp_path) -> None:
    artifact = tmp_path / "model.onnx"
    _write_linear_onnx_model(artifact)

    runtime = OnnxRuntime()
    model = runtime.load(artifact)

    with pytest.raises(ValueError, match="numeric"):
        runtime.predict(
            model,
            {"invalid": "input"},
        )