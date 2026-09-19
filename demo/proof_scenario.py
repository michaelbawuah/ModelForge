"""Run and capture a recruiter-visible ModelForge deployment proof."""

from __future__ import annotations

import argparse
import json
import math
import os
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"
MODEL_DIR = Path(__file__).with_name("models")


def auth_headers(
    *,
    api_key: str | None,
    workspace: str | None,
) -> dict[str, str]:
    """Build request headers without exposing credentials in evidence."""

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if workspace:
        headers["X-ModelForge-Workspace"] = workspace
    return headers


def relative_drift(baseline: float, candidate: float) -> float:
    """Return absolute relative drift, handling a zero baseline safely."""

    if baseline == 0:
        return 0.0 if candidate == 0 else math.inf
    return abs(candidate - baseline) / abs(baseline)


def summarize_traffic(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize serving lanes and versions from prediction evidence."""

    lanes = Counter(str(sample["traffic_lane"]) for sample in samples)
    versions = Counter(str(sample["model_version"]) for sample in samples)
    fallbacks = sum(bool(sample.get("canary_fallback")) for sample in samples)

    return {
        "requests": len(samples),
        "traffic_lanes": dict(sorted(lanes.items())),
        "model_versions": dict(sorted(versions.items())),
        "canary_fallbacks": fallbacks,
    }


def _require_status(
    response: httpx.Response,
    expected: int | tuple[int, ...],
) -> Any:
    allowed = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in allowed:
        raise RuntimeError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}: {response.text}"
        )
    if not response.content:
        return None
    return response.json()


def _require_close(actual: Any, expected: float, *, label: str) -> None:
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        raise TypeError(f"{label} returned non-numeric output: {actual!r}")
    if not math.isclose(
        float(actual),
        expected,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise RuntimeError(
            f"{label} returned {actual!r}; expected {expected!r}."
        )


def _upload_artifact(
    client: httpx.Client,
    *,
    model_id: int,
    filename: str,
    version: str,
) -> dict[str, Any]:
    artifact = (MODEL_DIR / filename).read_bytes()
    response = client.post(
        f"/models/{model_id}/artifacts",
        data={
            "version": version,
            "framework": "modelforge-json",
        },
        files={
            "artifact": (
                filename,
                artifact,
                "application/json",
            )
        },
    )
    return _require_status(response, 201)


def _create_deployment(
    client: httpx.Client,
    *,
    model_version_id: int,
    environment: str,
) -> dict[str, Any]:
    return _require_status(
        client.post(
            "/deployments",
            json={
                "model_version_id": model_version_id,
                "environment": environment,
            },
        ),
        201,
    )


def _predict(
    client: httpx.Client,
    *,
    environment: str,
    inputs: Any,
) -> dict[str, Any]:
    return _require_status(
        client.post(
            "/predict",
            json={
                "environment": environment,
                "inputs": inputs,
            },
        ),
        200,
    )


def _collect_canary_samples(
    client: httpx.Client,
    *,
    environment: str,
    inputs: Any,
    stable_version: str,
    canary_version: str,
    stable_expected: float,
    canary_expected: float,
    maximum_requests: int,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []

    for sequence in range(1, maximum_requests + 1):
        payload = _predict(
            client,
            environment=environment,
            inputs=inputs,
        )
        version = str(payload["model_version"])

        if version == stable_version:
            _require_close(
                payload["prediction"],
                stable_expected,
                label="stable canary sample",
            )
        elif version == canary_version:
            _require_close(
                payload["prediction"],
                canary_expected,
                label="candidate canary sample",
            )
        else:
            raise RuntimeError(
                f"Unexpected model version in canary traffic: {version!r}."
            )

        samples.append(
            {
                "sequence": sequence,
                "prediction": payload["prediction"],
                "deployment_id": payload["deployment_id"],
                "model_version_id": payload["model_version_id"],
                "model_version": version,
                "traffic_lane": payload["traffic_lane"],
                "cache_hit": payload["cache_hit"],
                "canary_fallback": payload["canary_fallback"],
            }
        )

        seen = {str(item["model_version"]) for item in samples}
        if (
            stable_version in seen
            and canary_version in seen
            and len(samples) >= 10
        ):
            return samples

    seen = {str(item["model_version"]) for item in samples}
    raise RuntimeError(
        "Canary proof did not observe both stable and candidate versions "
        f"within {maximum_requests} requests; observed {sorted(seen)}."
    )


def run_proof(
    *,
    base_url: str,
    environment: str,
    api_key: str | None,
    workspace: str | None,
    canary_weight: int,
    traffic_requests: int,
    timeout_seconds: float,
    regression_threshold: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run promotion, rollback, and regression-abort proof against ModelForge."""

    if canary_weight < 1 or canary_weight > 99:
        raise ValueError("canary_weight must be between 1 and 99.")
    if traffic_requests < 10:
        raise ValueError("traffic_requests must be at least 10.")
    if regression_threshold <= 0:
        raise ValueError("regression_threshold must be greater than zero.")

    suffix = uuid.uuid4().hex[:10]
    model_name = f"modelforge-proof-{suffix}"

    stable_expected = 21.0
    candidate_expected = 24.5
    risky_expected = 60.0
    test_input = 10

    started_at = datetime.now(UTC)

    with httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
        headers=auth_headers(api_key=api_key, workspace=workspace),
    ) as client:
        health = _require_status(client.get("/health"), 200)
        readiness = _require_status(client.get("/ready"), 200)

        model = _require_status(
            client.post(
                "/models",
                json={
                    "name": model_name,
                    "description": (
                        "Recruiter-proof model for canary promotion, rollback, "
                        "and regression abort."
                    ),
                },
            ),
            201,
        )

        stable_version = _upload_artifact(
            client,
            model_id=model["id"],
            filename="stable.json",
            version="1.0.0",
        )
        candidate_version = _upload_artifact(
            client,
            model_id=model["id"],
            filename="canary.json",
            version="2.0.0",
        )
        risky_version = _upload_artifact(
            client,
            model_id=model["id"],
            filename="risky.json",
            version="3.0.0",
        )

        stable_deployment = _create_deployment(
            client,
            model_version_id=stable_version["id"],
            environment=environment,
        )
        stable_active = _require_status(
            client.post(
                f"/deployments/{stable_deployment['id']}/promote"
            ),
            200,
        )

        baseline = _predict(
            client,
            environment=environment,
            inputs=test_input,
        )
        _require_close(
            baseline["prediction"],
            stable_expected,
            label="baseline",
        )
        if baseline["model_version"] != "1.0.0":
            raise RuntimeError("Baseline request was not served by stable v1.")

        candidate_deployment = _create_deployment(
            client,
            model_version_id=candidate_version["id"],
            environment=environment,
        )
        candidate_canary = _require_status(
            client.post(
                f"/deployments/{candidate_deployment['id']}/canary",
                json={"weight": canary_weight},
            ),
            200,
        )

        promotion_samples = _collect_canary_samples(
            client,
            environment=environment,
            inputs=test_input,
            stable_version="1.0.0",
            canary_version="2.0.0",
            stable_expected=stable_expected,
            canary_expected=candidate_expected,
            maximum_requests=traffic_requests,
        )

        promoted = _require_status(
            client.post(
                f"/deployments/{candidate_deployment['id']}/canary/promote"
            ),
            200,
        )
        promoted_prediction = _predict(
            client,
            environment=environment,
            inputs=test_input,
        )
        _require_close(
            promoted_prediction["prediction"],
            candidate_expected,
            label="promoted candidate",
        )
        if promoted_prediction["model_version"] != "2.0.0":
            raise RuntimeError("Canary promotion did not make v2 authoritative.")

        rolled_back = _require_status(
            client.post(
                f"/deployments/{stable_deployment['id']}/rollback"
            ),
            200,
        )
        rollback_prediction = _predict(
            client,
            environment=environment,
            inputs=test_input,
        )
        _require_close(
            rollback_prediction["prediction"],
            stable_expected,
            label="rollback",
        )
        if rollback_prediction["model_version"] != "1.0.0":
            raise RuntimeError("Rollback did not restore stable v1.")

        risky_deployment = _create_deployment(
            client,
            model_version_id=risky_version["id"],
            environment=environment,
        )
        risky_canary = _require_status(
            client.post(
                f"/deployments/{risky_deployment['id']}/canary",
                json={"weight": canary_weight},
            ),
            200,
        )

        risky_samples = _collect_canary_samples(
            client,
            environment=environment,
            inputs=test_input,
            stable_version="1.0.0",
            canary_version="3.0.0",
            stable_expected=stable_expected,
            canary_expected=risky_expected,
            maximum_requests=traffic_requests,
        )
        risky_observation = next(
            item
            for item in risky_samples
            if item["model_version"] == "3.0.0"
        )
        drift = relative_drift(
            stable_expected,
            float(risky_observation["prediction"]),
        )
        if drift <= regression_threshold:
            raise RuntimeError(
                "Risky canary did not exceed the configured regression threshold."
            )

        abort_reason = (
            "Automated demo guardrail rejected v3: output drift "
            f"{drift:.1%} exceeded threshold {regression_threshold:.1%}."
        )
        aborted = _require_status(
            client.post(
                f"/deployments/{risky_deployment['id']}/canary/abort",
                json={"reason": abort_reason},
            ),
            200,
        )
        if aborted["state"] != "FAILED":
            raise RuntimeError("Regression canary was not marked FAILED.")

        final_target = _require_status(
            client.get(f"/deployment-targets/{environment}"),
            200,
        )
        if final_target["active_deployment_id"] != stable_deployment["id"]:
            raise RuntimeError("Stable deployment was not preserved after abort.")
        if final_target["canary_deployment_id"] is not None:
            raise RuntimeError("Canary target remained configured after abort.")

        final_prediction = _predict(
            client,
            environment=environment,
            inputs=test_input,
        )
        _require_close(
            final_prediction["prediction"],
            stable_expected,
            label="final stable",
        )
        if final_prediction["model_version"] != "1.0.0":
            raise RuntimeError("Final serving target is not stable v1.")

    all_samples = [
        *(
            {
                "phase": "promotion-canary",
                **sample,
            }
            for sample in promotion_samples
        ),
        *(
            {
                "phase": "regression-canary",
                **sample,
            }
            for sample in risky_samples
        ),
    ]

    finished_at = datetime.now(UTC)
    summary = {
        "status": "PASS",
        "scenario": "stable-canary-promote-rollback-regression-abort",
        "base_url": base_url.rstrip("/"),
        "workspace": workspace,
        "environment": environment,
        "model": {
            "id": model["id"],
            "name": model_name,
        },
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "checks": {
            "health": health["status"],
            "readiness": readiness["status"],
            "stable_baseline": {
                "deployment_id": stable_active["id"],
                "version": "1.0.0",
                "input": test_input,
                "prediction": baseline["prediction"],
            },
            "candidate_canary": {
                "deployment_id": candidate_canary["id"],
                "version": "2.0.0",
                "weight_percent": canary_weight,
                "traffic": summarize_traffic(promotion_samples),
            },
            "promotion": {
                "deployment_id": promoted["id"],
                "state": promoted["state"],
                "prediction": promoted_prediction["prediction"],
            },
            "rollback": {
                "deployment_id": rolled_back["id"],
                "state": rolled_back["state"],
                "restored_version": rollback_prediction["model_version"],
                "prediction": rollback_prediction["prediction"],
            },
            "regression_canary": {
                "deployment_id": risky_canary["id"],
                "version": "3.0.0",
                "weight_percent": canary_weight,
                "traffic": summarize_traffic(risky_samples),
                "observed_prediction": risky_observation["prediction"],
                "relative_drift": drift,
                "threshold": regression_threshold,
            },
            "abort": {
                "deployment_id": aborted["id"],
                "state": aborted["state"],
                "failure_reason": aborted["failure_reason"],
            },
            "final_target": {
                "active_deployment_id": final_target["active_deployment_id"],
                "canary_deployment_id": final_target["canary_deployment_id"],
                "canary_weight": final_target["canary_weight"],
                "version": final_prediction["model_version"],
                "prediction": final_prediction["prediction"],
            },
        },
    }
    return summary, all_samples


