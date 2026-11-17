# Compose, browser and kind integration validation (2026-11-17)

## Repository facts discovered

The Windows host has no Docker CLI, kubectl, kubeconfig or NVIDIA GPU; it has an AMD Radeon 860M. The local Python API still cannot import LangGraph's `ormsgpack` because of Windows Application Control. Ubuntu GitHub Actions runners can run Docker Compose, Chromium and an ephemeral kind cluster. The existing API has no live Kubernetes write path.

## Implemented

- Added pinned `@playwright/test` and two Chromium interaction tests for a tenant's service creation → simulated execution → decision and research views, plus mobile navigation and overflow.
- Added a Compose smoke that waits for both real containers, exercises the Next proxy, FastAPI, SQLite, simulator and research endpoint, and checks the proxy allowlist.
- Added an ephemeral kind smoke that creates a CPU Deployment and narrow service-account RBAC, waits for Pod readiness, calls the real API server through the Phase 6 `dryRun=All` adapter, verifies replica count did not change, and confirms RBAC denial for an unprivileged account. It guards the exact kind context and deletes the cluster in CI.
- Fixed the root Docker build context to include the frozen split JSON required by the API Dockerfile. CI now has separate `compose_browser` and `kind_dryrun` jobs.

## How to run

The [GitHub Actions run](https://github.com/Dionisis09/sovereign-6g-jointsla/actions/runs/44059192658) executes all four jobs on commit `80bbec9`. For a local Docker-capable machine, set **demo-only** tenant tokens in the environment, then run:

```powershell
$env:SOVEREIGN_TENANT_TOKENS='{"ci":"ci-local-token"}'
$env:SOVEREIGN_DASHBOARD_TENANT_TOKEN='ci-local-token'
$env:SOVEREIGN_MODEL_DIR='/models/phase2-v1'
docker compose -f compose.maas.yaml up --build --wait --wait-timeout 180
python scripts/compose_smoke.py
cd apps/web
npm ci
npx playwright install chromium
npm run test:e2e
```

The kind smoke requires Docker, kind v0.33.0, kubectl and Python dependencies. It **only** accepts context `kind-sovereign-maas-ci`:

```bash
kind create cluster --name sovereign-maas-ci --wait 120s
python -m scripts.kind_dryrun_smoke
kind delete cluster --name sovereign-maas-ci
```

## Tests actually executed

| Check | Result |
| --- | --- |
| Ubuntu Python job | 417 passed; evidence hashes, Ruff, mypy and demos passed |
| Ubuntu web job | lint, TypeScript, build, frontend and production HTTP smoke passed |
| Compose browser job | Real API and web containers healthy; Compose smoke passed; **2 Playwright Chromium tests passed** |
| kind dry-run job | CPU Pod Ready; real Kubernetes API dry-run returned; replicas unchanged; denied service account rejected; cluster deleted |
| Windows local web checks | lint, TypeScript and production build passed |
| Windows local Docker/kubectl/GPU | Unavailable; not executed |

The first CI attempts found a script import-path error, a transient web-start connection reset and two overly strict Playwright locators. They were corrected. The four jobs passed on the final run linked above.

## Evidence and limitations

The browser tested the containerized Next/FastAPI/SQLite path using synthetic tenant data. The kind test reached an actual Kubernetes API server and a Ready CPU Pod, but the adapter issued **only `dryRun=All`** scale requests. The test proves admission behavior and unchanged replicas in that ephemeral cluster; it does not prove a live scaling rollout, rollback, service p95 or production authorization. The role has Kubernetes `update` permission because server dry-run requires it, although the adapter has no non-dry-run request path.

No NVIDIA GPU, HAMi device plugin, HAMi exporter or hardware workload was available. Resource-shape and metrics-reader behavior remain mock-tested. Do not interpret the CPU kind result as HAMi/GPU validation. There is no production cluster connection or deployment.

## Architecture decisions

Use CI-managed disposable containers and kind instead of altering the Windows host or an unknown external cluster. Keep browser and cluster tests separate from unit tests so their failures have clear causes. Pin the Playwright package and kind binary version. Keep all demo credentials scoped to the ephemeral CI job; the real API token is forwarded server-side by Next. The setup follows the official [Playwright CI](https://playwright.dev/docs/ci), [Docker Compose `up --wait`](https://docs.docker.com/reference/cli/docker/compose/up/), [kind quick start](https://kind.sigs.k8s.io/docs/user/quick-start/) and [Kubernetes dry-run](https://kubernetes.io/docs/reference/using-api/api-concepts/) contracts.

## What I should learn

1. Trace the browser click through the Next proxy, FastAPI intent endpoint, SQLite record and simulated decision.
2. Compare the adapter's `dryRun=All` receipt to the unchanged `Deployment.spec.replicas`, and explain why a Ready fixture Pod does not validate an actual scale action.
3. Inspect the two service accounts in the kind smoke and explain why an access review and API admission are both checked.

## Next phase

HAMi exporter scraping and GPU scheduling require an authorized NVIDIA GPU cluster with the plugin and metrics exporter installed. A live scale/rollback implementation would require a separate actuator, approvals, idempotency, readiness and SLO measurements. Neither is claimed by this validation.
