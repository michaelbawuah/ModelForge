resource "aws_secretsmanager_secret" "runtime_token" {
  name                    = "${var.name}/${var.environment}/runtime-token"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "metrics_token" {
  name                    = "${var.name}/${var.environment}/metrics-token"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "oidc_client_secret" {
  count = var.oidc_client_secret_required ? 1 : 0

  name                    = "${var.name}/${var.environment}/oidc-client-secret"
  recovery_window_in_days = 7
}