def render_markdown(summary: dict[str, Any]) -> str:
    """Render a compact human-readable proof report."""

    checks = summary["checks"]
    promotion_traffic = checks["candidate_canary"]["traffic"]
    regression = checks["regression_canary"]

    return f"""# ModelForge Deployment Proof

**Status:** {summary["status"]}

**Scenario:** stable → canary → promote → rollback → regression canary → abort

| Check | Evidence |
| --- | --- |
| Health | {checks["health"]} |
| Readiness | {checks["readiness"]} |
| Stable baseline | v1.0.0 → {checks["stable_baseline"]["prediction"]} |
| Candidate canary | {checks["candidate_canary"]["weight_percent"]}% configured; {promotion_traffic["requests"]} sampled requests |
| Candidate promotion | {checks["promotion"]["state"]}; prediction {checks["promotion"]["prediction"]} |
| Rollback | restored {checks["rollback"]["restored_version"]}; prediction {checks["rollback"]["prediction"]} |
| Regression canary | v3.0.0 drift {regression["relative_drift"]:.1%} vs threshold {regression["threshold"]:.1%} |
| Regression action | {checks["abort"]["state"]}: {checks["abort"]["failure_reason"]} |
| Final serving target | {checks["final_target"]["version"]}; no canary configured |

## Traffic evidence

Candidate canary lanes:

~~~json
{json.dumps(promotion_traffic, indent=2, sort_keys=True)}
~~~

Regression canary lanes:

~~~json
{json.dumps(regression["traffic"], indent=2, sort_keys=True)}
~~~

Generated by python demo/proof_scenario.py.
"""


