# ModelForge

**ModelForge** is a reliability-aware machine learning deployment and inference platform for registering, versioning, deploying, serving, and monitoring ML models.

The project explores the systems engineering behind production ML: immutable model artifacts, transactional deployment state, runtime isolation, model caching, observability, rollback, and cross-language inference execution.

Rather than treating model serving as a single `/predict` endpoint, ModelForge treats it as a reliability problem spanning the model lifecycle from artifact registration to production execution.

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
DEPLOYING → ACTIVE
     │
     └────→ FAILED

ACTIVE → SUPERSEDED
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

### Observability and Readiness

ModelForge exposes serving metrics and system readiness information.

The observability layer tracks inference behavior such as prediction execution and cache activity, while readiness checks verify critical service dependencies before reporting the platform ready to serve traffic.

This creates the foundation for measuring reliability and performance rather than assuming them.

## Technology Stack

| Layer | Technology |
|---|---|
| API / Control Plane | Python, FastAPI |
| Database | MySQL |
| ORM | SQLAlchemy |
| Database Migrations | Alembic |
| ML Execution | PyTorch, ONNX Runtime |
| External Runtime | Go |
| Runtime Communication | HTTP / JSON |
| Metrics | Prometheus |
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

The project includes tests across the major system boundaries:

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

- distributed caching and coordination
- asynchronous inference and worker execution
- runtime fleet health management
- retry, circuit-breaker, and resilience policies
- canary deployment strategies
- automated rollback policies
- load and performance testing
- failure-injection experiments
- cloud deployment
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
