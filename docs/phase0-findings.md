# Phase 0 conclusion: FAIL and stop

The fixed 500-run matrix produced **no qualifying scenario levels or families**.
This rejects continuation under the declared Phase 0 rule for this synthetic
model. It does not disprove cross-layer contracts in general.

The decisive comparison is CATALYST versus strong B1:

| Case | Breach reduction vs B1 | Seeds improved | Additional rollout time | False contract blocks |
|---|---:|---:|---:|---:|
| S1 load, level 1 | 0% | 0/10 | 0 s | No contract vetoes |
| S1 load, level 2 | -2.9% | 0/10 | 0.1 s | 0% |
| S1 load, level 3 | 0% | 0/10 | 0 s | No contract vetoes |
| S2 network, level 3 | 46.8% | 8/10 | 15.1 s | 55.2% |
| S3 compound, level 2 | 15.9% | 3/10 | 15.3 s | 68.8% |
| S3 compound, level 3 | 30.2% | 7/10 | 20.7 s | 27.3% |

S1 shows no meaningful gain. The largest S2 gain has a positive paired CI but
violates both the <=3 s extra rollout-time and <=10% false-block limits. The
main S3 scenario fails consistency, completion-delay and false-block checks.
At S3/level 3, A2 actually has slightly fewer breach seconds than CATALYST
(6.5 versus 6.7 seconds), so the pre-action gate does not establish the required
advantage there. Lower S2 levels worsen breach time by 25% and 16%.

The exact A1=B1 equivalence check passes for all individual request outcomes,
as required when composition is disabled. S0's decisive B1/CATALYST outcomes
and lifecycle timings match exactly; all three policies have identical primary
outcomes. B0 has an aggregate 1.3 s completion difference and 0.48 ms p99
difference. The S0 fixture and validation-rule corrections are disclosed in
the protocol and full report; all original pilot outputs are retained.

All B0, B1, CATALYST and A1 rollouts complete (100/100 each). A2 completes 98/100:
S1/level 1/seed 7 and S3/level 2/seed 7 remain incomplete at the horizon. All
admitted requests finish, and none are rejected. CATALYST's false-block audit
finds 50 false blocks out of 97 contract vetoes (51.5%) over the two-second
counterfactual horizon. A no-veto run has no empirical false-block observations;
its zero numerator must not be interpreted as a validated predictor accuracy.

Independent verification reconstructs every saved primary metric from raw
outcomes: **500 runs, 30,000 samples, 1,195,930 request outcomes**. NumPy quantiles
agree with the reused VISTA helper. Request IDs and tape hashes match across
policies; source/config/protocol hashes remain unchanged since the final
negative-control stage. The three reused AIMCO/VISTA source files remain
unchanged. All 26 tests pass, including hard-rule fixtures that reject delayed,
false-blocked, inconsistent, ablation-equivalent and zero-baseline gains.

The research mechanism uses a sum of projected component p99s. This is a
heuristic, not a calibrated end-to-end quantile or a probabilistic guarantee.
The high false-block rate is consistent with overprediction, but these results
do not isolate which predictor assumption causes it. The experiments are not
tuned to rescue the mechanism, and no extra matrix is run.

Artifacts: `results/phase0-v1/report.md`, `analysis.json`, `runs.csv`, `summary.csv`,
`verification.json`, plots, and complete compressed evidence. Source attribution
is in `docs/reuse-provenance.json`; audit and omitted components are in
`docs/reuse-audit.md`.
