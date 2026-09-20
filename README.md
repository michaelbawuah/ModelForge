# ModelForge

**ModelForge** is a reliability-aware machine learning deployment and inference platform for registering, versioning, deploying, serving, and monitoring ML models.

The project explores the systems engineering behind production ML: immutable model artifacts, transactional deployment state, runtime isolation, model caching, observability, rollback, and cross-language inference execution.

Rather than treating model serving as a single `/predict` endpoint, ModelForge treats it as a reliability problem spanning the model lifecycle from artifact registration to production execution.

## Project Snapshot

| Signal | Current validated result |
|---|---|
| Python test suite | **164 passed**, 3 skipped |
| Go validation | `gofmt`, `go test ./...`, and `go vet ./...` green |
| CI benchmark | **200 / 200 successful requests**, 0% errors |
| Throughput | **133.5 requests/s** |
| End-to-end latency | **p50 137.3 ms · p95 231.2 ms · p99 322.8 ms** |
| Runtime boundary | Python control plane + standalone Go inference service |
| Release safety | weighted canaries, rollback, circuit breakers, automatic stable fallback |
| Deployment proof | PASS — canary promotion, rollback, 185.7% regression detection, failed-canary abort, stable-target preservation |
| Product surfaces | public landing page, multi-tenant SaaS console, REST/OpenAPI, authenticated CLI |

> Benchmark values above come from the post-merge GitHub Actions smoke run on a hosted Ubuntu runner. They are reproducible validation evidence, not hardware-independent production performance claims.

## Quick Demo

Start the full stack:

```bash
docker compose up --build --wait --detach
```

Run the full deployment proof:

```bash
make proof
```

The proof creates three immutable versions and exercises the actual serving path:
stable deployment, weighted canary traffic, canary promotion, rollback, an
intentionally regressed canary, automated abort, and final stable-target
verification. It writes JSON/JSONL/Markdown evidence to
`demo-proof-evidence/` and exits non-zero if any lifecycle assertion fails.

For the smaller interactive stable + canary seed:

```bash
python demo/bootstrap_demo.py --environment demo --weight 20
```

Open the public product landing page:

```text
http://localhost:8000/
```

Open the ModelForge SaaS console:

```text
http://localhost:8000/dashboard
```

Or use the CLI:

```bash
modelforge status
modelforge deployments --environment demo
modelforge runtimes
modelforge predict demo 10
```

The full proof goes further: it proves both canary lanes serve real requests,
promotes version `2.0.0`, rolls back to version `1.0.0`, then detects a large
output regression in version `3.0.0` and aborts that canary while preserving
the stable target. Both the dashboard and CLI operate through the public
ModelForge API rather than bypassing deployment state internally.

## Architecture

```text
                         ┌──────────────────────┐
                         │      ModelForge      │
                         │   FastAPI Control    │
                         │        Plane         │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
       Model Registry        Deployment State       Observability
       + Versioning          + Environment          + Readiness
              │                Targets              + Metrics
              │                     │
              └──────────┬──────────┘
                         │
                         ▼
                  Runtime Resolver
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
       In-Process Runtime      External Runtime
              │                     │
        ┌─────┴─────┐               │ HTTP
        │           │               ▼
     PyTorch       ONNX        Go Runtime Service
        │           │               │
        └─────┬─────┘               │
              │                     │
              └──────────┬──────────┘
                         ▼
                     Prediction
```

## Implemented Capabilities

### Public SaaS Console and CLI

ModelForge now includes a public landing page plus a multi-tenant browser console on top of the same API used by automation.

The browser console at `/dashboard` exposes:

- authenticated user identity and workspace selection
- first-deployment onboarding
- workspace API-key creation, one-time secret reveal, listing, and revocation
- API readiness and external-runtime health
- model and immutable-version inventory
- deployment state by environment
- stable/canary targets and traffic weights
- runtime mode, circuit state, and failure count
- live inference with model-version and traffic-lane metadata
- promotion, rollback, canary reweight, promotion, and abort actions

Browser authentication uses OIDC Authorization Code + PKCE with nonce binding, opaque server-side sessions, HttpOnly session cookies, double-submit CSRF protection, and a strict Content Security Policy with packaged external CSS/JavaScript assets.

