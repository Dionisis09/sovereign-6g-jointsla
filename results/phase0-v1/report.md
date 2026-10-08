# CATALYST Phase 0: FAIL

300 primary runs + 200 ablation runs. 100 matched tapes; ten seeds per scenario/level. Parameters were fixed before running.

S0 passed: True; B1/CATALYST exact equality: True; all-policy primary-metric equality: True. Rejected requests: 0.

Validation correction: the original 40-rps S0 fixture produced resource pressure. It was reduced to 10 rps before stress experiments; both pilot controls are preserved. A draft requirement for every B0 request to match B1 exactly was also corrected to the user's near-equality requirement: B1/CATALYST remain exact; all-policy breach seconds match; aggregate completion spread <=3 s and p99 spread <=5 ms. These corrections were made after seeing S0, and are disclosed rather than described as originally preregistered. The S1-S3 parameters and hypothesis rules were unchanged.

This is a synthetic feasibility result, not a validated 6G deployment or a novelty claim.

| Scenario | B1 breach s | CATALYST breach s | Reduction | Improved seeds | Paired delta 95% CI, s | Qualifies |
|---|---:|---:|---:|---:|---|---|
| S0/L0 | 0.20 | 0.20 | 0.0% | 0/10 | [0.00, 0.00] | False |
| S1/L1 | 2.60 | 2.60 | 0.0% | 0/10 | [0.00, 0.00] | False |
| S1/L2 | 3.50 | 3.60 | -2.9% | 0/10 | [-0.30, 0.00] | False |
| S1/L3 | 4.80 | 4.80 | 0.0% | 0/10 | [0.00, 0.00] | False |
| S2/L1 | 1.60 | 2.00 | -25.0% | 0/10 | [-1.00, 0.00] | False |
| S2/L2 | 2.50 | 2.90 | -16.0% | 0/10 | [-1.00, 0.00] | False |
| S2/L3 | 7.70 | 4.10 | 46.8% | 8/10 | [2.00, 5.30] | False |
| S3/L1 | 3.50 | 3.40 | 2.9% | 1/10 | [-0.60, 0.90] | False |
| S3/L2 | 4.40 | 3.70 | 15.9% | 3/10 | [0.00, 1.60] | False |
| S3/L3 | 9.60 | 6.70 | 30.2% | 7/10 | [0.50, 5.10] | False |

The CI resamples paired seeds, not individual requests. Improvement is relative to B1; a positive paired delta favors CATALYST. B0 is explanatory only.

| Scenario | CATALYST completion seeds | Mean completion delay vs B1, s | False contract block rate | A1=B1 | A2 loss vs CATALYST, % of B1 breach |
|---|---:|---:|---:|---|---:|
| S0/L0 | 10/10 | 0.00 | 0.0% | True | 0.0 |
| S1/L1 | 10/10 | 0.00 | 0.0% | True | -7.7 |
| S1/L2 | 10/10 | 0.10 | 0.0% | True | -31.4 |
| S1/L3 | 10/10 | 0.00 | 0.0% | True | -39.6 |
| S2/L1 | 10/10 | 1.60 | 100.0% | True | 6.2 |
| S2/L2 | 10/10 | 7.30 | 66.7% | True | 8.0 |
| S2/L3 | 10/10 | 15.10 | 55.2% | True | 13.0 |
| S3/L1 | 10/10 | 3.50 | 80.0% | True | 0.0 |
| S3/L2 | 10/10 | 15.30 | 68.8% | True | 2.3 |
| S3/L3 | 10/10 | 20.70 | 27.3% | True | -2.1 |

False-block rates use independent, two-second forced-action shadow replays. They are bounded diagnostics. Full secondary metrics and resource seconds are in `summary.csv`; all seed-level metrics are in `runs.csv`. Compressed evidence retains each request, sample, decision, rejection reason and counterfactual audit. All admitted requests drain.

Rollouts completed in 498/500 runs. CATALYST false blocks: 50/97 audited contract vetoes.

Interpretation: a level needs >=5% reduction with positive paired CI, at least eight improved seeds, completed rollout, <=10% false blocks, <=3 s extra completion time, and both ablation checks. Two levels in each of two stressed families are required. See the preregistered `docs/protocol.md`.

## Reuse and code quality

EXISTING CODE REUSED: AIMCO `jsonable`/`digest`; VISTA `quantile`, `write_json`, `write_gzip`. See `docs/reuse-provenance.json` for exact source hashes. Immutable tapes, public-only snapshots and paired request accounting adapt established prior patterns.

EXTERNAL/STANDARD LIBRARIES REUSED: SimPy, Pydantic, NumPy, pandas, matplotlib, pytest; dataclasses, enum, collections, hashlib, JSON, gzip, argparse, pathlib, importlib.metadata.

NEW RESEARCH-SPECIFIC CODE: four-clause compiler, shared local safety and cross-layer action gate; minimal service binding and paired decision analysis. Generic scheduling, validation, quantiles, storage, plotting and random sampling use reused code or established libraries.

UNNECESSARY COMPONENTS NOT IMPLEMENTED: multi-tenancy, agents, Kubernetes, OpenNebula, RL, digital twins, extra baselines/ablations, deployment integration, broad policy language, six simulators.

## Limits

Model quality and service/network profiles are stipulated. The gate sums layer p99 predictions, a conservative heuristic rather than an exact end-to-end quantile. The local predictor is shared by B1 and CATALYST and can be inaccurate during transitions. One-second sampled breach durations and two-second windows may miss shorter violations. Availability counts late requests, while requests are never dropped. Default zero update outage makes disruption/availability mainly diagnostic clauses. No capacity event is added to the primary matrix. Stronger calibrated predictors or tighter local latency budgets could erase a composition benefit. Resource use may differ despite identical limits.

Phase 0 stops here. No matrix expansion, result-driven tuning, or rescued novelty claim.