def write_evidence(
    output_dir: Path,
    *,
    summary: dict[str, Any],
    samples: list[dict[str, Any]],
) -> None:
    """Write machine-readable and recruiter-readable proof artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "proof-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "traffic-samples.jsonl").open(
        "w",
        encoding="utf-8",
    ) as output:
        for sample in samples:
            output.write(json.dumps(sample, sort_keys=True))
            output.write("\n")
    (output_dir / "proof-report.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the ModelForge deployment proof scenario.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("MODELFORGE_URL", DEFAULT_URL),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MODELFORGE_API_KEY"),
    )
    parser.add_argument(
        "--workspace",
        default=os.getenv("MODELFORGE_WORKSPACE"),
    )
    parser.add_argument(
        "--environment",
        default="demo-proof",
    )
    parser.add_argument(
        "--weight",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--traffic-requests",
        type=int,
        default=60,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("demo-proof-evidence"),
    )
    args = parser.parse_args()

    summary, samples = run_proof(
        base_url=args.base_url,
        environment=args.environment,
        api_key=args.api_key,
        workspace=args.workspace,
        canary_weight=args.weight,
        traffic_requests=args.traffic_requests,
        timeout_seconds=args.timeout_seconds,
        regression_threshold=args.regression_threshold,
    )
    write_evidence(
        args.output_dir,
        summary=summary,
        samples=samples,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