The installable `modelforge` CLI supports workspace API keys and exposes the same operational model for terminal and CI workflows, including health inspection, deployment inventory, prediction, rollback, and canary operations.

### SaaS Tenancy and Access Control

Customer-owned resources are scoped to workspaces. Models, deployments, environment targets, canaries, artifacts, API keys, and inference requests all resolve inside the authenticated workspace boundary.

The SaaS foundation includes:

- users, workspaces, workspace membership, and role hierarchy;
- vendor-neutral OIDC bearer-token verification;
- opaque browser sessions with server-side expiry/revocation state;
- high-entropy `mf_live_...` API keys stored only as one-way hashes;
- per-workspace artifact namespaces;
- self-hosted compatibility through `MODELFORGE_AUTH_MODE=disabled`.

### Cloud Artifact Storage

The artifact abstraction supports both local filesystem storage for self-hosting and S3-compatible object storage for hosted deployments.

The cloud backend preserves immutable publication, SHA-256 integrity verification, tenant-separated object keys, and verified local materialization for in-process runtimes. S3-compatible endpoints can be configured without changing registry or inference semantics.

### Model Registry and Artifact Management

ModelForge provides a MySQL-backed registry for models and immutable model versions.

Model artifacts are stored through an artifact abstraction with:

- SHA-256 integrity verification
- immutable version identity
- bounded-memory streaming writes
- atomic artifact publication
- safe path validation
- protection against accidental overwrite
- integrity validation before model loading

This creates a trusted boundary between registered model metadata and the artifact that is actually executed.

### Transactional Deployment Lifecycle

ModelForge models deployment as explicit state rather than simply changing a model pointer.

Deployment states include:

```text
DEPLOYING ──→ ACTIVE ──→ SUPERSEDED
    │            │
    ├──→ CANARY ─┘
    │      │
    └────→ FAILED
```

Environment targets identify the authoritative active deployment.

The deployment layer supports:

- transactional model promotion
- environment-specific deployment targets
- rollback to previous deployments
- failure recording
- row locking for concurrent state changes
- protection against invalid lifecycle transitions

### Integrity-Aware Inference Serving

The prediction pipeline resolves:

```text
Environment
    ↓
Deployment Target
    ↓
ACTIVE Deployment
    ↓
Model Version
    ↓
Runtime Resolver
    ↓
Artifact Verification / Runtime Execution
    ↓
Prediction
```

For in-process models, artifacts are verified before their first load and cached by immutable model-version identity.

Cache lookup, loading, insertion, and hit determination are synchronized to prevent duplicate first-load work and inaccurate cache-hit reporting.

### Extensible Runtime System

ModelForge separates deployment orchestration from framework-specific model execution.

The runtime abstraction allows the serving layer to execute models without embedding framework-specific logic into the control plane.

Implemented runtime support includes:

- native ModelForge JSON test runtime
- PyTorch runtime
- ONNX runtime
- dynamically discoverable runtime plugins
- isolated external runtime services

A framework can therefore integrate with ModelForge without modifying the core inference pipeline.

### Runtime Plugin Discovery

Runtime plugins can be discovered dynamically and registered with the runtime system.

This allows independently supplied frameworks to participate in ModelForge inference while keeping the core platform framework-agnostic.

End-to-end tests verify that a runtime unknown to ModelForge core can register, deploy, and serve a model through the same inference path.

### External Runtime Isolation

ModelForge supports runtimes executing outside the Python control-plane process.

The runtime resolver chooses between:

```text
                  Framework
                      │
                      ▼
               Runtime Resolver
                 /          \
                /            \
        In Process          External
            │                  │
     Python Runtime       HTTP Boundary
                               │
                         Runtime Service
```

This provides a foundation for:

- language-independent inference runtimes
- framework dependency isolation
- independent runtime scaling
- crash isolation
- specialized execution environments

### Cross-Language Go Runtime

ModelForge includes a standalone inference runtime implemented in **Go**.

The Go runtime runs as an independent HTTP service and implements:

- `/health` health checking
- `/predict` inference
- structured JSON request/response handling
- model metadata validation
- runtime-level input validation
- structured logging
- graceful HTTP server shutdown
- Go unit and server tests

Example:

```text
Python ModelForge Control Plane
              │
              │ HTTP
              ▼
       Go Runtime Service
              │
              ▼
          Prediction
```

