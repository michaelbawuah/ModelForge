# Platform Overview

ModelForge manages the lifecycle of machine learning models from artifact
registration through deployment and inference. It combines a FastAPI control
plane, MySQL-backed model and deployment state, a browser console, an
authenticated CLI, and a standalone Go inference runtime.

## Model lifecycle

Model versions reference immutable artifacts with checksums. Deployments have
explicit lifecycle states, and each serving environment has an authoritative
target. Weighted canaries can receive live traffic before promotion. Operators
can abort a canary or roll back to a previous stable version.

## Runtime integration

The control plane supports in-process PyTorch and ONNX runtimes and an external
runtime protocol. The Go service implements that protocol in a separate
process. Other model frameworks can integrate through the same contract
without adding framework-specific inference logic to the control plane.

## Reliability and access

The serving path includes bounded retries, circuit breakers, health checks,
automatic stable fallback, and Prometheus metrics. Workspaces scope data and
API keys. Browser access uses OIDC Authorization Code with PKCE, opaque
sessions, CSRF protection, and a strict Content Security Policy.

## Validation and deployment

The repository includes a reproducible [deployment validation
scenario](demo-proof.md) covering stable serving, weighted canary traffic,
promotion, rollback, regression detection, failed-canary abort, and final
stable-target preservation. Benchmark results in the README were measured in
CI and should not be treated as production capacity estimates.

The [AWS reference deployment](../infra/aws/README.md) uses Terraform for
ECS/Fargate, RDS MySQL, S3, and supporting infrastructure. It is a deployment
reference; the public service has not yet been launched.
