# Architecture decisions

## ADR 001: Preserve research implementations

Use `prototype.controller.plan` for its real JointSLA-v2 warm-headroom rule. Label the Phase 1 migration and no-op alternatives as heuristics. Do not rewrite `joint_sla_v2.policy.actions`, research configs or results. Reason: the full action function expects simulator-specific structures and cannot safely consume a new bundle without a tested adapter.

## ADR 002: Local SQLite staging

Use a small SQLite repository with explicit schema version and tenant-scoped queries for the first offline vertical slice. This avoids requiring Docker/PostgreSQL on a CPU-only developer machine. Add PostgreSQL and Alembic when the storage contract and concurrency tests are mature. SQLite is not evidence of production transaction behavior.

## ADR 003: Deny by default

The API starts with no tenant credentials unless configured. Every service/run read and mutation is scoped to the authenticated tenant. The demo creates an ephemeral local token. Simulation endpoints cannot call the Kubernetes adapter.

## ADR 004: Rule forecasts

Expose deterministic TTV/TTR/PostSLA proxies with `SIMULATED_RULE` provenance, validity horizon and reasons. Do not call them calibrated probabilities. Missing/stale data causes no-op/escalation; no action bypasses capacity, residency or operation gates.

## ADR 005: Type-check scope

Mypy checks `sovereign_maas` and skips following imports into the historical JointSLA modules. A first transitive check found two unrelated existing `dynamic_placement/policies.py` type errors. This keeps the new slice's type gate useful without rewriting historical research code during Phase 1.

## ADR 006: Phase 2 grouped holdout and local models

Freeze split seeds and features before generating labels. Use one initial snapshot per seed/scenario, separate seed groups across train/validation/test, and calibrate on validation only. Discrete-time hazard models retain censored risk sets. This is a simulation-only baseline with a local trusted model artifact. PostgreSQL migration is deferred; it does not change prediction validity and the Phase 1 repository is persistent for local use.

## ADR 007: NumPy estimator fallback

Windows Application Control blocked the scikit-learn 1.9.1 `_cython_blas` DLL before training. Use NumPy-only logistic and linear quantile estimators with explicit coefficients and validation-only probability scaling. Keep the predeclared data, split and evaluation design. JSON model artifacts avoid pickle loading and keep local inference auditable. This is an implementation change, not evidence that NumPy models outperform scikit-learn.

## ADR 008: Bounded Phase 3 LLM and knowledge

Keep exact labeled-field parsing as the offline default. The optional OpenAI Responses adapter has an explicit model/key/tenant allowlist, strict JSON schema, ten-second HTTP timeout, one retry only for invalid parse and source-grounded Pydantic validation. No service, SLO or tenant value is inferred. A packaged local knowledge file uses tenant/classification filtering before lexical scoring, with source IDs and versions. The retrieved text is evidence, never an executable instruction or policy override.

## ADR 009: Durable local approval

Use LangGraph's SQLite checkpointer for a bounded parse → plan → approval interrupt → execute path. The main SQLite store owns tenant identity, idempotency and an auditable workflow record. A separate approver credential is required for non-no-op actions. On resume, re-evaluate the hard policy and snapshot age; an expired proposal is rejected. Simulator writes use a stable workflow ID so a repeated graph execution cannot create a second run. This does not provide distributed transaction guarantees or live actuation.

## ADR 010: Windows test plugin isolation

LangGraph depends on LangSmith, whose auto-loaded pytest plugin imports a native `uuid_utils` DLL blocked by this host's Windows Application Control. LangGraph itself imports and runs. Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for the project test command and CI, keeping tests local with no accidental plugin network behavior. This does not change application dependencies or skip project tests.

## ADR 011: Jev remains an advisory, not a predictor substitute

The official System One schema supports one bounded request with mixed Choice, Score and Noul questions; it does not return calibrated TTV/TTR seconds. Use a strict HTTPX adapter with a tenant egress allowlist, sanitized numeric state, checked answer distributions, bounded retries and a circuit breaker. The fixture answers are local rule proxies. Neither live nor fixture judgments bypass deterministic policy, role approval or model freshness. This phase compares advisory integration OFF/ON on matched synthetic episodes; genuine Jev-only predictive and hybrid efficacy awaits actual Jev measurements and separate validation.

