# Implementation plan and tracked tasks

Status values: `NOT_STARTED`, `STUB`, `SIMULATED`, `IMPLEMENTED`, `TESTED`, `VALIDATED_ON_HARDWARE`.

| Phase | Milestone | Status |
| --- | --- | --- |
| 0 | Audit existing JointSLA, preserve evidence, baseline tests, architecture and protocol | TESTED |
| 1 | Tenant-scoped typed intent -> seeded simulation -> JointSLA warm candidate -> deterministic decision -> simulated verification and API | TESTED |
| 2 | Replay dataset, frozen holdout, SLA/TTV/TTR/PostSLA baselines and conservative prediction adapter | TESTED |
| 3 | Optional structured LLM intent parser, tenant-filtered RAG, bounded checkpointed workflow | TESTED |
| 4 | Verified optional Jev adapter and OFF/ON comparative experiments | TESTED |
| 5 | Operations dashboard, observability and gated model registry | IMPLEMENTED; LOCAL VERIFICATION BLOCKED |
| 6 | Tenant-bound Kubernetes/HAMi dry-run adapter and simulated canary/rollback | TESTED OFFLINE; CLUSTER NOT VALIDATED |
| 7 | Masked one-step policy-gradient proposer and offline reward supervisor | TESTED OFFLINE; NO PROMOTION |

Phase 1 acceptance checklist:

- [x] Strict tenant-scoped structured intent and bundle persistence.
- [x] Seeded topology and telemetry with explicit `SIMULATED` provenance.
- [x] Three candidates including a real JointSLA warm-headroom recommendation, rejected alternatives, deterministic selection.
- [x] Simulation executor, post-action SLO verification and persisted audit/outcome.
- [x] Negative tests for auth, tenant isolation, capacity, stale telemetry, short recovery slack and idempotency.
- [x] One-command CPU demo, full baseline suite, format/lint/type checks, honest status update.

The checklist is updated only after verification. Historical datasets, experiment outputs and deployment manifests are out of scope for Phase 1.

Phase 2 acceptance checklist:

- [x] Freeze split groups and feature/metric choices before generation; preserve seed and scenario provenance.
- [x] Generate replayable Parquet episodes and action outcomes with first-breach and right-censor labels.
- [x] Fit/evaluate breach, discrete-time TTV, action-conditioned TTR and PostSLA baselines on a held-out test set.
- [x] Connect fresh valid predictions to the deterministic Decision Engine; test missing/stale/OOD fallback.
- [x] Produce hashed manifest, metrics, JSON model artifact and a one-command CPU reproduction.
- [x] Run the full suite, type/lint/format and demo checks; report exact results and limitations.

PostgreSQL/Alembic remains a later storage milestone because the Phase 1 SQLite adapter already satisfies the local persistence gate. It will not be mixed into the prediction experiment.

Phase 3 acceptance checklist (verify before marking complete):

- [x] Strict offline English/Greek intent parsing and optional Responses API structured output with mock tests; no guessed fields or network in tests.
- [x] Versioned lexical knowledge base with tenant/classification prefilter, citations and injection-resistant treatment as data.
- [x] Bounded LangGraph path with durable SQLite checkpoint, separate human approval, idempotent simulated effect and restart test.
- [x] Negative cases for malformed intents, cross-tenant access, injection, outage, duplicate approval and approval denial.
- [x] Full suite, lint, formatting, type check and local smoke run; truthful report and status update.

Phase 4 acceptance checklist (verify before marking complete):

- [x] Official TypeSafe request/response contract captured; `disabled`, `fixture`, optional `live` modes with typed validation and HTTP mocks.
- [x] Strict sanitized state, per-tenant external authorization, timeout/retry/rate/circuit limits, fail-closed advisory status.
- [x] Advisory visible in tenant-scoped API and checkpointed workflow without changing deterministic gates or approvals.
- [x] Predeclared matched-snapshot OFF/fixture ON/classic-ML comparisons, with all fixture evidence named as proxy rather than live Jev.
- [x] Negative tests for privacy, malformed responses, outage, stale/low-confidence judgments, and no policy bypass.
- [x] Full suite, lint, type check, demos and reproducible Phase 4 report; no historical result changes.

