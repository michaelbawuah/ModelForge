# ModelForge Recruiting Brief

## 30-second pitch

ModelForge is a reliability-aware ML deployment platform I built to explore the systems problems that appear after model training. It combines a Python/FastAPI control plane, MySQL-backed model and deployment state, framework-specific in-process runtimes, and a standalone Go inference runtime behind a framework-agnostic protocol. The platform supports immutable artifacts, transactional promotion and rollback, weighted canary releases, retries, circuit breakers, automatic stable fallback, Prometheus metrics, S3-compatible artifact storage, multi-tenant workspaces, secure OIDC browser sessions, a public SaaS console, an authenticated CLI, production configuration preflight, and a validated Terraform AWS reference deployment. The current post-merge CI checkpoint passes 164 Python tests and validates the full stack end to end.

## Resume bullets

- Built **ModelForge**, a reliability-aware ML deployment platform in **Python/FastAPI, MySQL, SQLAlchemy, Docker, and Go**, supporting immutable model versioning, deployment lifecycle management, PyTorch/ONNX execution, and framework-independent external runtimes.
- Designed a framework-agnostic runtime boundary with **bounded retries, exponential backoff, circuit breakers, health checks, Prometheus metrics, weighted canary releases, rollback, and automatic stable fallback** so future ML frameworks can integrate without control-plane rewrites.
- Shipped a **multi-tenant SaaS console + authenticated CLI + reproducible deployment proof**, with OIDC/PKCE browser sessions, hashed workspace API keys, strict CSP, S3-compatible artifacts, and a validated AWS ECS/Fargate + RDS + S3 Terraform reference; CI passes **164 Python tests** and the proof exercises weighted canary traffic, promotion, rollback, regression detection, failed-canary abort, and stable-target preservation through the public API.

## One-line project description

Production-style, multi-tenant ML deployment platform with framework-independent runtimes, immutable cloud artifacts, safe canary rollout/rollback, runtime resilience, observability, secure OIDC/API-key access, and cross-language Go inference.

## What makes the project technically strong

### 1. Framework independence

The control plane does not need framework-specific branches for every future model format. A new framework can implement the documented external runtime contract and register a framework identifier through configuration.

### 2. Reliability is part of the serving path

Retries, backoff, circuit breakers, canary routing, rollback, automatic fallback, health inspection, and metrics are implemented as platform behavior rather than demo-only scripts.

### 3. Model identity is immutable

Deployments point to immutable model versions and verified artifacts rather than mutable filesystem locations.

### 4. Cross-language execution is real

The reference Go runtime runs as a separate HTTP service and participates in the same deployment/inference flow as in-process runtimes.

### 5. Claims are measured

The repository includes reproducible load generation, fault injection, CI artifacts, p50/p95/p99 latency, throughput, error-rate, and traffic-lane reporting. A recruiter-proof harness also exercises stable serving, weighted canary traffic, promotion, rollback, regression detection, canary abort, and final stable-target preservation through the public API.

## 60-second interview answer

I built ModelForge because training a model is only one piece of an ML system. I wanted to understand what happens when you need to version artifacts, move traffic safely, isolate framework dependencies, recover from runtime failures, and prove which model actually served a request.

The control plane is FastAPI with MySQL and SQLAlchemy. Models are registered as immutable versions with checksums. Deployments have explicit lifecycle state, and environments have authoritative serving targets. For execution, ModelForge supports in-process runtimes like PyTorch and ONNX, but the important design choice is the external runtime contract. The Go runtime proves the control plane can serve through another language and process without adding Go-specific inference logic to the core.

Then I added reliability: retries, exponential backoff, circuit breakers, health inspection, weighted canaries, promotion, abort, rollback, and automatic stable fallback. I also turned the control plane into a multi-tenant SaaS foundation with workspaces, hashed API keys, OIDC Authorization Code + PKCE browser sessions, CSRF protection, strict CSP, and S3-compatible artifacts. The product has a public landing page, browser console, CLI, fault injection, and benchmark harness. The validated public-product checkpoint passes 164 Python tests and exercises the live Compose stack end to end.

## Good interview follow-up topics

- Why use immutable model-version identity instead of mutable artifact paths?
- How does transactional deployment state prevent split-brain serving decisions?
- Why isolate some runtimes out of process?
- What should happen when a canary runtime fails after receiving traffic?
- Why are circuit breakers per runtime instead of global?
- How would the current process-local cache evolve into a distributed serving system?
- What guarantees does the external runtime contract intentionally provide, and what is left runtime-specific?
- Why are CI benchmark numbers presented as validation evidence rather than production capacity claims?

## Demo script

1. Start the stack with `docker compose up --build --wait --detach`.
2. Run `make proof`.
3. Open `http://localhost:8000/` to show the public product, then enter `/dashboard` for the SaaS console.
4. Open `demo-proof-evidence/proof-report.md` and show that v2 received real weighted canary traffic before promotion.
5. Show that the proof promoted v2 and then rolled back to v1 through the deployment lifecycle.
6. Show the intentionally regressed v3 canary: the proof detects its output drift, aborts it, and ModelForge records the deployment as `FAILED` with a failure reason.
7. Show that the final environment target still points to stable v1 with no canary configured.
8. Run `modelforge runtimes` to show the Go runtime health and circuit state, then connect the same lifecycle to the AWS/Terraform/release-automation story.

The same proof harness accepts `MODELFORGE_URL`, `MODELFORGE_API_KEY`, and
`MODELFORGE_WORKSPACE`, so the identical scenario can be run against a hosted
multi-tenant deployment without modifying the script.

## Validated metrics to use carefully

- 164 Python tests passed; 3 skipped in the standard Python CI job.
- Full deployment proof passed in the live Compose stack: v2 canary promotion,
  rollback to v1, v3 output drift of 185.7% against a 50% threshold, v3 marked
  FAILED, and v1 preserved as the final active target.
- Go formatting, tests, and vet checks passed.
- 200/200 benchmark requests succeeded with 0% error.
- 133.5 requests/s in the post-merge GitHub-hosted CI smoke run.
- p50 137.3 ms, p95 231.2 ms, p99 322.8 ms end-to-end latency in that same run.

Always qualify the throughput/latency values as **GitHub-hosted CI smoke results**, not universal production limits.
