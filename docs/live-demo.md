# Hosted Demo Proof

This workflow is the final recruiter-facing proof for ModelForge. It is separate
from infrastructure provisioning and AWS release automation: first deploy
safely, then prove the hosted product through the same public API a customer
would use.

## What a successful proof demonstrates

A production proof validates all of the following against the public ModelForge
URL:

1. HTTPS is enabled.
2. /health reports healthy.
3. /ready reports ready.
4. hosted authentication is OIDC.
5. HSTS, CSP, anti-framing, MIME-sniffing, referrer, and request-ID headers are present.
6. a workspace API key can create model resources without exposing its secret.
7. immutable model artifacts can be uploaded to the hosted artifact backend.
8. version 1 becomes stable.
9. a deliberately different version 2 receives weighted canary traffic.
10. the version 2 semantic regression is observed and aborted without moving stable traffic.
11. a compatible version 3 is canaried and promoted.
12. the previous version 1 deployment is rolled back.
13. a compatible version 4 canary is left active so the dashboard visibly shows stable plus canary state.

The proof emits sanitized JSON, a Markdown lifecycle report, a public landing
page screenshot, and an authenticated SaaS-console screenshot.

## Production GitHub environment

Use the existing protected GitHub environment named production.

Add this secret:

    MODELFORGE_DEMO_API_KEY

Use a dedicated developer-role workspace API key. Do not reuse an administrator
key. The proof needs model, deployment, and inference permissions, but it does
not need API-key administration.

The workflow reuses this production environment variable:

    MODELFORGE_PUBLIC_URL

## Recommended workspace

Create a dedicated workspace named something like Recruiter Demo and generate
the developer API key there. Keeping demo resources isolated prevents
recruiter-facing evidence from mixing with unrelated production experiments.

## Run order

1. Run Release AWS from main and wait for it to finish green.
2. Confirm the hosted landing page and OIDC login manually.
3. Run Production Demo Proof from main.
4. Leave the default inputs unless you intentionally want another environment or traffic weight.
5. Download the modelforge-production-demo-<run id> artifact.

The artifact contains:

    public-verification.json
    hosted-demo.json
    hosted-demo.md
    landing-page.png
    saas-console.png
    screenshots.json

No API key, OIDC client secret, database password, runtime token, or metrics
token is written into those files.

## Local rehearsal

The same lifecycle is exercised in normal CI against the Docker Compose stack.
You can also run it manually:

    docker compose up --build --wait --detach

    python demo/verify_public.py       --base-url http://127.0.0.1:8000       --allow-http       --allow-auth-disabled       --output local-public-verification.json

    python demo/hosted_lifecycle.py       --base-url http://127.0.0.1:8000       --allow-self-hosted       --environment local-proof       --weight 25       --samples 40       --output local-hosted-demo.json       --markdown local-hosted-demo.md

## README promotion rule

Only after a real hosted proof passes:

- add the public URL;
- add the landing-page screenshot;
- add the SaaS-console screenshot;
- summarize the hosted proof artifact;
- update performance or release claims only with measurements captured from
  the hosted environment.

Do not describe the AWS deployment as live before both the real production
release workflow and hosted proof have passed.
