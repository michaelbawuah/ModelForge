# ModelForge Architecture

ModelForge separates **deployment orchestration** from **model execution**.

That separation is the central architectural decision in the project. The
control plane owns model identity, artifact integrity, deployment state,
traffic selection, observability, and rollback. Runtimes own framework-specific
loading and prediction.

## Control-plane responsibilities

The Python/FastAPI control plane is responsible for:

1. model registration and immutable version identity;
2. artifact storage and SHA-256 integrity verification;
3. deployment lifecycle state and authoritative environment targets;
4. stable/canary traffic selection;
5. rollback and automatic canary fallback;
6. runtime discovery and selection;
7. cache coordination for in-process runtimes;
8. retries, circuit breakers, metrics, readiness, and operational APIs;
9. workspace tenancy, user/API-key authorization, and browser-session security;
10. local or S3-compatible artifact persistence behind a shared storage contract.

The control plane should not need to understand how a framework performs tensor
operations, builds a graph, schedules kernels, or loads its native model
format.

## Runtime modes

ModelForge has two execution modes.

### In-process runtimes

An in-process runtime implements the Python runtime interface and is appropriate
when the framework can safely share the control-plane process.

Current examples include the built-in JSON runtime, PyTorch, and ONNX Runtime.

Optional framework dependencies are discovered at startup. ModelForge core can
boot without PyTorch or ONNX installed.

### External runtimes

An external runtime is a separate HTTP service. It can be implemented in any
language and packaged with any framework dependency stack.

The Go runtime is the reference implementation.

This boundary gives ModelForge:

- language independence;
- dependency isolation;
- crash isolation;
- independent scaling;
- a path for GPU- or accelerator-specific execution environments;
- compatibility with frameworks that do not exist when the control plane is
  released.

## Serving path

A normal request follows this path:

```text
POST /predict
      |
      v
Environment target
      |
      +---- weighted canary? ---- yes ---> CANARY deployment
      |                              
      no
      |
      v
ACTIVE stable deployment
      |
      v
Immutable model version
      |
      v
Runtime resolver
   /         \
  /           \
in-process   external
  |             |
artifact       HTTP runtime
verify/load     boundary
  \             /
   \           /
       prediction
```

The prediction response includes the deployment ID, immutable model-version ID,
framework, cache-hit information, traffic lane, and whether a canary fallback
occurred.

## Deployment invariants

ModelForge preserves several invariants:

- an environment has one authoritative stable deployment target;
- a deployment can only move through validated lifecycle transitions;
- a canary never replaces the stable target until promotion succeeds;
- aborting a canary removes it from traffic without changing stable;
- infrastructure failure while serving a canary can remove that canary and
  fall back to stable for the triggering request;
- promotion and rollback update deployment state and environment targets
  transactionally;
- registered artifacts are immutable identities, not mutable file pointers.

## Failure containment

External runtime calls are protected by:

- bounded retries;
- exponential backoff;
- per-runtime circuit breakers;
- health inspection;
- Prometheus metrics;
- deterministic failure/latency injection in the reference Go runtime.

These policies are implemented at the runtime boundary so future frameworks
inherit the same reliability behavior automatically.

## Tenant and authentication boundary

Hosted ModelForge resolves every customer-owned resource inside a workspace. Models, deployments, deployment targets, canaries, API keys, artifact namespaces, and prediction requests are scoped to that workspace.

Human browser authentication uses OIDC Authorization Code + PKCE. Login state and the PKCE verifier remain server-side, ID tokens are nonce-bound, and the browser receives an opaque HttpOnly session cookie rather than a provider token. Unsafe browser requests require double-submit CSRF proof whose server-side hash is bound to the session.

Automation uses high-entropy workspace API keys. Only a one-way hash and non-secret prefix are stored. Self-hosted installations can retain the default workspace by running with authentication disabled.

## Artifact persistence boundary

ModelForge's registry depends on an artifact-store contract rather than a filesystem path convention. The current implementations support local immutable storage and S3-compatible object storage.

Artifact identity remains SHA-256 verified regardless of backend. In-process runtimes materialize cloud artifacts into a verified local cache before loading them, while registry/deployment semantics remain backend-independent.

## Product surfaces

ModelForge exposes the same control plane through:

- the public product landing page at `/`;
- the multi-tenant SaaS console at `/dashboard`;
- the REST/OpenAPI API;
- the authenticated `modelforge` CLI.

The browser console and CLI are API clients. They do not bypass tenant boundaries, deployment lifecycle, artifact verification, or runtime resolution.

## Current scaling boundary

ModelForge currently uses process-local model caches and runtime client state.
That is intentional for the current project stage.

A distributed version would move coordination concerns such as cache
invalidation, asynchronous work, and runtime fleet membership behind explicit
shared-state interfaces rather than changing framework integrations.
