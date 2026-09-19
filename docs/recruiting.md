# ModelForge Recruiting Brief

## 30-second pitch

ModelForge is a reliability-aware ML deployment platform I built to explore the systems problems that appear after model training. It combines a Python/FastAPI control plane, MySQL-backed model and deployment state, framework-specific in-process runtimes, and a standalone Go inference runtime behind a framework-agnostic protocol. The platform supports immutable artifacts, transactional promotion and rollback, weighted canary releases, retries, circuit breakers, automatic stable fallback, Prometheus metrics, a browser dashboard, and a CLI. The current post-merge CI checkpoint passes 121 Python tests and validates the full stack end to end.

## Resume bullets

- Built **ModelForge**, a reliability-aware ML deployment platform in **Python/FastAPI, MySQL, SQLAlchemy, Docker, and Go**, supporting immutable model versioning, deployment lifecycle management, PyTorch/ONNX execution, and framework-independent external runtimes.
- Designed a framework-agnostic runtime boundary with **bounded retries, exponential backoff, circuit breakers, health checks, Prometheus metrics, weighted canary releases, rollback, and automatic stable fallback** so future ML frameworks can integrate without control-plane rewrites.
- Shipped an operator-facing **web dashboard + installable CLI + seeded stable/canary demo** and validated the production path with **121 passing Python tests** plus end-to-end CI that completed **200/200 requests at 0% error, 133.5 req/s, and 231.2 ms p95 latency** on a GitHub-hosted runner.

## One-line project description

Production-style ML deployment platform with framework-independent runtimes, transactional rollout/rollback, canary traffic, runtime resilience, observability, and cross-language Go inference.

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

The repository includes reproducible load generation, fault injection, CI artifacts, p50/p95/p99 latency, throughput, error-rate, and traffic-lane reporting.

## 60-second interview answer

I built ModelForge because training a model is only one piece of an ML system. I wanted to understand what happens when you need to version artifacts, move traffic safely, isolate framework dependencies, recover from runtime failures, and prove which model actually served a request.

The control plane is FastAPI with MySQL and SQLAlchemy. Models are registered as immutable versions with checksums. Deployments have explicit lifecycle state, and environments have authoritative serving targets. For execution, ModelForge supports in-process runtimes like PyTorch and ONNX, but the important design choice is the external runtime contract. The Go runtime proves the control plane can serve through another language and process without adding Go-specific inference logic to the core.

Then I added reliability: retries, exponential backoff, circuit breakers, health inspection, weighted canaries, promotion, abort, rollback, and automatic stable fallback. I also added a dashboard, CLI, fault injection, and benchmark harness. The final post-merge CI run passed 121 Python tests and exercised the live Compose stack end to end.

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
2. Seed the demo with `python demo/bootstrap_demo.py --environment demo --weight 20`.
3. Open `http://localhost:8000/dashboard`.
4. Show stable and canary deployment targets.
5. Run live predictions and point out deployment ID, model-version ID, traffic lane, cache state, and canary fallback metadata.
6. Run `modelforge runtimes` to show the Go runtime health and circuit state.
7. Reweight or promote the canary from the dashboard or CLI.
8. Point to the benchmark/fault-injection section and explain how resilience behavior is measured.

## Validated metrics to use carefully

- 121 Python tests passed; 3 skipped in the standard Python CI job.
- Go formatting, tests, and vet checks passed.
- 200/200 benchmark requests succeeded with 0% error.
- 133.5 requests/s in the post-merge GitHub-hosted CI smoke run.
- p50 137.3 ms, p95 231.2 ms, p99 322.8 ms end-to-end latency in that same run.

Always qualify the throughput/latency values as **GitHub-hosted CI smoke results**, not universal production limits.
