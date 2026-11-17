# Phase 7 masked policy and offline reward supervisor (2026-11-17)

## Repository facts discovered

The frozen Phase 2 replay has 500 initially healthy simulated episodes and 1,500 full synthetic counterfactual action outcomes (scale, migrate, no-op), with seed-disjoint train 0–59, validation 60–79 and test 80–99 across five families. It contains one initial decision state per episode, not a multi-step trajectory or real logged-action propensity. The deterministic `decide()` gate already enforces allowed actions, residency, capacity and recovery conditions. Under a fixed Gold/eu-gr/max-two-replicas research profile it allows scale on 125/300 train, 46/100 validation and 32/100 test episodes. The Phase 2/4 files and historical JointSLA source were not modified.

## Implemented

- `docs/PHASE7_PROTOCOL.json` freezes inputs, seed groups, features, five policy training RNG seeds, one-step masked REINFORCE hyperparameters, three bounded fixture reward proposals, baseline choices, paired bootstrap and offline review gate before the test run.
- `sovereign_maas/research_phase7.py` verifies the Phase 2 dataset hashes, constructs current-only features, calls the existing deterministic policy for an action mask, trains a two-action one-step policy gradient, evaluates predeclared no-op/SLA-threshold/JointSLA baselines, selects the reward proposal on validation only, and evaluates the chosen proposal on the reused test split. Migration stays masked because the fixed profile lacks residency authorization. Future post-action outcomes enter reward training and evaluation, never features or mask construction.
- `results/phase7-v1` has metrics, five trained weight matrices, bounded reflection history and SHA-256 manifest. Re-running the same command verifies exact bytes and refuses an existing changed output. The artifact is offline only and is never imported into the runtime decision path.
- `docs/PHASE7_PROMOTION_REVIEW.md` records the human review decision **DO NOT PROMOTE**. The preregistered mechanical gate only creates an `OFFLINE_REVIEW_CANDIDATE`; it cannot activate a policy.

This is a one-step contextual bandit inspired by [REINFORCE](https://doi.org/10.1007/BF00992696) and valid-action [policy-gradient masking](https://arxiv.org/abs/2006.14171). It is not PPO, Dreamer or a multi-step RL result. The offline fixture reward loop borrows the proposal/evaluate/reflect framing of [Eureka](https://arxiv.org/abs/2310.12931), but no LLM generated reward code or proposal in this run.

## How to run

From the repository root in PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.research_phase7 --dataset results/phase2-v1 --output results/phase7-v1
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_phase7.py
```

The first command verifies the existing artifact rather than overwriting it. Use a new output directory for any new protocol or source version. There is no Phase 7 Docker service, cluster command or runtime promotion command; the existing Docker Compose remains untested on this host.

## Tests actually executed

| Check | Outcome |
| --- | --- |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q tests/test_sovereign_phase7.py` | 5 passed |
| Phase 7 experiment command, then exact rerun to the same directory | Passed; identical output verified |
| Ruff lint/format and mypy | Passed; mypy checked 22 package files, after one unused-import fix in tests |
| `python -m pip check`, CI YAML parse, output/source hashes and `git diff --check` | Passed |
| Repository-wide pytest | Failed at collection in five modules: Windows Application Control blocked LangGraph `ormsgpack` |
| Live LLM reward supervisor, GPU, Kubernetes or hardware experiment | Not executed |

The focused tests check split sizes and mask counts, invalid-action rejection, seeded training repeatability, train-only input, dataset hash tampering, immutable output refusal, reflection provenance and runtime-disabled model artifact.

## Matched synthetic comparison

All rates below are **simulated post-action SLO outcomes** on the same 100 reused Phase 2 test episodes (five families × seeds 80–99). They are not live SLA rates or a fresh independent holdout.

| Policy | Simulated SLO rate | Scale action rate |
| --- | ---: | ---: |
| No-op | 0.16 | 0.00 |
| Fixed SLA threshold, 70 ms | 0.22 | 0.14 |
| JointSLA with hard gate | 0.32 | 0.32 |
| Chosen masked policy, mean of five training seeds | 0.32 | 0.32 |

All five trained policy seeds yielded the same aggregate test rates. The paired episode-seed bootstrap 95% interval for learned-minus-JointSLA simulated SLO rate is **[0, 0]**. Per-family SLO rates for both policies are burst 0.30, capacity 0.25, network 0.45, ramp 0.35 and steady 0.25. The result shows **no incremental benefit over the JointSLA gate**. These numbers are not directly comparable to Phase 2's trained-forecast decision replay, which used a different prediction gate and reported 0.16 selected/no-op SLO rates.

## Evidence and limitations

The synthetic generator supplies every action's counterfactual outcome, so the comparison has exact toy outcomes but does not solve real offline policy evaluation with missing counterfactuals or logged propensities. The fixed research profile is not a tenant deployment configuration. Masking prevents structurally unsupported actions in this experiment; the runtime decision gate remains authoritative. Test seeds 80–99 were previously used in Phase 2/4, so results are a transparent follow-up rather than an untouched holdout. No live LLM supervisor, GPU scheduling, cold-start, cluster admission, Pod readiness or hardware latency was measured. Transfer to hardware remains unknown.

The mechanical review gate accepts equality as noninferiority and records `OFFLINE_REVIEW_CANDIDATE`, but human review rejects promotion because the learned policy reproduces the JointSLA gate without benefit. No shadow/canary/runtime state changed.

## Architecture decisions

Use a small transparent policy-gradient bandit matched to the available one-step data. Reward proposals are typed, bounded and predeclared; there is no arbitrary generated code execution. Selection occurs on validation, then the reused test set is evaluated without threshold tuning. Source, split, dataset and output hashes make the result reproducible. Promotion requires a separate review and stronger evidence than this experiment provides.

## What I should learn

1. Trace one episode's `features`, `valid_actions`, sampled training action and post-action reward. Confirm no future outcome enters the feature vector or mask.
2. Change a copy of `actions.parquet` and verify the manifest check rejects it. Then rerun the experiment against the unchanged frozen input and confirm byte-identical output.
3. Explain why five training RNG seeds are not 500 independent test episodes, and why the [0, 0] paired interval gives no evidence of improvement over JointSLA.

## Next phase

Do not deploy Phase 7 v1. A new research iteration needs a preregistered protocol, genuinely new untouched workload seeds/environments, multi-step state/action dynamics if claiming MDP RL, realistic capacity/latency failure injection, and independent hardware validation. Separately, the Phase 5 full-suite/HTTP smoke and Phase 6 cluster dry-run gates remain open because this host lacks a permitted LangGraph DLL and cluster resources.