Live integration tests exercise the Python external-runtime client against the running Go service, proving that ModelForge can execute inference across a real language and process boundary.

### Runtime Resilience

External runtimes are protected by framework-independent resilience policies:

- bounded retries for transient transport and server failures
- exponential retry backoff
- per-runtime circuit breakers
- automatic half-open recovery after a cooldown window
- runtime inventory and health inspection endpoints
- Prometheus counters for requests, retries, and open-circuit rejections

These policies live at the runtime boundary, so the same reliability behavior
applies to Go, Fluxion, or a framework that does not exist yet.

### Canary Releases and Automatic Fallback

ModelForge can keep a stable deployment active while routing a configurable
percentage of traffic to a canary.

The canary lifecycle supports:

- transactional canary start
- weighted traffic routing
- traffic reweighting
- canary promotion to stable
- manual canary abort
- automatic removal of a canary after serving infrastructure failures
- immediate fallback to the stable deployment for the triggering request

Prediction responses identify whether they were served by the stable or canary
lane and whether automatic fallback occurred.

### Load Testing and Failure Injection

ModelForge includes a reproducible benchmark harness for exercising the full
HTTP serving path and reporting:

- throughput in requests per second
- success and error rates
- p50, p95, and p99 end-to-end latency
- HTTP status-code distribution
- stable versus canary traffic counts
- automatic canary fallback counts

Create an external Go-runtime benchmark deployment and run load:

```bash
python benchmarks/bootstrap_external.py \
  --environment benchmark-go \
  --output benchmark-bootstrap.json

python benchmarks/load_test.py \
  --environment benchmark-go \
  --requests 5000 \
  --concurrency 50 \
  --warmup 100 \
  --output benchmark-results.json
```

The Go runtime supports deterministic, opt-in fault injection:

```bash
MODELFORGE_GO_RUNTIME_FAIL_EVERY=2 \
MODELFORGE_GO_RUNTIME_DELAY_MS=25 \
docker compose up --build --wait
```

Fault injection defaults to disabled. It exists so retry, circuit-breaker,
latency, and fallback behavior can be reproduced without adding
framework-specific failure logic to the control plane.

CI also runs a smaller end-to-end benchmark smoke test and uploads its JSON
result as a workflow artifact. Hosted-runner measurements are validation
evidence rather than stable performance claims; release-quality numbers should
be captured on controlled hardware.

#### Latest post-merge CI baseline

| Metric | Result |
|---|---:|
| Requests | 200 |
| Successful | 200 / 200 |
| Error rate | 0.0% |
| Throughput | 133.5 requests/s |
| p50 latency | 137.3 ms |
| p95 latency | 231.2 ms |
| p99 latency | 322.8 ms |

The latest validation also smoke-tests the installed CLI, public landing page,
multi-tenant SaaS console, auth configuration, Docker Compose stack, external Go
runtime, and the full deployment validation scenario. In that scenario, v2 received
real weighted canary traffic and was promoted, v1 was restored through rollback,
and an intentionally regressed v3 produced 185.7% output drift against a 50%
threshold, was recorded FAILED, and left v1 as the authoritative final target.

### Observability and Readiness

ModelForge exposes serving metrics and system readiness information.

The observability layer tracks inference behavior such as prediction execution and cache activity, while readiness checks verify critical service dependencies before reporting the platform ready to serve traffic.

This creates the foundation for measuring reliability and performance rather than assuming them.

## Engineering Documentation

- [Architecture and system invariants](docs/architecture.md)
- [External runtime contract](docs/runtime-protocol.md)
- [Public-cloud deployment contract](docs/cloud-deployment.md)
- [AWS ECS/Fargate reference deployment](infra/aws/README.md)
- [Deployment validation scenario](docs/demo-proof.md)
- [Platform overview](docs/platform-overview.md)

Common workflows are available through the root `Makefile`:

```bash
make install
make check
make up
make demo
make proof
make benchmark
make down
```

## Technology Stack

