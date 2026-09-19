"""Run a complete hosted ModelForge release-safety proof."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"
MODEL_DIR = Path(__file__).with_name("models")
STABLE_INPUT = 10
STABLE_OUTPUT = 21.0
REGRESSION_OUTPUT = 24.5


class HostedDemoError(RuntimeError):
    """Raised when a hosted lifecycle proof violates an expected invariant."""


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.request(method, path, json=json_payload)
    response.raise_for_status()
    return response.json()


def _prediction(
    client: httpx.Client,
    environment: str,
) -> dict[str, Any]:
    return _request_json(
        client,
        "POST",
        "/predict",
        json_payload={
            "environment": environment,
            "inputs": STABLE_INPUT,
        },
    )


def _assert_prediction(
    prediction: dict[str, Any],
    *,
    expected_lane: str,
    expected_version: str,
    expected_output: float,
) -> None:
    if prediction.get("traffic_lane") != expected_lane:
        raise HostedDemoError(
            "Unexpected traffic lane: "
            f"{prediction.get('traffic_lane')!r}; expected {expected_lane!r}."
        )
    if prediction.get("model_version") != expected_version:
        raise HostedDemoError(
            "Unexpected model version: "
            f"{prediction.get('model_version')!r}; expected {expected_version!r}."
        )

    actual = prediction.get("prediction")
    if not isinstance(actual, (int, float)):
        raise HostedDemoError(f"Prediction is not numeric: {actual!r}.")
    if abs(float(actual) - expected_output) > 1e-9:
        raise HostedDemoError(
            f"Unexpected prediction {actual!r}; expected {expected_output!r}."
        )


def _upload_version(
    client: httpx.Client,
    *,
    model_id: int,
    version: str,
    artifact: bytes,
    filename: str,
) -> dict[str, Any]:
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
    response.raise_for_status()
    return response.json()


def _create_deployment(
    client: httpx.Client,
    *,
    model_version_id: int,
    environment: str,
) -> dict[str, Any]:
    return _request_json(
        client,
        "POST",
        "/deployments",
        json_payload={
            "model_version_id": model_version_id,
            "environment": environment,
        },
    )


def _sample_traffic(
    client: httpx.Client,
    *,
    environment: str,
    minimum_requests: int,
    maximum_requests: int = 200,
) -> dict[str, Any]:
    if minimum_requests < 2:
        raise ValueError("minimum_requests must be at least 2.")
    if maximum_requests < minimum_requests:
        raise ValueError("maximum_requests must be >= minimum_requests.")

    counts = {"stable": 0, "canary": 0}
    first_by_lane: dict[str, dict[str, Any]] = {}

    total = 0
    while total < maximum_requests:
        result = _prediction(client, environment)
        lane = result.get("traffic_lane")
        if lane not in counts:
            raise HostedDemoError(f"Unknown traffic lane: {lane!r}.")

        counts[lane] += 1
        first_by_lane.setdefault(lane, result)
        total += 1

        if total >= minimum_requests and all(counts.values()):
            break

    if not all(counts.values()):
        raise HostedDemoError(
            "Traffic sampling did not observe both stable and canary lanes. "
            f"Observed counts: {counts}."
        )

    return {
        "requests": total,
        "stable_requests": counts["stable"],
        "canary_requests": counts["canary"],
        "observed_canary_percent": round(
            counts["canary"] * 100.0 / total,
            2,
        ),
        "first_stable": first_by_lane["stable"],
        "first_canary": first_by_lane["canary"],
    }


def _abort_existing_canary(
    client: httpx.Client,
    *,
    environment: str,
) -> dict[str, Any] | None:
    response = client.get(f"/deployment-targets/{environment}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    target = response.json()
    canary_id = target.get("canary_deployment_id")
    if canary_id is None:
        return None

    aborted = _request_json(
        client,
        "POST",
        f"/deployments/{canary_id}/canary/abort",
        json_payload={
            "reason": "Resetting prior recruiter-demo canary before a new proof run."
        },
    )
    return {
        "deployment_id": canary_id,
        "resulting_state": aborted["state"],
    }


def _safe_identity(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        key: identity.get(key)
        for key in (
            "auth_type",
            "workspace_id",
            "workspace_slug",
            "role",
        )
    }


def _render_markdown(evidence: dict[str, Any]) -> str:
    samples = evidence["traffic_samples"]
    final_target = evidence["final_target"]
    timeline = evidence["timeline"]

    lines = [
        "# ModelForge Hosted Demo Evidence",
        "",
        f"- Generated: {evidence['generated_at']}",
        f"- Public URL: {evidence['public_url']}",
        f"- Workspace: {evidence['identity']['workspace_slug']}",
        f"- Environment: {evidence['environment']}",
        f"- Model: {evidence['model']['name']}",
        "",
        "## Proven lifecycle",
        "",
        "| Step | Result |",
        "|---|---|",
    ]
    for item in timeline:
        lines.append(f"| {item['step']} | {item['result']} |")

    lines.extend(
        [
            "",
            "## Traffic evidence",
            "",
            "| Phase | Requests | Stable | Canary | Observed canary share |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name in ("regression_canary", "good_canary", "final_visible_canary"):
        sample = samples[name]
        lines.append(
            "| "
            + name.replace("_", " ")
            + f" | {sample['requests']} | {sample['stable_requests']} "
            + f"| {sample['canary_requests']} "
            + f"| {sample['observed_canary_percent']}% |"
        )

    lines.extend(
        [
            "",
            "## Final dashboard state",
            "",
            f"- Stable deployment: #{final_target['active_deployment_id']}",
            f"- Canary deployment: #{final_target['canary_deployment_id']}",
            f"- Canary traffic: {final_target['canary_weight']}%",
            f"- Dashboard: {evidence['dashboard_url']}",
            "",
            "The final canary is intentionally left active so the deployment can be "
            "opened in the ModelForge console and captured for recruiter-facing proof.",
            "",
        ]
    )
    return "\n".join(lines)


def run_hosted_demo(
    client: httpx.Client,
    *,
    public_url: str,
    environment: str,
    canary_weight: int,
    sample_requests: int,
) -> dict[str, Any]:
    """Prove abort, promotion, rollback, and final visible canary state."""

    if canary_weight < 10 or canary_weight > 90:
        raise ValueError("canary_weight must be between 10 and 90 for demo proof.")
    if sample_requests < 10:
        raise ValueError("sample_requests must be at least 10.")

    health = _request_json(client, "GET", "/health")
    ready = _request_json(client, "GET", "/ready")
    identity = _request_json(client, "GET", "/auth/me")
    reset = _abort_existing_canary(client, environment=environment)

    suffix = uuid.uuid4().hex[:8]
    model_name = f"modelforge-hosted-proof-{suffix}"
    model = _request_json(
        client,
        "POST",
        "/models",
        json_payload={
            "name": model_name,
            "description": (
                "Hosted proof model demonstrating abort, promotion, rollback, "
                "and visible canary state."
            ),
        },
    )

    stable_artifact = (MODEL_DIR / "stable.json").read_bytes()
    regression_artifact = (MODEL_DIR / "canary.json").read_bytes()

    versions = {
        "stable_v1": _upload_version(
            client,
            model_id=model["id"],
            version="1.0.0",
            artifact=stable_artifact,
            filename="stable-v1.json",
        ),
        "regression_v2": _upload_version(
            client,
            model_id=model["id"],
            version="2.0.0",
            artifact=regression_artifact,
            filename="regression-v2.json",
        ),
        "good_v3": _upload_version(
            client,
            model_id=model["id"],
            version="3.0.0",
            artifact=stable_artifact,
            filename="good-v3.json",
        ),
        "visible_v4": _upload_version(
            client,
            model_id=model["id"],
            version="4.0.0",
            artifact=stable_artifact,
            filename="visible-v4.json",
        ),
    }

    stable = _create_deployment(
        client,
        model_version_id=versions["stable_v1"]["id"],
        environment=environment,
    )
    stable = _request_json(
        client,
        "POST",
        f"/deployments/{stable['id']}/promote",
    )
    baseline = _prediction(client, environment)
    _assert_prediction(
        baseline,
        expected_lane="stable",
        expected_version="1.0.0",
        expected_output=STABLE_OUTPUT,
    )

    regression = _create_deployment(
        client,
        model_version_id=versions["regression_v2"]["id"],
        environment=environment,
    )
    _request_json(
        client,
        "POST",
        f"/deployments/{regression['id']}/canary",
        json_payload={"weight": canary_weight},
    )
    regression_sample = _sample_traffic(
        client,
        environment=environment,
        minimum_requests=sample_requests,
    )
    _assert_prediction(
        regression_sample["first_stable"],
        expected_lane="stable",
        expected_version="1.0.0",
        expected_output=STABLE_OUTPUT,
    )
    _assert_prediction(
        regression_sample["first_canary"],
        expected_lane="canary",
        expected_version="2.0.0",
        expected_output=REGRESSION_OUTPUT,
    )
    aborted = _request_json(
        client,
        "POST",
        f"/deployments/{regression['id']}/canary/abort",
        json_payload={
            "reason": (
                "Hosted proof detected a semantic regression: input 10 returned "
                "24.5 on v2 instead of the stable 21.0."
            )
        },
    )
    after_abort = _request_json(
        client,
        "GET",
        f"/deployment-targets/{environment}",
    )
    if after_abort.get("active_deployment_id") != stable["id"]:
        raise HostedDemoError("Aborting the regression canary changed stable traffic.")
    if after_abort.get("canary_deployment_id") is not None:
        raise HostedDemoError("Regression canary remained configured after abort.")
    post_abort = _prediction(client, environment)
    _assert_prediction(
        post_abort,
        expected_lane="stable",
        expected_version="1.0.0",
        expected_output=STABLE_OUTPUT,
    )

    good = _create_deployment(
        client,
        model_version_id=versions["good_v3"]["id"],
        environment=environment,
    )
    _request_json(
        client,
        "POST",
        f"/deployments/{good['id']}/canary",
        json_payload={"weight": canary_weight},
    )
    good_sample = _sample_traffic(
        client,
        environment=environment,
        minimum_requests=sample_requests,
    )
    _assert_prediction(
        good_sample["first_canary"],
        expected_lane="canary",
        expected_version="3.0.0",
        expected_output=STABLE_OUTPUT,
    )
    promoted = _request_json(
        client,
        "POST",
        f"/deployments/{good['id']}/canary/promote",
    )
    after_promote = _prediction(client, environment)
    _assert_prediction(
        after_promote,
        expected_lane="stable",
        expected_version="3.0.0",
        expected_output=STABLE_OUTPUT,
    )

    rolled_back = _request_json(
        client,
        "POST",
        f"/deployments/{stable['id']}/rollback",
    )
    after_rollback = _prediction(client, environment)
    _assert_prediction(
        after_rollback,
        expected_lane="stable",
        expected_version="1.0.0",
        expected_output=STABLE_OUTPUT,
    )

    visible = _create_deployment(
        client,
        model_version_id=versions["visible_v4"]["id"],
        environment=environment,
    )
    _request_json(
        client,
        "POST",
        f"/deployments/{visible['id']}/canary",
        json_payload={"weight": canary_weight},
    )
    final_sample = _sample_traffic(
        client,
        environment=environment,
        minimum_requests=sample_requests,
    )
    _assert_prediction(
        final_sample["first_canary"],
        expected_lane="canary",
        expected_version="4.0.0",
        expected_output=STABLE_OUTPUT,
    )

    final_target = _request_json(
        client,
        "GET",
        f"/deployment-targets/{environment}",
    )
    deployments = client.get(
        "/deployments",
        params={"environment": environment},
    )
    deployments.raise_for_status()

    timeline: list[dict[str, str]] = []
    if reset is not None:
        timeline.append(
            {
                "step": "Reset previous canary",
                "result": (
                    f"deployment #{reset['deployment_id']} -> "
                    f"{reset['resulting_state']}"
                ),
            }
        )
    timeline.extend(
        [
            {
                "step": "Promote stable v1",
                "result": f"deployment #{stable['id']} ACTIVE; 10 -> 21.0",
            },
            {
                "step": "Observe regression canary v2",
                "result": (
                    f"deployment #{regression['id']} served 10 -> 24.5 on "
                    f"{regression_sample['canary_requests']} sampled canary requests"
                ),
            },
            {
                "step": "Abort regression canary",
                "result": (
                    f"deployment #{aborted['id']} FAILED; stable v1 stayed ACTIVE"
                ),
            },
            {
                "step": "Promote good v3",
                "result": (
                    f"deployment #{promoted['id']} ACTIVE after canary validation"
                ),
            },
            {
                "step": "Rollback to v1",
                "result": (
                    f"deployment #{rolled_back['id']} ACTIVE again; 10 -> 21.0"
                ),
            },
            {
                "step": "Leave visible v4 canary",
                "result": (
                    f"deployment #{visible['id']} CANARY at {canary_weight}% "
                    "for dashboard evidence"
                ),
            },
        ]
    )

    return {
        "status": "passed",
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_commit": os.getenv("GITHUB_SHA"),
        "public_url": public_url.rstrip("/"),
        "dashboard_url": public_url.rstrip("/") + "/dashboard",
        "environment": environment,
        "identity": _safe_identity(identity),
        "health": health,
        "readiness": ready,
        "model": {
            "id": model["id"],
            "name": model["name"],
        },
        "versions": {
            name: {
                "id": version["id"],
                "version": version["version"],
                "framework": version["framework"],
                "checksum": version["checksum"],
            }
            for name, version in versions.items()
        },
        "traffic_samples": {
            "regression_canary": regression_sample,
            "good_canary": good_sample,
            "final_visible_canary": final_sample,
        },
        "final_target": final_target,
        "deployments": deployments.json(),
        "timeline": timeline,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.getenv("MODELFORGE_PUBLIC_URL", DEFAULT_URL),
    )
    parser.add_argument(
        "--api-key-env",
        default="MODELFORGE_API_KEY",
        help="Environment variable containing the workspace API key.",
    )
    parser.add_argument("--allow-self-hosted", action="store_true")
    parser.add_argument("--environment", default="recruiter-demo")
    parser.add_argument("--weight", type=int, default=25)
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--output", type=Path, default=Path("hosted-demo.json"))
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("hosted-demo.md"),
    )
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key and not args.allow_self_hosted:
        parser.error(
            f"{args.api_key_env} must contain a ModelForge workspace API key."
        )

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    with httpx.Client(
        base_url=args.base_url.rstrip("/") + "/",
        timeout=args.timeout_seconds,
        headers=headers,
    ) as client:
        evidence = run_hosted_demo(
            client,
            public_url=args.base_url,
            environment=args.environment,
            canary_weight=args.weight,
            sample_requests=args.samples,
        )

    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")

    markdown = _render_markdown(evidence)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown + "\n", encoding="utf-8")

    print(rendered)


if __name__ == "__main__":
    main()
