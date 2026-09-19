"""Tests for the ModelForge command-line client."""

from __future__ import annotations

from typing import Any

from modelforge.cli import build_parser, main


class FakeAPI:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method, path, payload or params))
        return {
            "method": method,
            "path": path,
            "payload": payload,
            "params": params,
        }


def test_parser_supports_nested_canary_commands() -> None:
    args = build_parser().parse_args(
        ["canary", "start", "42", "--weight", "15"]
    )

    assert args.command == "canary"
    assert args.canary_command == "start"
    assert args.deployment_id == 42
    assert args.weight == 15


def test_cli_predict_sends_structured_json(capsys) -> None:
    instances: list[FakeAPI] = []

    def factory(base_url: str, timeout_seconds: float) -> FakeAPI:
        api = FakeAPI(base_url, timeout_seconds)
        instances.append(api)
        return api

    exit_code = main(
        [
            "--base-url",
            "http://example.test",
            "predict",
            "production",
            '{"features":[1,2,3]}',
        ],
        api_factory=factory,
    )

    assert exit_code == 0
    assert instances[0].calls == [
        (
            "POST",
            "/predict",
            {
                "environment": "production",
                "inputs": {"features": [1, 2, 3]},
            },
        )
    ]
    assert instances[0].closed is True
    assert '"path": "/predict"' in capsys.readouterr().out


def test_cli_canary_promote_uses_lifecycle_endpoint() -> None:
    instances: list[FakeAPI] = []

    def factory(base_url: str, timeout_seconds: float) -> FakeAPI:
        api = FakeAPI(base_url, timeout_seconds)
        instances.append(api)
        return api

    main(
        ["canary", "promote", "19"],
        api_factory=factory,
    )

    assert instances[0].calls == [
        ("POST", "/deployments/19/canary/promote", None)
    ]
