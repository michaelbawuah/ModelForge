"""Seed a visible stable + canary ModelForge demo."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"
MODEL_DIR = Path(__file__).with_name("models")


def bootstrap_demo(
    *,
    base_url: str,
    environment: str,
    canary_weight: int,
    timeout_seconds: float,
) -> dict[str, object]:
    """Create two real artifacts and leave one stable plus one canary."""

    if canary_weight < 1 or canary_weight > 99:
        raise ValueError("canary_weight must be between 1 and 99.")

    suffix = uuid.uuid4().hex[:8]
    model_name = f"modelforge-demo-{suffix}"

    stable_artifact = (MODEL_DIR / "stable.json").read_bytes()
    canary_artifact = (MODEL_DIR / "canary.json").read_bytes()

    with httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
    ) as client:
        model_response = client.post(
            "/models",
            json={
                "name": model_name,
                "description": (
                    "Seeded demo model showing stable/canary deployment behavior."
                ),
            },
        )
        model_response.raise_for_status()
        model = model_response.json()

        stable_response = client.post(
            f"/models/{model['id']}/artifacts",
            data={
                "version": "1.0.0",
                "framework": "modelforge-json",
            },
            files={
                "artifact": (
                    "stable.json",
                    stable_artifact,
                    "application/json",
                )
            },
        )
        stable_response.raise_for_status()
        stable_version = stable_response.json()

        canary_response = client.post(
            f"/models/{model['id']}/artifacts",
            data={
                "version": "2.0.0",
                "framework": "modelforge-json",
            },
            files={
                "artifact": (
                    "canary.json",
                    canary_artifact,
                    "application/json",
                )
            },
        )
        canary_response.raise_for_status()
        canary_version = canary_response.json()

        stable_deployment_response = client.post(
            "/deployments",
            json={
                "model_version_id": stable_version["id"],
                "environment": environment,
            },
        )
        stable_deployment_response.raise_for_status()
        stable_deployment = stable_deployment_response.json()

        promotion_response = client.post(
            f"/deployments/{stable_deployment['id']}/promote"
        )
        promotion_response.raise_for_status()

        canary_deployment_response = client.post(
            "/deployments",
            json={
                "model_version_id": canary_version["id"],
                "environment": environment,
            },
        )
        canary_deployment_response.raise_for_status()
        canary_deployment = canary_deployment_response.json()

        canary_start_response = client.post(
            f"/deployments/{canary_deployment['id']}/canary",
            json={"weight": canary_weight},
        )
        canary_start_response.raise_for_status()

    return {
        "model": model_name,
        "environment": environment,
        "stable": {
            "deployment_id": stable_deployment["id"],
            "model_version_id": stable_version["id"],
            "version": stable_version["version"],
            "example_input": 10,
            "expected_output": 21.0,
        },
        "canary": {
            "deployment_id": canary_deployment["id"],
            "model_version_id": canary_version["id"],
            "version": canary_version["version"],
            "weight_percent": canary_weight,
            "example_input": 10,
            "expected_output": 24.5,
        },
        "dashboard": f"{base_url.rstrip('/')}/dashboard",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.getenv("MODELFORGE_URL", DEFAULT_URL),
    )
    parser.add_argument("--environment", default="demo")
    parser.add_argument("--weight", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()

    result = bootstrap_demo(
        base_url=args.base_url,
        environment=args.environment,
        canary_weight=args.weight,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