## ADR 012: Local server-side dashboard capability

Keep the dashboard bound to loopback and forward a single configured tenant token from Next.js server routes through a small path allowlist. This avoids placing credentials in browser JavaScript, but it grants dashboard visitors the local configured tenant's capability. Do not expose it publicly until human authentication, session protection, CSRF defense and role separation are implemented. A separate configured approver token is required for approval routes; it is not sent to the browser.

## ADR 013: Honest observability and model review

Use low-cardinality route templates in protected Prometheus text metrics and redacted JSON request logs. A correlation header aids local debugging, but there is no distributed tracing backend. Report drift as `NOT_EVALUATED` without a live labeled baseline; show simulation-only forecast coverage and SLO rate separately. The model registry records approval for shadow review of the already loaded, hash-checked artifact. It never switches the runtime predictor or claims a canary deployment.

## ADR 014: Native dependency block after initial Phase 5 pass

On 2026-11-17 Windows Application Control began blocking the unsigned `ormsgpack.cp312-win_amd64.pyd` imported by LangGraph. Four focused Phase 5 tests had passed earlier in the session, but a subsequent full-suite run failed during collection and the HTTP smoke could not start FastAPI. The earlier pytest-plugin isolation does not address this new block. Preserve the failed result and rerun in a permitted Python environment or CI; do not alter LangGraph serialization to mask the failure.

## ADR 015: No cluster mutation in Phase 6 local slice

Keep local canary/rollback as a simulation and the Kubernetes integration strictly server-side dry-run. The adapter accepts a trusted tenant deployment binding, not arbitrary namespace or resource names from an intent, LLM or HTTP request. Use SelfSubjectAccessReview plus the API server's own RBAC/admission checks, resourceVersion preconditions and explicit HAMi resource limits. A dry-run response proves only admission of that request at that moment; it does not prove scheduling capacity, workload readiness, SLO compliance or rollback success. No hardware/cluster claim is made from mocks.

## ADR 016: One-step masked policy gradient, not PPO

The frozen Phase 2 replay has one initial state and three full synthetic counterfactual action outcomes per episode, not trajectories or logged propensities. Train a small masked one-step REINFORCE contextual bandit rather than claim PPO or Dreamer. Use the existing deterministic policy as the action mask; never use future outcomes to decide validity. Keep migration masked without residency evidence. Compare matched no-op, fixed SLA threshold, JointSLA gate and learned policy on the same seed groups. This experiment tests a narrow offline choice mechanism, not autonomous cluster control.

## ADR 017: Reward proposals and promotion remain offline

Freeze three bounded reward proposals before inspecting reused test outcomes. The supervisor is an `OFFLINE_FIXTURE`, not a live LLM; reflection history records validation results without granting mutation authority. Select by validation SLO then action rate. The preregistered test gate permits only offline review and never changes runtime configuration. Manual review rejects Phase 7 v1 promotion because it exactly matches the JointSLA gate and the test set is reused synthetic evidence.

## ADR 018: Prospective frozen-weight follow-up

Lock the saved Phase 7 v1 model and its manifest by SHA-256 before evaluating untouched seeds 100–119. Recompute outcomes with the frozen Phase 2 simulator under registered arrival factors, while preserving the existing current-state action gate. Do not retrain, tune thresholds or select a model using the fresh cases. Require a strictly positive paired seed-bootstrap lower bound at every factor and no greater action rate for even an offline review candidate. The equal decisions observed across all factors fail this gate. Elevated pressure also makes scale invalid under the fixed profile; this is a simulator/decision-envelope finding, not proof of resilience. Keep the runtime policy disabled.

## ADR 019: Read-only frozen evidence gate

CI checks all recorded Phase 2/4/7 and fresh-follow-up file and source SHA-256 values before running tests. It reports tampering or source drift and never regenerates or overwrites research evidence. This checks repository integrity and lineage, not statistical validity or transfer to hardware. The Windows `ormsgpack` block does not affect the pure-standard-library verifier.
