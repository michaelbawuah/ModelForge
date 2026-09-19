# External Runtime Contract

This document defines the current ModelForge external-runtime contract.

The contract is intentionally small. A new framework should be able to support
ModelForge by implementing an isolated service instead of changing the
control-plane inference code.

## Required endpoints

### `GET /health`

A healthy runtime returns HTTP 200 with a JSON object containing:

```json
{
  "status": "healthy",
  "service": "example-runtime"
}
```

ModelForge treats non-200 responses, transport failures, malformed JSON, and a
status other than `healthy` as unhealthy.

### `POST /predict`

Request:

```json
{
  "model": {
    "model_version_id": 42,
    "version": "2.1.0",
    "framework": "future-framework",
    "artifact_uri": "scheme://location/model",
    "checksum": "registered-checksum"
  },
  "inputs": {
    "features": [1, 2, 3]
  }
}
```

Successful response:

```json
{
  "prediction": {
    "class": "example"
  }
}
```

The `prediction` value may be any JSON-compatible value.

## Error semantics

A runtime should use:

- **2xx** for successful execution;
- **4xx** when the request or model is not valid for that runtime;
- **5xx** when execution failed because of a runtime/server condition.

ModelForge can retry transport failures and 5xx responses according to the
configured resilience policy. Repeated failures can open that runtime's
circuit breaker.

## Framework identifier

The model version's `framework` string is the routing key.

A framework integration registers that identifier with ModelForge configuration
and points it at the external runtime service:

```json
{
  "future-framework": {
    "name": "future-runtime",
    "base_url": "http://future-runtime:9000",
    "timeout_seconds": 5.0,
    "max_retries": 2,
    "retry_backoff_seconds": 0.05,
    "circuit_failure_threshold": 3,
    "circuit_reset_seconds": 30.0
  }
}
```

No framework-specific conditional is required in the control plane.

## Artifact responsibility

The external runtime receives the registered artifact URI and checksum.

How it retrieves and loads that artifact is runtime-specific. A runtime may use
a local volume, object storage, a framework-native registry, or another
artifact transport.

ModelForge's control plane still owns the immutable model-version metadata.

## Adding a framework that does not exist today

A future framework integration should:

1. implement `GET /health`;
2. implement `POST /predict` using the request/response shape above;
3. choose a stable framework identifier;
4. package the framework and its dependencies in its runtime environment;
5. register its base URL in `MODELFORGE_EXTERNAL_RUNTIMES`;
6. add contract and integration tests.

The Python control plane does not need to import the framework package.

## Compatibility

The current wire contract is the first public external-runtime contract for
ModelForge.

Explicit protocol-version negotiation is intentionally not required yet. Any
future incompatible protocol revision should introduce version negotiation or a
new endpoint namespace while preserving this contract for existing runtimes.

The reference Go runtime and Python external-runtime tests act as executable
examples of the current contract.
