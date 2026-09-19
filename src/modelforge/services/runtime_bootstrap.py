"""Runtime registry construction for ModelForge."""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec

from modelforge.services.json_runtime import JsonModelRuntime
from modelforge.services.runtimes import RuntimeRegistry


def create_runtime_registry(
    *,
    discover_plugins: bool = True,
) -> RuntimeRegistry:
    """Create the runtime registry used by ModelForge inference."""

    registry = RuntimeRegistry()
    registry.register("modelforge-json", JsonModelRuntime())

    if find_spec("onnxruntime") is not None and find_spec("numpy") is not None:
        module = import_module("modelforge.services.onnx_runtime")
        registry.register("onnx", module.OnnxRuntime())

    if find_spec("torch") is not None:
        module = import_module("modelforge.services.pytorch_runtime")
        registry.register("pytorch", module.PyTorchRuntime())

    if discover_plugins:
        registry.discover_plugins()

    return registry
