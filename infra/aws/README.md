# AWS Reference Deployment

This directory is a production-shaped AWS reference deployment for ModelForge.
It keeps AWS concerns outside ModelForge core: framework/runtime integration
still happens only through the external runtime contract.

## Architecture

```text
Internet
   |
Route53 / external DNS
   |
ACM TLS
   |
Application Load Balancer
   |
private application subnets
   |
   +-- ECS/Fargate: ModelForge API
   |      |
   |      +-- RDS MySQL (private DB subnets)
   |      +-- S3 artifact bucket through a VPC gateway endpoint
   |      +-- Secrets Manager
   |      +-- OIDC provider through NAT egress
   |
   +-- ECS/Fargate: Go runtime
          |
          +-- Cloud Map private DNS: go-runtime.modelforge.internal
```

The runtime service has no public load balancer and accepts port 8090 only from
the API security group. RDS accepts MySQL only from the API/migration security
group. API tasks accept port 8000 only from the ALB.

## Why services start at zero

The first Terraform apply creates infrastructure, ECR repositories, task
definitions, secret slots, RDS, networking, the artifact bucket, and the ALB,
but `activate_services=false` keeps the ECS desired counts at zero.

That gives the release a safe order:

1. provision infrastructure;
2. populate secrets;
3. build and push immutable images;
4. run the migration task;
5. activate services.

No half-configured public API is allowed to boot during the bootstrap apply.

## 1. Configure Terraform

```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

Use an ACM certificate that covers `domain_name`. When
`route53_zone_id` is set, Terraform creates the ALB alias record. Otherwise
point your DNS provider at the `alb_dns_name` output after apply.

For stronger multi-AZ resilience, set:

```hcl
ha_nat_gateways = true
db_multi_az     = true
```

Those settings increase AWS cost, so the checked-in example keeps them disabled
until explicitly selected.

## 2. Populate secret slots

Terraform creates secret resources but never writes customer secret values into
Terraform state.

Generate and store the runtime bearer token:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw runtime_token_secret_arn)" \
  --secret-string "$(openssl rand -hex 32)"
```

Protect Prometheus metrics with a separate token:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw metrics_token_secret_arn)" \
  --secret-string "$(openssl rand -hex 32)"
```

RDS manages and rotates its own master password through Secrets Manager. If
`oidc_client_secret_required=true`, populate the
`oidc_client_secret_arn` output in the same way with the client secret issued
by your identity provider.

## 3. Build and push images

Authenticate Docker to ECR:

```bash
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGION="$(terraform output -raw artifact_bucket >/dev/null; aws configure get region)"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin \
    "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
```

Build Linux/amd64 images to match the ECS task definitions:

```bash
API_REPO="$(terraform output -raw api_ecr_repository_url)"
RUNTIME_REPO="$(terraform output -raw runtime_ecr_repository_url)"
TAG="YOUR_GIT_SHA"

docker buildx build \
  --platform linux/amd64 \
  -t "$API_REPO:$TAG" \
  --push \
  ../..

docker buildx build \
  --platform linux/amd64 \
  -t "$RUNTIME_REPO:$TAG" \
  --push \
  ../../runtimes/go-runtime
```

Set the same immutable tag in `terraform.tfvars`:

```hcl
image_tag = "YOUR_GIT_SHA"
```

Apply once so the migration task definition points at that image:

```bash
terraform apply
```

## 4. Run the release migration task

```bash
CLUSTER="$(terraform output -raw ecs_cluster_name)"
TASK="$(terraform output -raw migration_task_definition_arn)"
SG="$(terraform output -raw api_security_group_id)"
SUBNETS="$(terraform output -json private_app_subnet_ids | jq -r 'join(",")')"

aws ecs run-task \
  --cluster "$CLUSTER" \
  --launch-type FARGATE \
  --task-definition "$TASK" \
  --network-configuration \
  "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}"
```

Wait for that task to stop and verify its exit code is zero before activating
the API.

## 5. Activate ModelForge

Set:

```hcl
activate_services = true
```

Then:

```bash
terraform apply
```

The ALB health check uses `/ready`, so traffic is sent only after the API can
reach MySQL. ECS deployment circuit breakers roll back task deployments that
cannot become healthy.

## 6. Release verification

Verify:

```bash
curl -fsS "$(terraform output -raw public_url)/health"
curl -fsS "$(terraform output -raw public_url)/ready"
```

Then exercise the product lifecycle through the browser or workspace API key:

```text
login
  -> create/select workspace
  -> create API key
  -> register model/version
  -> deploy stable
  -> start canary
  -> predict
  -> promote or roll back
```

## Security boundaries

- only the ALB is publicly reachable;
- API and runtime tasks run without public IPs;
- RDS has no public endpoint;
- S3 public access is blocked and TLS is enforced;
- artifact S3 permission exists only on the API task role;
- the runtime receives no S3 permission;
- RDS manages its master password in Secrets Manager;
- Terraform creates runtime/metrics/OIDC secret slots without storing values;
- ECS receives secrets through task-definition secret references;
- runtime HTTP traffic is bearer-authenticated in addition to private-network isolation.

## Cost boundary

NAT gateways, ALB, RDS, Fargate, CloudWatch, and public IPv4 resources can incur
ongoing AWS charges. Destroy disposable environments when they are no longer
needed. Production databases default to deletion protection; disable that
setting explicitly before destroying a protected database.


## GitHub Actions production releases

After the first infrastructure bootstrap, ModelForge can release from
[`.github/workflows/release-aws.yml`](../../.github/workflows/release-aws.yml)
without storing long-lived AWS access keys in GitHub.

The workflow is manual, runs only from `main`, targets the GitHub
`production` environment, and uses GitHub's OIDC token to assume an AWS role.
It then:

1. builds immutable API and Go-runtime images;
2. pushes both images to ECR;
3. registers new API/runtime/migration task-definition revisions;
4. runs the migration task and requires exit code 0;
5. deploys the runtime and waits for ECS stability;
6. deploys the API and waits for ECS stability;
7. verifies public `/health` and `/ready`;
8. rolls services back to their previous task definitions if deployment or
   verification fails.

### AWS OIDC trust

AWS accounts normally have one GitHub OIDC provider for
`https://token.actions.githubusercontent.com`. Pass that provider ARN into:

```hcl
github_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
```

Terraform then creates `github_actions_deploy_role_arn`. Its trust policy is
restricted to:

```text
repo:michaelbawuah/ModelForge:environment:production
```

If this repository is forked or renamed, override `github_repository`. If a
different protected GitHub environment is used, override
`github_environment`.

The deploy policy grants only the release-plane permissions required for the
two ECR repositories, ECS service/task operations, and passing the existing
ModelForge ECS roles.

### GitHub repository variables

Configure these non-secret GitHub Actions variables:

```text
AWS_DEPLOY_ROLE_ARN=<terraform output github_actions_deploy_role_arn>
AWS_REGION=us-east-1
MODELFORGE_PUBLIC_URL=https://modelforge.example.com
```

The workflow derives the standard Terraform resource names automatically.
Only set these optional variables when the Terraform naming defaults were
changed:

```text
MODELFORGE_NAME
MODELFORGE_ENVIRONMENT
MODELFORGE_ECS_CLUSTER
MODELFORGE_API_SERVICE
MODELFORGE_RUNTIME_SERVICE
MODELFORGE_API_ECR_REPOSITORY
MODELFORGE_RUNTIME_ECR_REPOSITORY
```

Use GitHub environment protection rules on `production` when release approval
is required. The AWS trust policy binds the OIDC subject to that environment,
so changing the workflow branch alone cannot satisfy the production role's
trust condition.
