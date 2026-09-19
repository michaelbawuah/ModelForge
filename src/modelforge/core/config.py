"""Deployment environment and production preflight validation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_DATABASE_URL = (
    "mysql+pymysql://modelforge:modelforge_dev@127.0.0.1:3306/modelforge"
)
VALID_ENVIRONMENTS = frozenset({"development", "test", "production"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


class ProductionConfigError(RuntimeError):
    """Raised when ModelForge production configuration is unsafe or incomplete."""


@dataclass(frozen=True)
class DeploymentConfigReport:
    """Sanitized deployment configuration suitable for logs and CLI output."""

    environment: str
    auth_mode: str
    artifact_backend: str
    public_base_url: str | None
    trusted_hosts: tuple[str, ...]
    external_runtime_count: int
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "auth_mode": self.auth_mode,
            "artifact_backend": self.artifact_backend,
            "public_base_url": self.public_base_url,
            "trusted_hosts": list(self.trusted_hosts),
            "external_runtime_count": self.external_runtime_count,
            "warnings": list(self.warnings),
            "status": "valid",
        }


def _value(environment: Mapping[str, str], name: str, default: str = "") -> str:
    return str(environment.get(name, default)).strip()


def _truthy(value: str) -> bool:
    return value.strip().lower() in _TRUE_VALUES


def _origin(value: str) -> tuple[str, str, int | None] | None:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return None
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port


def _runtime_configuration(
    environment: Mapping[str, str],
    *,
    errors: list[str],
    warnings: list[str],
) -> int:
    raw = _value(environment, "MODELFORGE_EXTERNAL_RUNTIMES")
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        errors.append("MODELFORGE_EXTERNAL_RUNTIMES must contain valid JSON.")
        return 0

    if not isinstance(payload, dict):
        errors.append(
            "MODELFORGE_EXTERNAL_RUNTIMES must be a JSON object keyed by framework."
        )
        return 0

    for framework, settings in payload.items():
        if not isinstance(settings, dict):
            errors.append(
                f"External runtime '{framework}' configuration must be an object."
            )
            continue

        secret_name = settings.get("auth_token_env")
        if secret_name is None:
            warnings.append(
                f"External runtime '{framework}' has no auth_token_env; "
                "keep it on a trusted private network."
            )
            continue

        if not isinstance(secret_name, str) or not secret_name.strip():
            errors.append(
                f"External runtime '{framework}' auth_token_env must be a non-empty string."
            )
            continue

        if not _value(environment, secret_name):
            errors.append(
                f"External runtime '{framework}' references missing secret "
                f"environment variable '{secret_name}'."
            )

    return len(payload)


def validate_deployment_config(
    environment: Mapping[str, str] | None = None,
) -> DeploymentConfigReport:
    """Validate deployment settings and fail closed for unsafe production config."""

    env = os.environ if environment is None else environment
    deployment_environment = _value(
        env,
        "MODELFORGE_ENV",
        "development",
    ).lower()

    if deployment_environment not in VALID_ENVIRONMENTS:
        raise ProductionConfigError(
            "MODELFORGE_ENV must be one of: development, test, production."
        )

    auth_mode = _value(env, "MODELFORGE_AUTH_MODE", "disabled").lower()
    artifact_backend = _value(
        env,
        "MODEL_ARTIFACT_BACKEND",
        "local",
    ).lower()
    trusted_hosts = tuple(
        host.strip()
        for host in _value(env, "MODELFORGE_TRUSTED_HOSTS", "*").split(",")
        if host.strip()
    )
    public_base_url = _value(env, "MODELFORGE_PUBLIC_BASE_URL") or None

    errors: list[str] = []
    warnings: list[str] = []
    external_runtime_count = _runtime_configuration(
        env,
        errors=errors,
        warnings=warnings,
    )

    if deployment_environment == "production":
        database_url = _value(env, "DATABASE_URL")
        if not database_url or database_url == DEFAULT_DATABASE_URL:
            errors.append(
                "DATABASE_URL must be set to a non-development database in production."
            )

        if artifact_backend != "s3":
            errors.append(
                "MODEL_ARTIFACT_BACKEND must be 's3' in production."
            )
        if not _value(env, "MODEL_ARTIFACT_S3_BUCKET"):
            errors.append(
                "MODEL_ARTIFACT_S3_BUCKET is required in production."
            )

        if auth_mode != "oidc":
            errors.append("MODELFORGE_AUTH_MODE must be 'oidc' in production.")

        for name in (
            "MODELFORGE_OIDC_ISSUER",
            "MODELFORGE_OIDC_AUDIENCE",
            "MODELFORGE_OIDC_JWKS_URL",
            "MODELFORGE_OIDC_AUTHORIZATION_URL",
            "MODELFORGE_OIDC_TOKEN_URL",
            "MODELFORGE_OIDC_CLIENT_ID",
            "MODELFORGE_OIDC_REDIRECT_URI",
        ):
            if not _value(env, name):
                errors.append(f"{name} is required in production.")

        if not public_base_url:
            errors.append("MODELFORGE_PUBLIC_BASE_URL is required in production.")
        else:
            public_origin = _origin(public_base_url)
            if public_origin is None or public_origin[0] != "https":
                errors.append(
                    "MODELFORGE_PUBLIC_BASE_URL must be an absolute HTTPS URL."
                )

            parsed_public = urlsplit(public_base_url)
            if parsed_public.path not in {"", "/"} or parsed_public.query or parsed_public.fragment:
                errors.append(
                    "MODELFORGE_PUBLIC_BASE_URL must contain only the public origin."
                )

        redirect_uri = _value(env, "MODELFORGE_OIDC_REDIRECT_URI")
        if redirect_uri:
            redirect_origin = _origin(redirect_uri)
            if redirect_origin is None or redirect_origin[0] != "https":
                errors.append(
                    "MODELFORGE_OIDC_REDIRECT_URI must be an absolute HTTPS URL."
                )
            elif public_base_url and redirect_origin != _origin(public_base_url):
                errors.append(
                    "MODELFORGE_OIDC_REDIRECT_URI must use the public ModelForge origin."
                )

        if not _truthy(_value(env, "MODELFORGE_SESSION_COOKIE_SECURE", "true")):
            errors.append(
                "MODELFORGE_SESSION_COOKIE_SECURE must remain enabled in production."
            )

        if not trusted_hosts or "*" in trusted_hosts:
            errors.append(
                "MODELFORGE_TRUSTED_HOSTS must explicitly list production hosts."
            )
        elif public_base_url:
            hostname = urlsplit(public_base_url).hostname
            if hostname and hostname not in trusted_hosts:
                errors.append(
                    "MODELFORGE_TRUSTED_HOSTS must include the public ModelForge host."
                )

        if not _value(env, "MODELFORGE_METRICS_TOKEN"):
            errors.append(
                "MODELFORGE_METRICS_TOKEN is required to protect production metrics."
            )

    if errors:
        formatted = "\n- ".join(errors)
        raise ProductionConfigError(
            "Invalid ModelForge deployment configuration:\n- " + formatted
        )

    return DeploymentConfigReport(
        environment=deployment_environment,
        auth_mode=auth_mode,
        artifact_backend=artifact_backend,
        public_base_url=public_base_url,
        trusted_hosts=trusted_hosts,
        external_runtime_count=external_runtime_count,
        warnings=tuple(warnings),
    )
