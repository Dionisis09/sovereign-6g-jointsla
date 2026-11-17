# Sovereign-MaaS repository audit (2026-11-16)

## Inventory and baseline

The source checkout is `Dionisis09/sovereign-6g-jointsla`, branch `codex/catalyst-phase0`, commit `e455be9`. The checkout was clean before this work. No `AGENTS.md` was found in the checkout or its workspace parents. The root `pyproject.toml` packages only `catalyst`; the repository also has separate `dynamic_placement`, `joint_routing`, `joint_sla_v2`, `prototype`, dashboard, research/evaluation, hardware-grounded, and test modules. `configs/`, `results/`, `JointSLA/`, and `docs/` hold configurations and frozen evidence. Do not edit historical results.

The existing runtime `prototype/controller.py::plan` calls the real `joint_sla_v2.policy.required_warm` rule; `prototype/controller.py::route` uses `joint_routing.router.choose`. The former provides a bounded replica recommendation, not a complete placement/migration candidate API. The `joint_sla_v2.policy.actions` function is coupled to the research simulator's snapshot/config types, so direct use with a new ServiceBundle would require an explicit translation and validation layer. The new Phase 1 adapter will reuse the warm-headroom recommendation and label its other candidates as heuristics. The prototype HTTP gateway and Kubernetes adapter are separate live-runtime components and will not be actuated by the local simulator API.

The existing `catalyst` experiment has a four-clause Pydantic intent and deterministic SimPy simulation. It is a separate Phase 0 research experiment, not a tenant-aware MaaS API. Its experiments, configs, output and results remain unchanged.

The checkout has one tracked config file under `configs/`, 24 test files after this addition, and 7,281 files under `results/` (including 200 CSV, 3,611 JSON and 60 compressed JSON files; no Parquet files). The result tree includes `phase0-v1`, `paper_30seeds`, `strong_baseline_30seeds`, `dynamic`, `joint_routing_30seeds`, `jointsla_v2_heldout` and hardware-grounded protocols/manifests. These are historical evidence, not Phase 1 training data. Existing infrastructure includes `prototype/compose.yaml` and Kubernetes YAML plus `deploy.ps1`; none was run or modified.

`SovereignArchitecture.pdf` was available in Downloads and read. It sketches Cloud/Edge/Far-Edge, an MDP placement agent, telemetry and an offline Eureka-style reward supervisor. These are conceptual in this repository. No claim of integration with the SOVEREIGN DSO follows from that diagram. The repo's `docs/paper_sov6g_integration.md` makes the same boundary explicit.

## Baseline test evidence

Bundled Python 3.12.14 initially had no `pytest`. A local ignored `.venv` was created. The first selected test collection failed because `prometheus_client` and `scipy` were absent. After installing pinned test dependencies, `python -m pytest -q tests/test_phase0.py tests/test_prototype.py tests/test_joint_sla_v2.py tests/test_joint_routing.py` passed: **78 passed in 3.60s**. This is a selected baseline, not the full repository suite. No research experiment was rerun.

After Phase 1 was added, the full suite was run. Initial full-suite collection required the repository's pinned Streamlit, Plotly and PyYAML packages. A subsequent run had 345 passes and six import failures because the pinned Kubernetes Python package was missing. After installing `kubernetes==36.0.2`, the final full suite passed **352 tests, one Starlette TestClient deprecation warning, in 30.83s**. These unit tests did not connect to a cluster. The seven new Phase 1 tests account for the difference from the historical suite; the historical 345-test claim was independently reproduced by this run, not assumed from the README.

## Gaps and no-go assumptions

- No existing tenant-authenticated FastAPI orchestration API, ServiceBundle store, run/decision audit API, or generic candidate contract.
- No calibrated TTV, action-conditioned TTR or PostSLA model in the MaaS sense. Phase 1 values must be named deterministic simulator rules.
- Existing `prototype` can patch a fixed Kubernetes deployment; it is not authorized for this task and is not wired into the new API.
- Residency, privacy, quota and model quality cannot be inferred from the existing JointSLA inputs. The first slice accepts explicit structured fields and rejects unsupported operations.
- SQLite persistence is a staged local adapter. PostgreSQL/Alembic are planned for Phase 2 after the transaction and tenancy contract is tested. SQLite behavior must not be claimed as production concurrency validation.
- The new FastAPI/TestClient combination emits a Starlette deprecation warning about `httpx`; it is not a test failure. Docker CLI was unavailable in this environment, so the Docker path has not been smoke-tested.

## Phase 4 dependency audit

No Jev/TypeSafe adapter, credential, cached Jev output or live Jev evaluation exists in this checkout. The Phase 2 synthetic replay and its held-out labels are available for matched offline comparisons, but they cannot measure Jev quality without actual Jev responses. The official TypeSafe System One API reference documents `POST /v1/systemone` with `model`, `state`, and named mixed questions, plus typed `answers` and usage. This is enough to implement an optional HTTPX adapter and mock its contract; it is not evidence of account access, live latency or calibration on network incidents.

## Phase 6 infrastructure audit (2026-11-17)

The machine has no `kubectl`, Helm or Docker CLI, cluster credentials, GPU or HAMi exporter. The historical prototype contains a Kubernetes adapter, but it is not tenant-bound to the new MaaS service/run audit and was not called. The new Phase 6 path is a separate dry-run-only adapter. The cluster-dependent validation checklist and precise local test results are in `PHASE6_REPORT.md`. The full repository Python suite remains blocked locally by Windows Application Control on LangGraph's native `ormsgpack` extension; standalone Phase 6 tests avoid importing LangGraph.

## Phase 7 replay audit (2026-11-17)

The frozen Phase 2 dataset has 500 initially healthy episodes and 1,500 complete synthetic action outcomes; it has no multi-step state transitions or real logged propensities. The original JointSLA warm-headroom adapter and deterministic gate are reusable as a valid-action mask under an explicitly fixed research profile. The available evidence supports a one-step contextual bandit comparison, not PPO/Dreamer or a hardware deployment claim. The new Phase 7 artifact is written only under `results/phase7-v1`; Phase 2/4 data, models and metrics remain unchanged.