| Layer | Technology |
|---|---|
| API / Control Plane | Python, FastAPI |
| Database | MySQL |
| Identity | OIDC Authorization Code + PKCE, opaque browser sessions, workspace API keys |
| Object Storage | Local filesystem or S3-compatible storage |
| ORM | SQLAlchemy |
| Database Migrations | Alembic |
| ML Execution | PyTorch, ONNX Runtime |
| External Runtime | Go |
| Runtime Communication | HTTP / JSON |
| Metrics | Prometheus |
| Cloud reference | AWS ECS/Fargate, RDS MySQL, S3, ALB, Cloud Map, Secrets Manager |
| Infrastructure as Code | Terraform |
| Testing | pytest, Go testing |
| Python Quality | Ruff |
| Go Quality | gofmt, go vet |

## Reliability Principles

ModelForge is being built around several engineering principles.

**Immutable model identity.**
A deployed model version represents a specific artifact rather than a mutable file.

**Verify before execution.**
Artifact checksums are validated before an in-process model enters the serving cache.

**Fail closed.**
Missing, corrupted, unsupported, or inconsistent serving state should produce an explicit failure rather than silently executing the wrong model.

**Transactional deployment state.**
Promotion and rollback modify authoritative deployment state through controlled transitions.

**Framework independence.**
The control plane should orchestrate models without becoming tightly coupled to every framework it supports.

**Runtime isolation.**
Model execution can cross process and language boundaries when dependency, reliability, or scaling requirements demand it.

**Measure claims.**
Reliability and performance characteristics should be demonstrated through tests, metrics, and experiments.

## Testing

The post-merge validation checkpoint currently reports **164 Python tests passed, 3 skipped**, with Go formatting, unit tests, and vet checks green. The project includes tests across the major system boundaries:

```text
Artifact storage
      ↓
Model registry
      ↓
Deployment lifecycle
      ↓
Runtime resolution
      ↓
Inference execution
      ↓
External runtime boundary
      ↓
Cross-language integration
```

Python validation:

```bash
python -m ruff check .
python -m pytest -q
git diff --check
```

Go runtime validation:

```bash
cd runtimes/go-runtime

gofmt -w .
go test ./...
go vet ./...
```

The repository also includes live integration tests for communication between ModelForge and the standalone Go runtime.

## Running the Full Platform

ModelForge can run locally as a multi-service stack with the Python control
plane, MySQL metadata store, and Go external runtime:

```bash
docker compose up --build
```

The stack exposes:

- ModelForge API: `http://localhost:8000`
- API readiness: `http://localhost:8000/ready`
- Prometheus metrics: `http://localhost:8000/metrics`
- Go runtime: `http://localhost:8090`
- MySQL: `localhost:3306`

The API boot sequence applies Alembic migrations before accepting traffic.
Model artifacts are stored in a named Docker volume so immutable artifacts
survive container restarts.

External runtimes are configured through
`MODELFORGE_EXTERNAL_RUNTIMES`, a JSON object keyed by framework name:

```json
{
  "framework-from-2036": {
    "name": "future-runtime",
    "base_url": "http://future-runtime:9000",
    "timeout_seconds": 5.0
  }
}
```

This keeps framework knowledge outside the control plane. A future framework
can provide an HTTP runtime implementing ModelForge's protocol and be wired in
through configuration rather than a core-code change.

## Running the Go Runtime

From the repository root:

```bash
cd runtimes/go-runtime
go run ./cmd/server
```

The service listens on port `8090` by default.

Health check:

```bash
curl http://localhost:8090/health
```

Example response:

```json
{
  "service": "modelforge-go-runtime",
  "status": "healthy"
}
```

The Python control plane can communicate with the service through ModelForge's external-runtime client.

## Roadmap

ModelForge is under active development.

Upcoming engineering milestones include:

- hosted AWS release evidence and production smoke validation
- controlled-hardware performance baselines
- distributed caching and coordination
- asynchronous inference and worker execution
- expanded serving observability

## Why ModelForge?

Training a model does not make it a production system.

A production ML platform must answer a different set of questions:

- Which exact model artifact is running?
- How was its integrity verified?
- Which deployment owns production traffic?
- What happens if promotion fails?
- Can the previous version be restored safely?
- How are loaded models cached?
- Can new frameworks integrate without changing the control plane?
- Can model execution be isolated from the platform process?
- Can runtimes be implemented in another language?
- Is the service actually healthy and ready?
- Can its reliability and performance claims be measured?

**ModelForge is an exploration of those systems problems.**
