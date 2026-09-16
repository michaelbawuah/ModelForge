"""Runtime registry construction for ModelForge."""

from __future__ import annotations

from modelforge.services.json_runtime import JsonModelRuntime
from modelforge.services.onnx_runtime import OnnxRuntime
from modelforge.services.pytorch_runtime import PyTorchRuntime
from modelforge.services.runtimes import RuntimeRegistry


def create_runtime_registry(
    *,
    discover_plugins: bool = True,
) -> RuntimeRegistry:
    """Create the runtime registry used by ModelForge inference."""

    registry = RuntimeRegistry()

    registry.register(
        "modelforge-json",
        JsonModelRuntime(),
    )
    registry.register(
        "onnx",
        OnnxRuntime(),
    )
    registry.register(
        "pytorch",
        PyTorchRuntime(),
    )

    if discover_plugins:
        registry.discover_plugins()

    return registry