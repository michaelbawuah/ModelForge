output "public_url" {
  description = "Configured public ModelForge URL."
  value       = "https://${var.domain_name}"
}

output "alb_dns_name" {
  description = "ALB DNS name. Use this when DNS is managed outside Route53."
  value       = aws_lb.api.dns_name
}

output "api_ecr_repository_url" {
  description = "ECR repository for the ModelForge API image."
  value       = aws_ecr_repository.api.repository_url
}

output "runtime_ecr_repository_url" {
  description = "ECR repository for the Go runtime image."
  value       = aws_ecr_repository.runtime.repository_url
}

output "runtime_token_secret_arn" {
  description = "Populate this Secrets Manager secret before activating services."
  value       = aws_secretsmanager_secret.runtime_token.arn
}

output "metrics_token_secret_arn" {
  description = "Populate this Secrets Manager secret before activating services."
  value       = aws_secretsmanager_secret.metrics_token.arn
}

output "oidc_client_secret_arn" {
  description = "OIDC client secret slot when oidc_client_secret_required=true."
  value = (
    var.oidc_client_secret_required
    ? aws_secretsmanager_secret.oidc_client_secret[0].arn
    : null
  )
}

output "database_master_secret_arn" {
  description = "RDS-managed master credential secret."
  value       = aws_db_instance.modelforge.master_user_secret[0].secret_arn
  sensitive   = true
}

output "artifact_bucket" {
  description = "Immutable ModelForge artifact bucket."
  value       = aws_s3_bucket.artifacts.bucket
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "migration_task_definition_arn" {
  description = "Run this task definition once per release before activating new API tasks."
  value       = aws_ecs_task_definition.migration.arn
}

output "private_app_subnet_ids" {
  value = [for subnet in aws_subnet.app : subnet.id]
}

output "api_security_group_id" {
  value = aws_security_group.api.id
}

output "github_actions_deploy_role_arn" {
  description = "OIDC deploy role ARN when github_oidc_provider_arn is configured."
  value = (
    var.github_oidc_provider_arn == null
    ? null
    : aws_iam_role.github_actions_deploy[0].arn
  )
}
