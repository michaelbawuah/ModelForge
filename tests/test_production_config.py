"""Tests for ModelForge deployment preflight validation."""

from __future__ import annotations

import pytest

from modelforge.core.config import (
    ProductionConfigError,
    resolve_database_url,
    validate_deployment_config,
)


def production_environment() -> dict[str, str]:
    return {
        "MODELFORGE_ENV": "production",
        "DATABASE_URL": (
            "mysql+pymysql://app:secret@mysql.internal:3306/modelforge"
        ),
        "MODEL_ARTIFACT_BACKEND": "s3",
        "MODEL_ARTIFACT_S3_BUCKET": "modelforge-production",
        "MODELFORGE_AUTH_MODE": "oidc",
        "MODELFORGE_OIDC_ISSUER": "https://identity.example.com/",
        "MODELFORGE_OIDC_AUDIENCE": "https://api.modelforge.example",
        "MODELFORGE_OIDC_JWKS_URL": (
            "https://identity.example.com/.well-known/jwks.json"
        ),
        "MODELFORGE_OIDC_AUTHORIZATION_URL": (
            "https://identity.example.com/authorize"
        ),
        "MODELFORGE_OIDC_TOKEN_URL": "https://identity.example.com/oauth/token",
        "MODELFORGE_OIDC_CLIENT_ID": "modelforge-web",
        "MODELFORGE_OIDC_REDIRECT_URI": (
            "https://modelforge.example/auth/callback"
        ),
        "MODELFORGE_PUBLIC_BASE_URL": "https://modelforge.example",
        "MODELFORGE_SESSION_COOKIE_SECURE": "true",
        "MODELFORGE_TRUSTED_HOSTS": "modelforge.example",
        "MODELFORGE_METRICS_TOKEN": "metrics-secret",
    }


def test_development_configuration_remains_self_host_friendly() -> None:
    report = validate_deployment_config({})

    assert report.environment == "development"
    assert report.auth_mode == "disabled"
    assert report.artifact_backend == "local"


def test_secure_production_configuration_passes() -> None:
    report = validate_deployment_config(production_environment())

    assert report.environment == "production"
    assert report.auth_mode == "oidc"
    assert report.artifact_backend == "s3"
    assert report.public_base_url == "https://modelforge.example"
    assert report.trusted_hosts == ("modelforge.example",)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MODEL_ARTIFACT_BACKEND", "local", "must be 's3'"),
        ("MODELFORGE_AUTH_MODE", "disabled", "must be 'oidc'"),
        ("MODELFORGE_SESSION_COOKIE_SECURE", "false", "must remain enabled"),
        ("MODELFORGE_TRUSTED_HOSTS", "*", "explicitly list production hosts"),
        ("MODELFORGE_PUBLIC_BASE_URL", "http://modelforge.example", "HTTPS URL"),
        ("MODELFORGE_METRICS_TOKEN", "", "required to protect production metrics"),
    ],
)
def test_production_preflight_rejects_unsafe_settings(
    name: str,
    value: str,
    message: str,
) -> None:
    environment = production_environment()
    environment[name] = value

    with pytest.raises(ProductionConfigError, match=message):
        validate_deployment_config(environment)


def test_external_runtime_secret_reference_must_resolve() -> None:
    environment = production_environment()
    environment["MODELFORGE_EXTERNAL_RUNTIMES"] = (
        '{"future-ai":{"base_url":"http://runtime.internal:9000",'
        '"auth_token_env":"FUTURE_RUNTIME_TOKEN"}}'
    )

    with pytest.raises(ProductionConfigError, match="FUTURE_RUNTIME_TOKEN"):
        validate_deployment_config(environment)


def test_external_runtime_without_auth_token_warns_instead_of_guessing_network_policy() -> None:
    environment = production_environment()
    environment["MODELFORGE_EXTERNAL_RUNTIMES"] = (
        '{"future-ai":{"base_url":"http://runtime.internal:9000"}}'
    )

    report = validate_deployment_config(environment)

    assert report.external_runtime_count == 1
    assert "trusted private network" in report.warnings[0]



def test_database_url_can_be_built_from_cloud_secret_components() -> None:
    environment = {
        "MODELFORGE_DATABASE_HOST": "db.internal",
        "MODELFORGE_DATABASE_PORT": "3307",
        "MODELFORGE_DATABASE_NAME": "modelforge",
        "MODELFORGE_DATABASE_USER": "app",
        "MODELFORGE_DATABASE_PASSWORD": "p@ss/word",
    }

    url = resolve_database_url(environment)

    assert url == (
        "mysql+pymysql://app:p%40ss%2Fword@db.internal:3307/modelforge"
    )


def test_production_accepts_database_components_without_full_url() -> None:
    environment = production_environment()
    environment.pop("DATABASE_URL")
    environment.update(
        {
            "MODELFORGE_DATABASE_HOST": "db.internal",
            "MODELFORGE_DATABASE_PORT": "3306",
            "MODELFORGE_DATABASE_NAME": "modelforge",
            "MODELFORGE_DATABASE_USER": "app",
            "MODELFORGE_DATABASE_PASSWORD": "secret",
        }
    )

    report = validate_deployment_config(environment)

    assert report.environment == "production"


def test_production_rejects_incomplete_database_components() -> None:
    environment = production_environment()
    environment.pop("DATABASE_URL")
    environment["MODELFORGE_DATABASE_HOST"] = "db.internal"

    with pytest.raises(ProductionConfigError, match="MODELFORGE_DATABASE_USER"):
        validate_deployment_config(environment)
