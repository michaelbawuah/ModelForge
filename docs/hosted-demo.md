# Hosted Demo Launch

This is the final ModelForge proof step. The repository already validates the
full platform locally and in CI; this run proves the same lifecycle against the
real public HTTPS deployment.

## What must exist first

Before running the hosted proof, the AWS reference stack must be provisioned and
activated:

- public HTTPS DNS name and ACM certificate;
- ECS/Fargate API and Go-runtime services with desired count greater than zero;
- RDS MySQL;
- S3 artifact bucket;
- populated runtime and metrics secrets;
- configured OIDC application/callback;
- successful database migration task;
- successful Release AWS workflow.

The AWS bootstrap and release sequence is documented in infra/aws/README.md.

## First browser login

Open the production URL in a browser and sign in through the configured OIDC
provider.

Create or select the workspace that will be used for recruiter proof. In that
workspace create a developer API key. The raw mf_live_ secret is shown only
once.

Use a dedicated demo workspace instead of a personal production workspace when
possible. The proof intentionally creates immutable model versions and
deployment records.

## GitHub production environment

Configure these non-secret variables:

~~~text
MODELFORGE_PUBLIC_URL=https://YOUR_PUBLIC_HOST
MODELFORGE_DEMO_WORKSPACE=YOUR_WORKSPACE_SLUG
~~~

Configure this environment secret:

~~~text
MODELFORGE_DEMO_API_KEY=mf_live_...
~~~

The same protected production environment may already contain the AWS release
variables used by release-aws.yml.

## Verify the hosted surface

You can run the verifier locally without changing data:

~~~bash
MODELFORGE_URL=https://YOUR_PUBLIC_HOST \
MODELFORGE_API_KEY=mf_live_... \
MODELFORGE_WORKSPACE=YOUR_WORKSPACE_SLUG \
python -m modelforge.hosted_verify
~~~

It checks HTTPS, health/readiness, OIDC mode, HSTS, strict CSP,
unauthenticated-request rejection, protected metrics, workspace API-key
identity, runtime inventory, and external-runtime health. The report never
includes the raw API key.

## Run the final hosted proof

In GitHub:

1. Open Actions.
2. Select Hosted Demo Proof.
3. Choose Run workflow from main.
4. Keep the default serving environment or choose another isolated name.
5. Run it.

The workflow first runs the packaged hosted verifier, then executes the same
full-lifecycle proof used by local CI:

~~~text
stable v1
  -> v2 weighted canary
  -> real traffic through both lanes
  -> promote v2
  -> rollback to v1
  -> v3 regression canary
  -> detect output drift
  -> abort v3 as FAILED
  -> verify v1 remains authoritative
~~~

A successful run uploads one GitHub Actions artifact containing:

~~~text
hosted-release-evidence.json
hosted-demo-proof/proof-summary.json
hosted-demo-proof/traffic-samples.jsonl
hosted-demo-proof/proof-report.md
hosted-demo-proof.log
~~~

That artifact is the evidence to cite when the README says the public hosted
demo passed.

## Portfolio capture

After the hosted proof is green, capture real screenshots of:

1. the public ModelForge landing page;
2. signed-in workspace overview;
3. model registry with the proof versions;
4. stable/canary deployment state;
5. runtime fleet showing the external Go runtime healthy;
6. the GitHub Hosted Demo Proof run and PASS artifact.

Do not fabricate or mock these screenshots. They should come from the real
hosted deployment and real proof run.

## Final claim boundary

Before the hosted workflow passes, describe ModelForge as having a validated AWS
deployment architecture and hosted-proof workflow.

After it passes, it is accurate to say the identical deployment lifecycle was
executed successfully against the public hosted ModelForge service.
