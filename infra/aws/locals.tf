data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  public_subnets = {
    for index, az in local.azs :
    az => cidrsubnet(var.vpc_cidr, 8, index)
  }

  app_subnets = {
    for index, az in local.azs :
    az => cidrsubnet(var.vpc_cidr, 8, index + 10)
  }

  db_subnets = {
    for index, az in local.azs :
    az => cidrsubnet(var.vpc_cidr, 8, index + 20)
  }

  artifact_bucket_name = (
    var.artifact_bucket_name != null
    ? var.artifact_bucket_name
    : "${var.name}-${data.aws_caller_identity.current.account_id}-${var.aws_region}-artifacts"
  )

  runtime_host = "go-runtime.${var.private_dns_namespace}"

  api_image     = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
  runtime_image = "${aws_ecr_repository.runtime.repository_url}:${var.image_tag}"

  api_environment = [
    { name = "MODELFORGE_ENV", value = "production" },
    { name = "PORT", value = "8000" },
    { name = "MODELFORGE_WORKERS", value = tostring(var.api_workers) },
    { name = "MODELFORGE_RUN_MIGRATIONS", value = "false" },
    { name = "MODELFORGE_FORWARDED_ALLOW_IPS", value = "*" },
    { name = "MODELFORGE_DATABASE_HOST", value = aws_db_instance.modelforge.address },
    { name = "MODELFORGE_DATABASE_PORT", value = tostring(aws_db_instance.modelforge.port) },
    { name = "MODELFORGE_DATABASE_NAME", value = var.db_name },
    { name = "MODELFORGE_DATABASE_USER", value = var.db_username },
    { name = "MODEL_ARTIFACT_BACKEND", value = "s3" },
    { name = "MODEL_ARTIFACT_S3_BUCKET", value = aws_s3_bucket.artifacts.bucket },
    { name = "MODEL_ARTIFACT_S3_PREFIX", value = var.artifact_prefix },
    { name = "MODEL_ARTIFACT_CACHE_ROOT", value = "/tmp/modelforge-artifact-cache" },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "MODELFORGE_PUBLIC_BASE_URL", value = "https://${var.domain_name}" },
    { name = "MODELFORGE_TRUSTED_HOSTS", value = var.domain_name },
    { name = "MODELFORGE_SESSION_COOKIE_SECURE", value = "true" },
    { name = "MODELFORGE_AUTH_MODE", value = "oidc" },
    { name = "MODELFORGE_OIDC_ISSUER", value = var.oidc_issuer },
    { name = "MODELFORGE_OIDC_AUDIENCE", value = var.oidc_audience },
    { name = "MODELFORGE_OIDC_JWKS_URL", value = var.oidc_jwks_url },
    { name = "MODELFORGE_OIDC_AUTHORIZATION_URL", value = var.oidc_authorization_url },
    { name = "MODELFORGE_OIDC_TOKEN_URL", value = var.oidc_token_url },
    { name = "MODELFORGE_OIDC_CLIENT_ID", value = var.oidc_client_id },
    { name = "MODELFORGE_OIDC_REDIRECT_URI", value = "https://${var.domain_name}/auth/callback" },
    { name = "MODELFORGE_OIDC_SCOPE", value = var.oidc_scope },
    {
      name = "MODELFORGE_EXTERNAL_RUNTIMES"
      value = jsonencode({
        "go-linear" = {
          name                      = "modelforge-go-runtime"
          base_url                  = "http://${local.runtime_host}:8090"
          timeout_seconds           = 2.0
          max_retries               = 2
          retry_backoff_seconds     = 0.05
          circuit_failure_threshold = 3
          circuit_reset_seconds     = 30.0
          auth_token_env            = "MODELFORGE_RUNTIME_TOKEN"
        }
      })
    },
  ]

  api_secrets = concat(
    [
      {
        name      = "MODELFORGE_DATABASE_PASSWORD"
        valueFrom = "${aws_db_instance.modelforge.master_user_secret[0].secret_arn}:password::"
      },
      {
        name      = "MODELFORGE_RUNTIME_TOKEN"
        valueFrom = aws_secretsmanager_secret.runtime_token.arn
      },
      {
        name      = "MODELFORGE_METRICS_TOKEN"
        valueFrom = aws_secretsmanager_secret.metrics_token.arn
      },
    ],
    var.oidc_client_secret_required ? [
      {
        name      = "MODELFORGE_OIDC_CLIENT_SECRET"
        valueFrom = aws_secretsmanager_secret.oidc_client_secret[0].arn
      }
    ] : []
  )

  execution_secret_arns = concat(
    [
      aws_db_instance.modelforge.master_user_secret[0].secret_arn,
      aws_secretsmanager_secret.runtime_token.arn,
      aws_secretsmanager_secret.metrics_token.arn,
    ],
    var.oidc_client_secret_required ? [
      aws_secretsmanager_secret.oidc_client_secret[0].arn
    ] : []
  )
}
