# Phase 5 dashboard and MLOps report (2026-11-17)

## Repository facts discovered

The repository has an existing Streamlit research view, a FastAPI simulator, tenant token authentication, separate workflow approver tokens, SQLite schema v2, and frozen Phase 2/4 results. There were no collection endpoints for services/runs/workflows and no local operations dashboard. Node 26 and npm 11 are installed; Docker CLI is absent. The historical `joint_sla_v2`, `prototype`, and frozen research sources/results were left unchanged.

## Implemented

- `apps/web`: Next.js 16 App Router, TypeScript, Tailwind 4, responsive operations dashboard. Sections: overview, service catalog and typed/plain intent forms, historical simulated p95 timeline, decision inspector, execution timeline, research evidence, workflow approval queue, model review. Loading, empty and error states are visible. p99, GPU utilization, throughput and energy are labeled unavailable.
- `apps/web/src/app/api/maas/[...path]/route.ts`: server-side allowlisted proxy, forwarding local tenant and optional separate approver credentials. The browser does not receive tokens. It is a single-tenant loopback demo, not a production authentication design.
- `sovereign_maas/store.py` and `api.py`: bounded, tenant-filtered list endpoints; local monitoring for recent simulation forecast coverage and SLO rate; read-only Phase 2/4 research summary; schema v3 model review table; separate-credential `promote-shadow` route. The latter only records approval metadata. The loaded predictor remains selected by `SOVEREIGN_MODEL_DIR`.
- `sovereign_maas/observability.py`: redacted JSON request logs with correlation ID, response correlation header and `/metrics` Prometheus text endpoint protected by a distinct token. Metric labels use method, route template and status only.
- Dockerfiles, Compose definition, web CI job, four Phase 5 API tests and a production Next → FastAPI → SQLite HTTP smoke script.

## How to run locally

From the repository root in PowerShell, after installing `requirements-maas.txt` and running `npm ci` in `apps/web`:

```powershell
$env:SOVEREIGN_TENANT_TOKENS='{"demo":"change-this-local-token"}'
$env:SOVEREIGN_APPROVER_TOKENS='{"demo":"different-local-approver-token"}'
$env:SOVEREIGN_MODEL_DIR='results/phase2-v1'
$env:SOVEREIGN_RESEARCH_DIR='results'
$env:SOVEREIGN_DB_PATH='sovereign_maas.sqlite3'
.\.venv\Scripts\python.exe -m uvicorn sovereign_maas.api:app --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal:

```powershell
cd apps/web
$env:SOVEREIGN_API_BASE_URL='http://127.0.0.1:8000'
$env:SOVEREIGN_DASHBOARD_TENANT_TOKEN='change-this-local-token'
$env:SOVEREIGN_DASHBOARD_APPROVER_TOKEN='different-local-approver-token'
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. The first run requires a service to be created before the execution and decision views contain data. The offline parser accepts all seven explicitly labeled fields; it is not an unrestricted natural-language interpreter. Without a configured model, the model registry is empty and the Phase 1 rule path remains available.

Docker Compose is defined but **not tested on this host**. With a local `.env` containing tenant token mapping and matching dashboard token, use `docker compose -f compose.maas.yaml up --build`. For the checked predictor, set `SOVEREIGN_MODEL_DIR=/models/phase2-v1`. Keep ports bound to loopback.

## Tests actually executed

| Check | Result |
| --- | --- |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q tests/test_sovereign_phase5.py` | 4 passed earlier in the session |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q` after the host policy change | Failed at collection (five modules); `ormsgpack` DLL blocked by Windows Application Control |
| `python scripts/phase5_http_smoke.py` | Failed before API ready; same native DLL block |
| `npm run build` | Passed; production routes compiled |
| `npm run lint` | Passed after React effect and PostCSS fixes |
| `npm run typecheck` | Passed |
| `python scripts/phase5_frontend_smoke.py` | Passed: production page, missing-config response, proxy allowlist |
| `python -m mypy sovereign_maas` | Passed, 19 source files |
| Ruff lint/format and Python compileall | Passed after fixes |
| `python -m pip check` and `git diff --check` | Passed |
| Compose and GitHub Actions YAML parse | Passed; neither runtime was executed |
| Docker Compose/browser E2E | Not executed; Docker CLI unavailable and API could not start for browser test |

The first focused run found two failing Phase 3 assertions because schema v3 replaces v2; those assertions were updated. Ruff initially found import ordering and formatting issues; they were corrected. The local full-suite gate remains blocked by Windows Application Control. Ubuntu CI later passed the full suite and the production HTTP smoke; see the verified follow-up below.

## Evidence and limitations

All operational snapshots, decisions, verifications and monitoring rates come from the simulator. The p95 bar chart is a historical snapshot view with a capped visual scale, not a live telemetry stream. Research panels read the existing Phase 2/4 metrics files, including their explicit simulation and fixture provenance. Phase 4 contains no measured live Jev accuracy. No hardware, GPU, Kubernetes, live traffic or energy measurements were available. Drift is `NOT_EVALUATED`; there is no live labeled baseline. No distributed trace exporter, browser automation pass, Docker run, or production auth has been validated. A local dashboard exposed beyond loopback would need human authentication and role enforcement first.

## Architecture decisions

The frontend uses server-side token forwarding to keep secrets out of browser bundles. API endpoints retain tenant filtering and bounded pages. The model review stage is persistent metadata for the already configured artifact; it cannot bypass the deterministic decision policy or activate a deployment. The metrics endpoint uses a distinct credential and bounded labels to avoid tenant or object identifiers in scrape output. See `ARCHITECTURE.md` and `DECISIONS.md`.

## What I should learn

1. Trace one service through `POST /v1/intents`, `POST /v1/simulations/run`, the SQLite row, and the decision inspector. Verify the `SIMULATED` fields remain visible.
2. Create two tenant tokens and prove each list endpoint returns only its tenant's rows. Then inspect why the server proxy must stay on loopback until user authentication exists.
3. Compare the Phase 2 model hash in `model_manifest.json` with the registry response. Approve shadow review, restart the API, and verify the stage persists while the runtime predictor remains configured by environment.

## Next phase

Run a browser interaction smoke and Docker Compose where those tools are available. Cluster-dependent validation remains separate from the simulator safety gate.

## Verified Ubuntu CI follow-up (2026-11-17)

[Run 44055591073](https://github.com/Dionisis09/sovereign-6g-jointsla/actions/runs/44055591073) on commit `42b9593` passed both jobs. The Python job passed **417 tests**, the frozen-evidence verifier, Ruff lint/format, mypy and all configured demos/research reproductions. The web job passed npm lint, TypeScript, production build, frontend smoke and the end-to-end production HTTP smoke (`Next → FastAPI → SQLite → simulator → research`), including the check that secrets were absent from HTML. These results verify the CI environment; they do not remove the Windows host's local `ormsgpack` block or validate Docker, browser interaction, Kubernetes or hardware.
