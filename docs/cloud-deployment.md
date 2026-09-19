# Public Cloud Deployment

ModelForge's hosted deployment boundary is intentionally provider-neutral:

```text
Internet
   |
TLS / load balancer
   |
ModelForge API containers
   |---- managed MySQL
   |---- S3-compatible artifact bucket
   |
private network / authenticated runtime contract
   |
external runtime containers
```

The control plane stays framework-neutral. PyTorch, ONNX, Go, Fluxion, or a future framework can run in-process or behind the external runtime contract without changing deployment, tenant, or artifact semantics.

## Production contract

Set `MODELFORGE_ENV=production` to enable fail-closed production validation. ModelForge will refuse to start unless the deployment has:

- a non-development `DATABASE_URL`;
- S3-compatible artifact storage and a bucket;
- OIDC browser authentication;
- an HTTPS public origin and HTTPS OIDC callback on that origin;
- secure browser-session cookies;
- explicit trusted hosts instead of `*`;
- a metrics bearer token;
- valid external-runtime secret references when `auth_token_env` is configured.

Run the same preflight manually before a release:

```bash
modelforge config-check
```

The command prints only sanitized configuration; it never prints database passwords, OIDC secrets, metrics tokens, or runtime tokens.

## Container contract

The API image accepts:

- `PORT` — provider-assigned HTTP port, default `8000`;
- `MODELFORGE_WORKERS` — Uvicorn worker count, default `1`;
- `MODELFORGE_FORWARDED_ALLOW_IPS` — trusted proxy IPs for forwarded headers;
- `MODELFORGE_RUN_MIGRATIONS=true` — optional single-instance/local convenience migration path.

The production recommendation is to run migrations as a separate release task:

```bash
alembic upgrade head
```

Then start one or more API replicas from the same immutable image. Do not run the migration flag on every replica in a horizontally scaled service.

## Managed MySQL

Create a MySQL database reachable only from the ModelForge service network. Put the complete SQLAlchemy URL in `DATABASE_URL` through the cloud secret manager.

ModelForge uses `pool_pre_ping` so stale pooled connections fail before they reach request handling. Schema changes remain Alembic-managed.

## Artifact bucket

Use `MODEL_ARTIFACT_BACKEND=s3` with `MODEL_ARTIFACT_S3_BUCKET`. AWS S3 works directly; S3-compatible providers can additionally set `MODEL_ARTIFACT_S3_ENDPOINT`.

Grant the API identity only the object permissions it needs for the configured bucket/prefix. Model artifacts remain immutable and SHA-256 verified. Tenant namespaces are part of the object key.

In-process runtimes materialize verified objects into `MODEL_ARTIFACT_CACHE_ROOT`. In ephemeral cloud containers, point that cache at writable ephemeral storage such as `/tmp`.

## Identity

Configure an OIDC application with the callback:

```text
https://YOUR_PUBLIC_HOST/auth/callback
```

Browser login uses Authorization Code + PKCE with nonce binding. Provider tokens are not persisted in browser storage; the browser receives an opaque HttpOnly ModelForge session cookie and a separate CSRF token.

## External runtimes

Prefer a private service network between the control plane and external runtimes. ModelForge also supports an optional bearer token per runtime. Put the secret in a dedicated environment variable and reference only its variable name from `MODELFORGE_EXTERNAL_RUNTIMES` using `auth_token_env`.

This keeps framework credentials out of runtime JSON configuration and gives future framework adapters the same transport boundary.

## Release sequence

1. Build immutable API and runtime images from the same commit.
2. Push images to your container registry.
3. Provision managed MySQL, the artifact bucket, TLS/load balancing, and secrets.
4. Run `modelforge config-check` using the production environment.
5. Run `alembic upgrade head` once as a release task.
6. Start the API and external runtime services.
7. Verify `/health` and `/ready`.
8. Verify OIDC login and workspace creation.
9. Create a workspace API key and exercise the CLI.
10. Register a model, create a canary, run inference, promote, and roll back.
11. Scrape `/metrics` with the configured bearer token.

## Scale boundary

API replicas are stateless with respect to durable customer data when using managed MySQL and S3-compatible artifacts. The current in-process model cache and circuit-breaker state are replica-local. That is acceptable for the present architecture and is documented rather than hidden.

A later distributed-control-plane milestone can move cache coordination and runtime fleet state behind shared services without changing the framework adapter contract.
