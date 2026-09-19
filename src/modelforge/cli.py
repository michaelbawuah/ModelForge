"""Command-line client for the ModelForge control plane."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from modelforge.core.config import (
    ProductionConfigError,
    validate_deployment_config,
)

DEFAULT_URL = "http://127.0.0.1:8000"


class ModelForgeCLIError(Exception):
    """Raised for API errors that should be shown cleanly to CLI users."""


class ModelForgeAPI:
    """Authenticated HTTP client used by the ModelForge CLI."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        *,
        api_key: str | None = None,
        workspace: str | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if workspace:
            headers["X-ModelForge-Workspace"] = workspace

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers=headers,
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(
                method,
                path,
                json=payload,
                params=params,
            )
        except httpx.RequestError as exc:
            raise ModelForgeCLIError(
                f"Unable to reach ModelForge at {self._client.base_url}."
            ) from exc

        try:
            data = response.json()
        except ValueError:
            data = response.text

        if response.is_error:
            detail = data.get("detail") if isinstance(data, dict) else data
            raise ModelForgeCLIError(
                f"HTTP {response.status_code}: {detail}"
            )

        return data


def _json_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("value must be valid JSON") from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the public ModelForge command-line interface."""

    parser = argparse.ArgumentParser(
        prog="modelforge",
        description="Operate a ModelForge control plane.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("MODELFORGE_URL", DEFAULT_URL),
        help="ModelForge API base URL (or set MODELFORGE_URL).",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MODELFORGE_API_KEY"),
        help="Workspace API key (or set MODELFORGE_API_KEY).",
    )
    parser.add_argument(
        "--workspace",
        default=os.getenv("MODELFORGE_WORKSPACE"),
        help="Workspace slug/id for OIDC sessions.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds.",
    )

    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status", help="Show API, readiness and runtime health.")
    commands.add_parser(
        "config-check",
        help="Validate local deployment configuration without contacting the API.",
    )
    commands.add_parser("models", help="List registered models.")
    commands.add_parser("whoami", help="Show the authenticated workspace context.")

    deployments = commands.add_parser("deployments", help="List deployments.")
    deployments.add_argument("--environment")

    commands.add_parser("runtimes", help="List runtime inventory and health.")

    predict = commands.add_parser("predict", help="Run inference.")
    predict.add_argument("environment")
    predict.add_argument("inputs", type=_json_value)

    deploy = commands.add_parser("deploy", help="Deployment lifecycle actions.")
    deploy_commands = deploy.add_subparsers(dest="deploy_command", required=True)

    promote = deploy_commands.add_parser("promote")
    promote.add_argument("deployment_id", type=int)

    rollback = deploy_commands.add_parser("rollback")
    rollback.add_argument("deployment_id", type=int)

    canary = commands.add_parser("canary", help="Canary lifecycle actions.")
    canary_commands = canary.add_subparsers(dest="canary_command", required=True)

    canary_start = canary_commands.add_parser("start")
    canary_start.add_argument("deployment_id", type=int)
    canary_start.add_argument("--weight", type=int, required=True)

    canary_weight = canary_commands.add_parser("weight")
    canary_weight.add_argument("deployment_id", type=int)
    canary_weight.add_argument("--weight", type=int, required=True)

    canary_promote = canary_commands.add_parser("promote")
    canary_promote.add_argument("deployment_id", type=int)

    canary_abort = canary_commands.add_parser("abort")
    canary_abort.add_argument("deployment_id", type=int)
    canary_abort.add_argument("--reason", required=True)

    return parser


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _execute(api: ModelForgeAPI, args: argparse.Namespace) -> Any:
    if args.command == "status":
        return {
            "health": api.request("GET", "/health"),
            "readiness": api.request("GET", "/ready"),
            "runtime_health": api.request("GET", "/runtimes/health"),
        }

    if args.command == "whoami":
        return api.request("GET", "/auth/me")

    if args.command == "models":
        return api.request("GET", "/models")

    if args.command == "deployments":
        params = {}
        if args.environment:
            params["environment"] = args.environment
        return api.request("GET", "/deployments", params=params)

    if args.command == "runtimes":
        return {
            "inventory": api.request("GET", "/runtimes"),
            "health": api.request("GET", "/runtimes/health"),
        }

    if args.command == "predict":
        return api.request(
            "POST",
            "/predict",
            payload={
                "environment": args.environment,
                "inputs": args.inputs,
            },
        )

    if args.command == "deploy":
        if args.deploy_command == "promote":
            return api.request(
                "POST",
                f"/deployments/{args.deployment_id}/promote",
            )
        if args.deploy_command == "rollback":
            return api.request(
                "POST",
                f"/deployments/{args.deployment_id}/rollback",
            )

    if args.command == "canary":
        base = f"/deployments/{args.deployment_id}/canary"

        if args.canary_command == "start":
            return api.request(
                "POST",
                base,
                payload={"weight": args.weight},
            )
        if args.canary_command == "weight":
            return api.request(
                "PATCH",
                base,
                payload={"weight": args.weight},
            )
        if args.canary_command == "promote":
            return api.request("POST", base + "/promote")
        if args.canary_command == "abort":
            return api.request(
                "POST",
                base + "/abort",
                payload={"reason": args.reason},
            )

    raise ModelForgeCLIError("Unsupported command.")


def main(
    argv: Sequence[str] | None = None,
    *,
    api_factory: Callable[..., ModelForgeAPI] = ModelForgeAPI,
) -> int:
    """Run the ModelForge CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "config-check":
        try:
            report = validate_deployment_config()
        except ProductionConfigError as exc:
            parser.exit(1, f"modelforge: {exc}\n")
        _print_json(report.as_dict())
        return 0

    api = api_factory(
        args.base_url,
        args.timeout,
        api_key=args.api_key,
        workspace=args.workspace,
    )

    try:
        result = _execute(api, args)
    except ModelForgeCLIError as exc:
        parser.exit(1, f"modelforge: {exc}\n")
    finally:
        api.close()

    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
