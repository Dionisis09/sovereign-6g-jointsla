# JointSLA — project entry point

## Sovereign-MaaS local Phase 1 slice

The new `sovereign_maas` package is a **simulation-only**, tenant-scoped FastAPI
vertical slice. It uses the existing JointSLA-v2 warm-headroom recommendation
from `prototype.controller.plan`, compares it with clearly labeled heuristic
and no-op alternatives, applies deterministic policy gates, and persists the
simulated decision and verification in SQLite. It does not invoke the existing
Kubernetes adapter or change frozen research results. See
`docs/REPO_AUDIT.md`, `docs/ARCHITECTURE.md`, and `docs/STATUS.md`.

From the repository root on Windows with Python 3.12+:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[maas,test,quality]"
& .\.venv\Scripts\python.exe -m sovereign_maas.demo
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_maas.py
```

The demo creates an ephemeral tenant token and temporary SQLite database. To
serve the API locally, set a private token mapping before starting Uvicorn:

```powershell
$env:SOVEREIGN_TENANT_TOKENS = '{"demo-tenant":"replace-with-a-random-token"}'
& .\.venv\Scripts\python.exe -m uvicorn sovereign_maas.api:app --host 127.0.0.1 --port 8000
```

Use `X-Tenant-Token` on the API calls and `Idempotency-Key` on
`POST /v1/simulations/run`. OpenAPI is at `/docs`. Docker users can set the same
environment variable and run `docker compose -f compose.maas.yaml up --build`.
The Docker path has no GPU, paid key or Kubernetes dependency.

### Phase 2 replay and trained forecasts

The CPU-only Phase 2 pipeline uses frozen seed groups and synthetic Parquet replay:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-maas.txt
& .\.venv\Scripts\python.exe -m sovereign_maas.research_runner --output results/phase2-v1
```

The command verifies existing hashes rather than overwriting prior evidence.
Review `docs/PHASE2_REPORT.md` and `results/phase2-v1/metrics.json` before using
the models. To enable trained forecasts for local API requests, set
`SOVEREIGN_MODEL_DIR` to the absolute `results/phase2-v1` path before starting
Uvicorn. `POST /v1/predictions/evaluate` then exposes model outputs. Invalid,
expired, missing or out-of-distribution forecasts select no-op in the simulator.
For Docker Compose, set `SOVEREIGN_MODEL_DIR=/models` after generating the files;
the Compose configuration mounts that result directory read-only. All forecasts
and outcomes remain **SIMULATION_ONLY**. The tested policy did not improve the
held-out simulated SLO rate over no-op.

### Phase 3 offline intent, knowledge and approval workflow

Install `requirements-maas.txt` and run the CPU-only demo:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-maas.txt
& .\.venv\Scripts\python.exe -m sovereign_maas.phase3_demo
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_phase3.py
```

`POST /v1/intents/parse` accepts English or Greek labeled intent text with all
seven required fields. `GET /v1/knowledge/search?q=...` returns versioned,
tenant-filtered local citations. `POST /v1/workflows` accepts `{"text": "...",
"seed": 7}` with `X-Tenant-Token` and `Idempotency-Key`. A proposed scale or
migration pauses with `NEEDS_APPROVAL`; `POST /v1/workflows/{id}/approve` accepts
`{"approved": true}` only with an additional `X-Approver-Token` for that tenant.
The workflow resumes from a SQLite LangGraph checkpoint, rechecks policy and
telemetry freshness, then writes one idempotent **simulated** run. A no-op needs
no approval. Check `GET /v1/workflows/{id}` and `GET /v1/simulations/{run_id}`.

The default parser is offline and makes no network request. To opt into the
OpenAI Responses parser, set `SOVEREIGN_LLM_MODE=openai`, `OPENAI_API_KEY`,
`SOVEREIGN_LLM_MODEL`, and `SOVEREIGN_LLM_ALLOWED_TENANTS` explicitly. An
unlisted tenant is denied before any external request. Missing key or model
uses the offline parser, identified in the response. Live OpenAI calls were
tested only with an HTTP mock; they require an account and compatible model.
Never send tenant-sensitive text to an external provider without authorization.
See `docs/PHASE3_REPORT.md` for exact tests and limits.

### Phase 4 TypeSafe/Jev advisory and matched synthetic comparison

The API now accepts a `JudgmentProvider` with `disabled` (default), `fixture`
or opt-in `live` mode. `POST /v1/judgments/evaluate` returns a typed advisory
record for a tenant-owned service and seeded simulator snapshot. Simulation
runs and checkpointed workflows retain that record. The deterministic action
policy and separate approval requirement do not use it as authorization.

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.phase4_demo
& .\.venv\Scripts\python.exe -m sovereign_maas.research_phase4 --models results/phase2-v1 --output results/phase4-v1
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_phase4.py
```

