# Capacity sweep: 5–10 edge nodes

The sweep adds 90 runs: 8, 9 and 10 nodes, each with the same 30 seeds
used by the previous capacity experiment. The verified 5–7-node runs are reused,
giving six capacity points and 180 paired runs in `combined_runs.csv`.

Run from the repository root after generating the previous scenario exports:

```powershell
& .\.venv\Scripts\python.exe -m dynamic_placement.capacity_sweep
& .\.venv\Scripts\python.exe -m tools.verify_capacity_sweep
```

The runner accepts `--config`, `--history`, `--output` and `--master` paths.
Defaults are `dynamic_placement/config.json`, `results/dynamic_scenarios`,
`results/capacity_sweep` and `results/dynamic`, respectively.

## Controlled comparison

All capacities use identical requests, service demands, deadlines, ingress
nodes and traffic bursts for a given seed. Extra heterogeneous nodes and links
use separate deterministic random streams, so each smaller topology is a
prefix of every larger topology. The initial greedy placement is recomputed
for the available pool. The SLA-aware decision function, three-replica limit,
two-action budget and lifecycle penalties remain unchanged. There is no
predictive prewarming or admission control, and no requests are dropped.

The latency table uses equal-weight arrival-slot means within each run;
request-weighted latency is exported separately. All requests drain to
completion. SLA failures use all offered requests. Summary uncertainty is
sample standard deviation across seeds, not a confidence interval.

## Locating diminishing returns

The descriptive knee analysis fits a continuous two-segment line to mean SLA
failure versus node count. It evaluates interior candidates 6–9 and selects
the smallest residual sum of squares. A knee requires a declining first
segment and at least a 25% reduction in absolute slope afterwards. The
analysis resamples the 30 complete paired seed curves 1,000 times with RNG
seed 6801. Method settings are recorded in `protocol.json`.

The best fit selects 7 nodes. Bootstrap samples select 7 in 68.5% of cases,
8 in 31.4%, and no qualifying knee in 0.1%. Thus the observed region of
diminishing returns is approximately **7–8 nodes**, rather than an exact
physical inflection or a proven economic optimum. This does not establish
performance at untested capacities.

At 8, 9 and 10 nodes, mean SLA failure is respectively 27.97%, 23.19% and
21.08%. Adding these nodes gives successively smaller mean reductions:
6.91, 4.79 and 2.11 percentage points. The mean **<15% target remains unmet**;
1/30 seeds meet it at 9 nodes and 2/30 at 10 nodes.

## Exports

`results/capacity_sweep` contains the new request outcomes, per-slot and
per-node trajectories, action and capacity ledgers, hashed inputs, combined
run table and mean/SD/count summary. `marginal_gains.csv` records the mean and
sample SD of paired differences. `knee_analysis.json` and
`target_evaluation.json` document the knee fit and target checks.

Three figures are provided as PNG and SVG:

- `capacity_curve`: latency and SLA failure against capacity, with sample SD.
- `marginal_benefits`: paired reductions from each added node.
- `gpu_utilization_over_time`: pool utilization weighted by GPU compute units,
  then averaged across seeds; individual node trajectories remain in CSV.

The master `results/dynamic/summary.csv` retains its eight earlier rows and
adds the three new capacities. The capacity and marginal-benefit figures are
also copied there. Earlier trajectories and figures are preserved.

The independent verifier checks all 528,408 new request outcomes, paired
traffic, topology prefixes, source/input hashes, resource reservations,
summary statistics, marginal differences and the fitted curve. Its report
is `export_verification.json`.
