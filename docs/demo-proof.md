# Deployment Validation Scenario

This scenario is the shortest way to demonstrate ModelForge as a working ML
deployment platform rather than a collection of API endpoints.

It exercises the actual serving path:

~~~text
register model
  -> upload immutable v1/v2/v3 artifacts
  -> deploy v1 stable
  -> serve baseline inference
  -> start weighted v2 canary
  -> observe both traffic lanes
  -> promote v2
  -> roll back to v1
  -> start intentionally regressed v3 canary
  -> detect output drift
  -> abort v3 with a recorded failure reason
  -> verify v1 remains authoritative
~~~

## Local proof

Start ModelForge:

~~~bash
docker compose up --build --wait --detach
~~~

Run the proof:

~~~bash
python demo/proof_scenario.py --environment validation-demo --output-dir demo-proof-evidence
~~~

The command exits non-zero if any lifecycle assertion fails.

## Hosted proof

Create a workspace API key with at least the developer role, then run:

~~~bash
export MODELFORGE_URL="https://YOUR_MODELFORGE_HOST"
export MODELFORGE_API_KEY="mf_live_..."
export MODELFORGE_WORKSPACE="YOUR_WORKSPACE_SLUG"

python demo/proof_scenario.py --environment validation-demo --output-dir demo-proof-evidence
~~~

The raw API key is used only as an HTTP Authorization header. It is never
written to the evidence bundle.

## Evidence bundle

The output directory contains:

- proof-summary.json — compact machine-readable lifecycle evidence;
- traffic-samples.jsonl — request-level model-version and traffic-lane proof;
- proof-report.md — human-readable summary of the deployment lifecycle checks.

The proof deliberately includes both a successful and unsuccessful release:

1. v2 receives weighted canary traffic and is promoted;
2. v1 is restored through rollback;
3. v3 produces a large output regression;
4. the demo guardrail aborts v3 and ModelForge records the deployment as
   FAILED while v1 stays active.

This gives a reviewer concrete evidence for canary routing, promotion, rollback,
failure recording, and stable-target preservation in one reproducible run.


## Hosted GitHub proof

The repository also includes a manual `Hosted Demo Proof` workflow. It runs
the same proof against the public production service and uploads the evidence
bundle as a GitHub Actions artifact.

Configure these values on the protected GitHub `production` environment:

- variable `MODELFORGE_PUBLIC_URL` — the HTTPS ModelForge origin;
- variable `MODELFORGE_DEMO_WORKSPACE` — a workspace slug reserved for demo
  evidence;
- secret `MODELFORGE_DEMO_API_KEY` — a workspace API key with at least the
  `developer` role.

Then dispatch `Hosted Demo Proof` from the `main` branch.

The workflow validates HTTPS, checks `/health` and `/ready`, runs the full
promotion/rollback/regression-abort scenario, and retains the generated proof
bundle for 30 days. The API key is injected only as an environment secret and
is never written to the uploaded evidence.
