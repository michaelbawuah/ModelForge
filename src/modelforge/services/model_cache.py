"""Thread-safe cache for loaded inference models."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import TypeVar, cast

ModelT = TypeVar("ModelT")


class ModelCache:
    """Cache loaded models by immutable model-version identity."""

    def __init__(self) -> None:
        self._models: dict[int, object] = {}
        self._lock = RLock()

    def contains(self, model_version_id: int) -> bool:
        """Return whether a model version is currently loaded."""

        with self._lock:
            return model_version_id in self._models

    def get_or_load(
        self,
        model_version_id: int,
        loader: Callable[[], ModelT],
    ) -> tuple[ModelT, bool]:
        """Return a model and whether it was already cached.

        The lookup, optional load, cache insertion, and hit determination
        happen while holding the same lock. This keeps cache-hit reporting
        consistent with the model actually returned to the caller.
        """

        with self._lock:
            cached = self._models.get(model_version_id)

            if cached is not None:
                return cast(ModelT, cached), True

            model = loader()
            self._models[model_version_id] = model

            return model, False

    def invalidate(self, model_version_id: int) -> None:
        """Remove one model version from the cache."""

        with self._lock:
            self._models.pop(model_version_id, None)

    def clear(self) -> None:
        """Remove every loaded model."""

        with self._lock:
            self._models.clear()

    def __len__(self) -> int:
        """Return the number of loaded model versions."""

        with self._lock:
            return len(self._models)