"""Tests for the inference model cache."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from modelforge.services.model_cache import ModelCache


def test_get_or_load_loads_model_once() -> None:
    """Repeated access to one model version reuses the cached model."""

    cache = ModelCache()
    load_count = 0

    def loader() -> object:
        nonlocal load_count
        load_count += 1
        return object()

    first_model, first_hit = cache.get_or_load(1, loader)
    second_model, second_hit = cache.get_or_load(1, loader)

    assert first_model is second_model
    assert first_hit is False
    assert second_hit is True
    assert load_count == 1
    assert len(cache) == 1


def test_get_or_load_keeps_versions_separate() -> None:
    """Different immutable model versions receive separate cache entries."""

    cache = ModelCache()

    first_model, first_hit = cache.get_or_load(1, object)
    second_model, second_hit = cache.get_or_load(2, object)

    assert first_model is not second_model
    assert first_hit is False
    assert second_hit is False
    assert len(cache) == 2


def test_contains_reports_loaded_versions() -> None:
    """Contains reflects whether a model version is loaded."""

    cache = ModelCache()

    assert cache.contains(7) is False

    cache.get_or_load(7, object)

    assert cache.contains(7) is True


def test_invalidate_removes_one_model_version() -> None:
    """Invalidating one version leaves other cached versions untouched."""

    cache = ModelCache()

    cache.get_or_load(1, object)
    cache.get_or_load(2, object)

    cache.invalidate(1)

    assert cache.contains(1) is False
    assert cache.contains(2) is True
    assert len(cache) == 1


def test_clear_removes_all_model_versions() -> None:
    """Clearing the cache evicts every loaded model."""

    cache = ModelCache()

    cache.get_or_load(1, object)
    cache.get_or_load(2, object)

    cache.clear()

    assert cache.contains(1) is False
    assert cache.contains(2) is False
    assert len(cache) == 0


def test_concurrent_get_or_load_loads_once_and_reports_one_miss() -> None:
    """Concurrent access loads once and atomically reports cache status."""

    cache = ModelCache()
    load_count = 0
    load_count_lock = Lock()

    def loader() -> object:
        nonlocal load_count

        with load_count_lock:
            load_count += 1

        sleep(0.05)
        return object()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(cache.get_or_load, 42, loader)
            for _ in range(8)
        ]

    results = [future.result() for future in futures]
    models = [model for model, _ in results]
    cache_hits = [cache_hit for _, cache_hit in results]

    assert load_count == 1
    assert len({id(model) for model in models}) == 1
    assert cache_hits.count(False) == 1
    assert cache_hits.count(True) == 7
    assert len(cache) == 1