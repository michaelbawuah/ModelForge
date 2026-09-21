variable "name" {
  description = "Prefix used for AWS resource names."
  type        = string
  default     = "modelforge"
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
  default     = "production"
}

variable "aws_region" {
  description = "AWS region for the ModelForge stack."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the ModelForge VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "domain_name" {
  description = "Public HTTPS hostname, for example modelforge.example.com."
  type        = string
}

variable "route53_zone_id" {
  description = "Optional Route53 hosted-zone ID. Leave null when DNS is managed elsewhere."
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "ACM certificate ARN covering domain_name."
  type        = string
}

variable "artifact_bucket_name" {
  description = "Optional globally unique S3 bucket name. A deterministic account/region name is used when null."
  type        = string
  default     = null
}

variable "artifact_prefix" {
  description = "S3 object prefix used by ModelForge."
  type        = string
  default     = "modelforge"
}

variable "image_tag" {
  description = "Immutable container image tag deployed to ECS."
  type        = string
  default     = "latest"
}

variable "activate_services" {
  description = "Start ECS services after images and secrets are populated and migrations have run."
  type        = bool
  default     = false
}

variable "api_desired_count" {
  description = "Desired ModelForge API task count when services are activated."
  type        = number
  default     = 2
}

variable "runtime_desired_count" {
  description = "Desired Go runtime task count when services are activated."
  type        = number
  default     = 2
}

variable "api_cpu" {
  description = "Fargate CPU units for the API task."
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Fargate memory in MiB for the API task."
  type        = number
  default     = 1024
}

variable "runtime_cpu" {
  description = "Fargate CPU units for the Go runtime task."
  type        = number
  default     = 256
}

variable "runtime_memory" {
  description = "Fargate memory in MiB for the Go runtime task."
  type        = number
  default     = 512
}

variable "api_workers" {
  description = "Uvicorn worker count per API task."
  type        = number
  default     = 2
}

variable "ha_nat_gateways" {
  description = "Create one NAT gateway per application AZ instead of one shared NAT gateway."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  description = "RDS MySQL instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial RDS storage in GiB."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum RDS storage autoscaling limit in GiB."
  type        = number
  default     = 100
}

variable "db_multi_az" {
  description = "Enable Multi-AZ RDS deployment."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Protect the production database from accidental deletion."
  type        = bool
  default     = true
}

variable "db_name" {
  description = "ModelForge database name."
  type        = string
  default     = "modelforge"
}

variable "db_username" {
  description = "RDS master username. RDS manages the password in Secrets Manager."
  type        = string
  default     = "modelforge"
}

variable "mysql_engine_version" {
  description = "Optional RDS MySQL engine version. Null lets AWS choose the current default supported by the provider."
  type        = string
  default     = null
}

variable "oidc_issuer" {
  description = "OIDC issuer URL."
  type        = string
}

variable "oidc_audience" {
  description = "OIDC audience expected by ModelForge."
  type        = string
}

variable "oidc_jwks_url" {
  description = "OIDC JWKS URL."
  type        = string
}

variable "oidc_authorization_url" {
  description = "OIDC authorization endpoint."
  type        = string
}

variable "oidc_token_url" {
  description = "OIDC token endpoint."
  type        = string
}

variable "oidc_client_id" {
  description = "OIDC client ID."
  type        = string
}

variable "oidc_scope" {
  description = "OIDC scopes requested during browser login."
  type        = string
  default     = "openid profile email"
}

variable "oidc_client_secret_required" {
  description = "Create and inject a Secrets Manager slot for a confidential OIDC client."
  type        = bool
  default     = false
}

variable "private_dns_namespace" {
  description = "Private Cloud Map DNS namespace used for external runtimes."
  type        = string
  default     = "modelforge.internal"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention period."
  type        = number
  default     = 30
}

variable "github_oidc_provider_arn" {
  description = "Existing AWS IAM OIDC provider ARN for token.actions.githubusercontent.com. Null disables creation of the GitHub deploy role."
  type        = string
  default     = null
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the optional deploy role."
  type        = string
  default     = "michaelbawuah/ModelForge"
}

variable "github_repository_owner_id" {
  description = "Immutable GitHub owner ID for the deploy role's OIDC subject. Update for a different owner."
  type        = string
  default     = "273423923"
}

variable "github_repository_id" {
  description = "Immutable GitHub repository ID for the deploy role's OIDC subject. Update for a fork."
  type        = string
  default     = "1373471661"
}

variable "github_environment" {
  description = "GitHub environment encoded into the OIDC subject for production releases."
  type        = string
  default     = "production"
}
