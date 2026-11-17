# Phase 7 prospective synthetic holdout (2026-11-17)

## Repository facts discovered

Phase 7 v1 saved five policy weight matrices with `runtime_enabled=false`. Its test seeds 80–99 had already appeared in Phase 2/4. The frozen Phase 2 generator accepts new seed groups without modifying its source or earlier artifacts. The local Python environment still encounters a Windows Application Control block on LangGraph's native `ormsgpack` during repository-wide test collection.

## Implemented

- `PHASE7_FRESH_PROTOCOL.json` was written before generating the new outcomes. It fixes the v1 model and manifest SHA-256 hashes, untouched seeds 100–119, five scenario families, three arrival pressure factors, baselines, seed-cluster bootstrap and a strictly positive improvement gate.
- `research_phase7_fresh.py` evaluates the five **saved** policies without training, selection or tuning. It reuses the Phase 2 simulator and current-state deterministic action mask, and recomputes all action outcomes at each pressure factor. At factor 1.0 it checks exact agreement with the original simulator output.
- `results/phase7-fresh-v1` contains checked metrics and a SHA-256 manifest. Re-running against the same directory verifies identical bytes and rejects any changed output. The v1 artifacts remain unchanged.

## How to run

From the repository root in PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.research_phase7_fresh
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_phase7_fresh.py
```

The evaluator uses the hash-locked `results/phase7-v1/models.json` and writes or checks `results/phase7-fresh-v1`. A changed model, protocol, or existing result requires a new protocol and output version.

## Tests actually executed

The four focused tests cover unused seed separation, the locked model/manifest hashes, all 300 pressure cases, action-mask structure, exact repeated output, tamper refusal and model hash rejection. The original and fresh Phase 7 test modules pass together (9/9). A separate read-only evidence gate verifies 31 recorded output/source hashes across Phases 2, 4 and 7; its two tests pass, including a tamper case. Ruff lint/format, mypy and YAML parsing pass. The local full suite still fails during collection because Windows Application Control blocks `ormsgpack`. [Ubuntu CI run 44055591073](https://github.com/Dionisis09/sovereign-6g-jointsla/actions/runs/44055591073) passed the integrity gate, all **417 tests** and the fresh evaluation command on commit `42b9593`. No cluster or hardware test was executed.

## Evidence and limitations

Each pressure has 100 unique family/seed cases and five frozen policy evaluations. Rates below are **simulated post-action SLO rates**, not observed SLA performance.

| Arrival factor | JointSLA SLO | Learned mean SLO | JointSLA scale rate | Learned mean scale rate | Paired seed bootstrap 95% SLO delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1.0 | 0.35 | 0.35 | 0.37 | 0.37 | [0.00, 0.00] |
| 1.2 | 0.00 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |
| 1.5 | 0.00 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |

Across all three settings, the saved policy choices agree with the JointSLA gate on every case. The strict gate for scale rejects all cases at 1.2 and 1.5 pressure, so those settings show a common failure mode rather than policy robustness. No masked action was selected. The preregistered strict-positive lower-bound criterion fails at every pressure; the artifact records `REJECTED_OFFLINE`. The manual decision remains **DO NOT PROMOTE**. Nothing enabled a runtime, shadow or canary policy.

Seeds 100–119 are new and disjoint from Phase 2/4/7 train, validation and test groups, but they come from the **same synthetic generator**. Pressure changes only initial arrival rate; it does not model a new network, actual GPU contention or a cluster response. The simulator supplies full counterfactual outcomes and cannot validate real logged-action policy evaluation. The five weight matrices are correlated training repeats on the same data; paired intervals resample the 20 episode seeds, not 500 independent observations.

## Architecture decisions

Freeze the evaluation protocol and model hash before producing fresh outcomes. Keep the deterministic gate as the action authority, use one implementation of the Phase 2 outcome simulator, and use a new immutable result directory. Report the pressure-induced gate collapse explicitly rather than treating it as a successful stress test.

## What I should learn

1. Compare the factor 1.0 action outcome with its direct `episode()` output and explain why equality is a useful simulator integrity check.
2. Inspect the mask at factor 1.2 and trace why a high arrival rate can leave only no-op valid under the fixed Gold/max-two-replicas profile.
3. Explain why a fresh seed group from the same generator improves independence from earlier split reuse but does not establish external validity.

## Next phase

Keep the policy disabled. A new candidate needs a changed, preregistered policy or reward design and an independent workload environment where safe actions remain feasible under pressure. Measure real cluster admission, readiness, GPU contention, p95 latency and rollback before any deployment claim. Ubuntu CI now covers the full suite and HTTP smoke; a local Windows rerun awaits a host policy that permits the native dependency.
