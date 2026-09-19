"""Concurrent HTTP load generator for ModelForge prediction endpoints."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any

import httpx


@dataclass(frozen=True)
class RequestSample:
    latency_ms: float
    status_code: int
    success: bool
    traffic_lane: str | None
    canary_fallback: bool


def percentile(values: list[float], percentile_value: float) -> float:
    """Return a linearly interpolated percentile for a non-empty list."""

    if not values:
        raise ValueError("percentile requires at least one value.")

    if percentile_value < 0 or percentile_value > 100:
        raise ValueError("percentile_value must be between 0 and 100.")

    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(
    samples: list[RequestSample],
    *,
    elapsed_seconds: float,
) -> dict[str, Any]:
    """Aggregate request samples into stable benchmark output."""

    if not samples:
        raise ValueError("At least one benchmark sample is required.")

    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be greater than zero.")

    latencies = [sample.latency_ms for sample in samples]
    successes = sum(sample.success for sample in samples)
    failures = len(samples) - successes
    lanes = Counter(
        sample.traffic_lane
        for sample in samples
        if sample.traffic_lane is not None
    )
    statuses = Counter(str(sample.status_code) for sample in samples)

    return {
        "requests": len(samples),
        "successes": successes,
        "failures": failures,
        "error_rate": failures / len(samples),
        "duration_seconds": elapsed_seconds,
        "requests_per_second": len(samples) / elapsed_seconds,
        "latency_ms": {
            "min": min(latencies),
            "mean": fmean(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": max(latencies),
        },
        "status_codes": dict(sorted(statuses.items())),
        "traffic_lanes": dict(sorted(lanes.items())),
        "canary_fallbacks": sum(
            sample.canary_fallback
            for sample in samples
        ),
    }


async def _single_request(
    client: httpx.AsyncClient,
    *,
    environment: str,
    inputs: Any,
) -> RequestSample:
    start = perf_counter()

    try:
        response = await client.post(
            "/predict",
            json={
                "environment": environment,
                "inputs": inputs,
            },
        )
    except httpx.RequestError:
        return RequestSample(
            latency_ms=(perf_counter() - start) * 1000,
            status_code=0,
            success=False,
            traffic_lane=None,
            canary_fallback=False,
        )

    latency_ms = (perf_counter() - start) * 1000
    traffic_lane = None
    canary_fallback = False

    if response.status_code == 200:
        payload = response.json()
        traffic_lane = payload.get("traffic_lane")
        canary_fallback = bool(payload.get("canary_fallback", False))

    return RequestSample(
        latency_ms=latency_ms,
        status_code=response.status_code,
        success=response.status_code == 200,
        traffic_lane=traffic_lane,
        canary_fallback=canary_fallback,
    )


async def run_load(
    *,
    base_url: str,
    environment: str,
    inputs: Any,
    requests: int,
    concurrency: int,
    warmup: int,
    timeout_seconds: float,
) -> tuple[list[RequestSample], float]:
    """Run bounded-concurrency requests against one serving environment."""

    if requests <= 0:
        raise ValueError("requests must be greater than zero.")
    if concurrency <= 0:
        raise ValueError("concurrency must be greater than zero.")
    if warmup < 0:
        raise ValueError("warmup cannot be negative.")

    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )

    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
        limits=limits,
    ) as client:
        for _ in range(warmup):
            await _single_request(
                client,
                environment=environment,
                inputs=inputs,
            )

        queue: asyncio.Queue[int | None] = asyncio.Queue()

        for index in range(requests):
            queue.put_nowait(index)

        for _ in range(concurrency):
            queue.put_nowait(None)

        samples: list[RequestSample] = []
        samples_lock = asyncio.Lock()

        async def worker() -> None:
            while True:
                item = await queue.get()

                if item is None:
                    return

                sample = await _single_request(
                    client,
                    environment=environment,
                    inputs=inputs,
                )

                async with samples_lock:
                    samples.append(sample)

        start = perf_counter()
        await asyncio.gather(
            *(worker() for _ in range(concurrency))
        )
        elapsed = perf_counter() - start

    return samples, elapsed


def _parse_inputs(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("--inputs must be valid JSON.") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--environment", required=True)
    parser.add_argument("--inputs", default="10")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--warmup", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.max_error_rate < 0 or args.max_error_rate > 1:
        raise ValueError("--max-error-rate must be between 0 and 1.")

    samples, elapsed = asyncio.run(
        run_load(
            base_url=args.base_url,
            environment=args.environment,
            inputs=_parse_inputs(args.inputs),
            requests=args.requests,
            concurrency=args.concurrency,
            warmup=args.warmup,
            timeout_seconds=args.timeout_seconds,
        )
    )

    summary = summarize(samples, elapsed_seconds=elapsed)
    payload = json.dumps(summary, indent=2, sort_keys=True)
    print(payload)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")

    if summary["error_rate"] > args.max_error_rate:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