Phase 5 acceptance checklist:

- [x] Responsive Next.js/Tailwind local dashboard for services, typed/plain intent, simulated telemetry, decision inspection, workflows, research artifacts, approval and model review.
- [x] Tenant-filtered bounded list endpoints, monitoring coverage, request correlation logs, protected Prometheus text metrics and SQLite schema v3 migration.
- [x] Separate approver gate for workflow approval and shadow review; model promotion cannot switch the configured predictor.
- [x] Docker/CI definitions and a production Next → FastAPI → SQLite HTTP smoke script.
- [x] Next production build, ESLint, TypeScript, mypy and frontend-only production HTTP smoke in the local environment.
- [ ] Rerun full Python suite and HTTP smoke in an environment that can load the LangGraph `ormsgpack` native extension. Four focused Phase 5 tests passed before the local Windows Application Control block appeared; current collection fails before any test executes.
- [ ] Execute Docker Compose and browser interaction smoke. Docker CLI is unavailable on this Windows host, and no browser E2E run has been completed.

Phase 6 acceptance checklist:

- [x] Recheck tenant/service identity, selected deterministic scale action, snapshot freshness, allowed action, residency, simulated capacity and verification before any cluster preview.
- [x] CPU-only canary/target/rollback state machine with success and failure tests; explicit `SIMULATED` evidence.
- [x] Typed Kubernetes `Deployment`/`Scale` subset, namespace and owner labels, replica/resourceVersion preconditions, SelfSubjectAccessReview, strict server `dryRun=All` for canary and target only.
- [x] Validate explicit CPU/memory requests and limits plus HAMi NVIDIA GPU/memory/core resource shape; read configured HAMi host metrics with exact node allowlist and provenance.
- [x] MockTransport tests require no network or cluster; demo runs on CPU. No production writes or arbitrary kubectl path exists.
- [ ] Live Kubernetes dry-run and HAMi exporter scrape on a provisioned test cluster with appropriate RBAC/CA, GPU plugin, observability and approval; none is available here.
- [ ] Re-run the repository-wide Python suite when the Windows `ormsgpack` DLL block is removed or in CI. Phase 6 module tests run independently.

Phase 7 acceptance checklist:

- [x] Freeze seed groups, action mask, features, reward proposals, training seeds/hyperparameters, validation selection and paired test comparison in `PHASE7_PROTOCOL.json`.
- [x] Reuse checked Phase 2 counterfactuals, existing deterministic hard gate and real JointSLA warm-headroom adapter; keep migration masked without residency evidence.
- [x] Train a one-step masked policy-gradient contextual bandit across five RNG seeds; evaluate no-op, fixed SLA threshold, JointSLA-gated and learned policies on matched synthetic episodes.
- [x] Record proposal/validation reflection, per-family outcomes, paired seed bootstrap, model weights and immutable SHA-256 manifest.
- [x] Enforce no automatic runtime promotion; document human rejection of v1 because it exactly matches JointSLA with no incremental benefit.
- [x] Focused tests, lint, type-check and exact rerun of the frozen output.
- [x] Fresh seed-disjoint synthetic holdout for frozen v1 weights, with registered arrival-pressure sweep and manual rejection; this is not external validation.
- [ ] Multi-step RL environment, live LLM reward proposals and hardware transfer validation. None is claimed by v1 or the fresh-seed follow-up.
- [x] Read-only integrity gate for frozen Phase 2/4/7 and fresh Phase 7 output/source hashes; included in CI.
- [ ] Repository-wide Python suite once the host's `ormsgpack` Application Control block is resolved or CI runs.
