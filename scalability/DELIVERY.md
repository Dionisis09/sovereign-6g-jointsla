# Scalability experiment delivery

Completed controlled evaluation of the unchanged JointSLA, SLA-aware and
SLA-aware+ShortestQueue implementations. The preregistered protocol is in
[README.md](README.md); detailed results are in
[report.md](../results/scalability_30seeds/report.md).

## Execution and verification

- SMALL: 5 nodes / 20 services; MEDIUM: 10 / 40; LARGE: 20 / 80.
- Seeds 1–30, with identical hashed traffic tapes within each scale/seed.
- 270 fresh main simulations, preceded by 27 separate pilot simulations.
- 1,225,366 distinct offered requests across 90 main workload tapes;
  3,676,098 policy-specific request outcomes independently verified.
- 2,556,927 routing decisions replayed; 810 request quantiles recomputed.
- 31,978 reservation events checked. The verifier reports 315,000 node-slot
  checks across CPU, GPU and link resource trajectories.
- All offered requests completed; no drops, unplaced requests, loss or duplication.
- All 138 tests passed, including the 113 pre-existing tests.
- Protected source and both verified result directories remain byte-identical.

The full main run took 693.53 seconds including exports and run validation;
preflight, pilot and later statistical/independent verification are additional.
Per-run wall-clock timing in the CSVs excludes generation, export and validation.
Ten figures are exported as PNG (300 dpi), SVG and PDF.

## Result interpretation

All 12 primary paired comparisons favor JointSLA after the fixed Holm correction.
Relative SLA improvements at SMALL/MEDIUM/LARGE are 10.48%, 8.06%, 7.79%;
p95 improvements are 33.30%, 27.25%, 29.80%. All negative seeds remain in the
statistics and `negative_seed_cases.csv`. Average replicas, VRAM residency,
cold starts and accepted actions are lower at every scale.

H1, H2, H3 and H5 pass. H4 fails: LARGE mean full controller time is 26.84 ms,
above the preregistered 10-ms budget; SMALL and MEDIUM average 2.52 and 6.93 ms.
Performance persistence therefore does not establish acceptable overhead at
every scale. Gold-tier breaches also worsen descriptively at MEDIUM/LARGE;
aggregate gains do not establish priority-tier protection.

The global two-actions-per-slot budget is identical at every scale, so available
control opportunities per service decline. Compute load distributions and
capacity pressure pass the fixed preflight consistency screens. This study
supports empirical generalization within the synthetic model, not production
scalability or a mathematical complexity claim. No optional stress run was added.

## Files and measurement definitions

- `configuration.py`: proportional configuration and preflight consistency.
- `measurement.py`: timing wrappers and sampled process RSS without changing
  simulator event behavior, policy decisions or latency.
- `experiment.py`: protected hashes, frozen sources, pilot and sequential runs.
- `analysis.py`: unchanged statistical helpers, normalization and scale trends.
- `presentation.py`: ten figures, full report and evidence-linked claim ledger.
- `validation.py`: independent request, routing, resource and statistical checks.
- Root `run_scalability_experiments.py`: reproducible command-line runner.
- `tools/verify_scalability.py`: independent verification entry point.
- `tests/test_scalability.py`: additional scale, causality and accounting tests.

`results/scalability_30seeds/` contains the requested raw, summary, paired-test,
configuration, trend, gain, resource, overhead and negative-case CSVs, plus the
report, figure exports, per-run compressed audit data and verification manifests.

Latency statistics include drainage of the arrival cohort after the 100-slot
horizon. Physical utilization and VRAM residency describe the arrival horizon.
Actual within-horizon completion throughput is separately exported. Replica
eligibility is sampled at the existing slot-end snapshots; allocated replica
residency is integrated. Busy GPU utilization is distinct from VRAM residency.

Full controller timing includes snapshot construction, policy and application;
total process CPU additionally includes routing dispatch and online audit
creation. Host CPU timing is quantized and process-wide. No measured wall-clock
cost is injected into simulated request latency. Baseline has no explicit router,
so CPU per routing decision is undefined with an availability flag. Rare
bootstrap migration ratios with zero baseline denominators are marked undefined;
absolute confidence intervals retain every resample.

## Reproduction

From the repository root with the existing virtual environment:

```powershell
.venv\Scripts\python.exe run_scalability_experiments.py --pilot
.venv\Scripts\python.exe run_scalability_experiments.py --seeds 1:30 --force
.venv\Scripts\python.exe run_scalability_experiments.py --seeds 1:30 --reuse-results
.venv\Scripts\python.exe tools\verify_scalability.py
.venv\Scripts\python.exe -m pytest -q
```

On a fresh output directory, omit `--force`; the successful pilot is required
and automatically run if absent. `--reuse-results` rebuilds analysis/figures and
independently verifies existing main outcomes without rerunning simulations.
`--force` reruns main simulations under the same frozen protocol and cannot
target protected result directories. Changing a frozen core source requires a
separate experiment output rather than silently replacing this experiment.