The `fixture` is deterministic code, **not a Jev measurement**. To enable live
TypeSafe calls, set `SOVEREIGN_JEV_MODE=live`, `TYPESAFE_API_KEY`, a model name
from your TypeSafe account in `SOVEREIGN_JEV_MODEL`, and
`SOVEREIGN_JEV_ALLOWED_TENANTS`. The adapter sends only allowlisted numeric
simulator features to the documented `/v1/systemone` endpoint, validates every
typed answer, and returns `UNAVAILABLE` on denial, stale data or failure. No
live Jev call was made in this phase; tests use HTTP mocks. See
`docs/PHASE4_REPORT.md` for the comparison and its limits.


Start with the [organized JointSLA folder](JointSLA/README.md): mathematical scaler/router Word, full 107-slide presentation, final technical report, conference paper, figures, tables and links to all implementation modules.

For a fresh GitHub clone, installation and what is included/excluded, use the [repository guide](REPOSITORY_GUIDE.md). Install `requirements-research.txt` to run the dashboard and tests from the clone.

Open the [research dashboard](http://127.0.0.1:8501/?view=kubernetes-v2) or the [real inference / MaaS demo](http://127.0.0.1:8501/?view=maas). See [dashboard/README.md](dashboard/README.md) and [Kubernetes setup](prototype/kubernetes/README.md) for local runtime prerequisites. Frozen research remains under its original paths in `results/` and `docs/jointsla_kubernetes_v2_final/`.

The existing research history and run instructions follow below; dated test counts are historical records.

## CATALYST: runtime cross-layer contracts, Phase 0

The separate [real-inference infrastructure prototype](prototype/README.md)
adds Docker, real PyTorch serving, Prometheus/Grafana and a scoped Kubernetes
adapter. Frozen simulator/paper results remain unchanged.

Final local prototype deliverables: [unified JointSLA report](JOINTSLA_FINAL_REPORT.md)
and [live infrastructure dashboard](http://127.0.0.1:3001/d/jointsla-runtime).
The dated audit verified 306 tests / 1,420 outcomes; the dashboard extension
passes 310 tests. The report keeps the 38.83% and 47.27% burst runs separate.

The statistical paper evaluation is documented in
[paper_evaluation/README.md](paper_evaluation/README.md). Run
`python run_paper_experiments.py --seeds 1:30 --reuse-results` to reproduce the
analysis of the saved 120 policy runs. Results, 95% confidence intervals,
paired tests, figures and generated report are in `results/paper_30seeds`.

The dynamic extension is documented in [dynamic_placement/README.md](dynamic_placement/README.md).
Run `python -m dynamic_placement.runner` for 30 paired seeds, 100 slots,
explicit queues, scaling and migrations. Outputs are in `results/dynamic`.

Run `python -m dynamic_placement.scenarios` for the follow-up predictive,
extra-capacity and admission-control comparisons; see
[SCENARIOS.md](dynamic_placement/SCENARIOS.md).

The newer five-node service-placement experiment is documented in
[placement_experiment/README.md](placement_experiment/README.md). Run it with
`python -m placement_experiment.runner`; its outputs are separate in `results/placement`.

The Phase 0 study uses one configurable synthetic service
engine, B0 PLAIN_LOCAL, B1 STRONG_LOCAL_SAFE, CATALYST RUNTIME_CONTRACT, and only
the two requested ablations. See [the protocol](docs/protocol.md) and
[the code reuse audit](docs/reuse-audit.md).

Generic helpers from the earlier AIMCO/VISTA projects are included with
[exact provenance](docs/reuse-provenance.json). Their controllers, claims and tuned
parameters are not imported. The provenance record preserves historical source
locations and hashes; these external originals are not included in a fresh clone.

## Run

Create a local environment with Python >=3.12 and install the pinned project
dependencies (`.venv` is not included in the repository):

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[test]"
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage all --output results/reproduction
```

To follow the prescribed sequence separately:

```powershell
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage negative
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage stress
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage ablations
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage analyze
```

Final artifacts: [report](results/phase0-v1/report.md),
[interpreted findings](docs/phase0-findings.md),
[decision and paired intervals](results/phase0-v1/analysis.json),
[seed-level metrics](results/phase0-v1/runs.csv),
[secondary metrics](results/phase0-v1/summary.csv), and
[plot](results/phase0-v1/breach_seconds.png).

Independent metric reconstruction: `python -m tools.verify_results`.

The initial failed S0 at 40 rps is preserved in `results/phase0`; the corrected
10-rps S0 with an overly strict draft B0 equality check is in `results/phase0-final`.
These are validation pilots, not extra stress experiments. The protocol and report
disclose both corrections. No S1–S3 parameters or hypothesis thresholds were tuned.

## Inspect and replay

Each case retains a frozen workload tape and compressed policy evidence, including
all request outcomes, public snapshots, clause predictions, lifecycle actions,
breach samples and bounded counterfactual false-block audits. Seeds are the units
of statistical replication. Source/config/protocol hashes are frozen before the
first stage. Changed files require a fresh output directory; old runs are not mixed.

For a single run:

```python
from catalyst.scenario import load_config, matrix, workload
from catalyst.engine import Engine
c = load_config()
s = next(s for s in matrix(c) if s.family == "S3" and s.level == 2)
tape = workload(c, s, seed=0)
run = Engine(c, s, tape, "CATALYST").run()
print(run.summary())
```

No request rejection, autonomous agents, deployment infrastructure, RL, digital
twin, extra baselines, or broad policy language is implemented. Quality scores
and service profiles are stipulated. This experiment can reject the mechanism's
Phase 0 hypothesis; it cannot establish real-world performance or novelty.


## Real Kubernetes comparative validation

The unchanged JointSLA runtime is being evaluated against static, CPU-reactive
and native HPA policies plus two registered scaling/routing controls. The isolated
lab preserves historical experiments and the primary dashboard. See the
[benchmark instructions](prototype/benchmark/README.md),
[frozen evaluation protocol](prototype/kubernetes/RESEARCH_EVALUATION_PROTOCOL.md),
and [contribution scope](prototype/kubernetes/COMPARATIVE_NOVELTY_SCOPE.md).
The main experiment has 30 paired seeds, 180 trials and 230,400 offered requests.
Progress is recorded in `prototype/.cache/kubernetes_comparison_v2/progress.json`;
only completion plus independently reconstructed analysis supports final findings.

## Sovereign-MaaS local operations slice

The separate `sovereign_maas` package adds a tenant-scoped **simulator** API and an
`apps/web` Next.js operations dashboard. It does not actuate Kubernetes or
measure live 6G/GPU hardware. Start with [the architecture](docs/ARCHITECTURE.md),
[Phase 5 report](docs/PHASE5_REPORT.md) and [status](docs/STATUS.md). Phase 2/4
research evidence is in `results/phase2-v1` and `results/phase4-v1`.

Install backend extras with `python -m pip install -r requirements-maas.txt`.
Set `SOVEREIGN_TENANT_TOKENS` to a JSON object, then run
`python -m uvicorn sovereign_maas.api:app --host 127.0.0.1 --port 8000`.
For the local UI, run `npm ci` and `npm run dev` in `apps/web`, with
`SOVEREIGN_API_BASE_URL=http://127.0.0.1:8000` and a matching
`SOVEREIGN_DASHBOARD_TENANT_TOKEN`. See `apps/web/.env.example` for variables.
The dashboard is a single-tenant loopback demo; do not expose it to a shared
network without adding human authentication. Set `SOVEREIGN_MODEL_DIR` to
`results/phase2-v1` to enable the checked local predictor. Docker Compose is
defined in `compose.maas.yaml` but has not been run on this host.

Phase 6 has a CPU-only, no-cluster safe rollout demo:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.phase6_demo
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_phase6.py
```

It produces a tenant-bound simulated scale plan and success/rollback traces.
The optional Kubernetes adapter performs only API-server `dryRun=All` requests;
it has not been validated against a cluster. See
[the Phase 6 report](docs/PHASE6_REPORT.md) for the API contract and limits.

Phase 7 has a separate offline research command:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.research_phase7 --dataset results/phase2-v1 --output results/phase7-v1
```

It trains a masked one-step contextual bandit on frozen synthetic action
outcomes, compares matched baselines and records immutable evidence. The learned
policy showed no improvement over the JointSLA gate and was **not promoted**.
See [the Phase 7 report](docs/PHASE7_REPORT.md) and
[promotion review](docs/PHASE7_PROMOTION_REVIEW.md).

A preregistered follow-up evaluates the frozen weights on new synthetic seeds
100–119 and three arrival pressure factors:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.research_phase7_fresh
```

It found no improvement over JointSLA; at higher pressure the hard gate allowed
no scaling and both arms missed every simulated SLO. The policy remains disabled.
See [the fresh holdout report](docs/PHASE7_FRESH_REPORT.md).

Verify the checked Phase 2/4/7 evidence and source lineage without rewriting it:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.evidence
```
