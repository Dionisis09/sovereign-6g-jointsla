# First service-placement experiment

Pure Python experiment: 5 edge servers, 20 AI applications, 30 paired seeds,
four methods. No orchestration platform or real networking. The older CATALYST
experiment is separate and its results are preserved.

From the repository root (Python >=3.12):

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m placement_experiment.runner
```

An existing `.venv` is ready in this workspace. To change the seed range or config:

```powershell
& .\.venv\Scripts\python.exe -m placement_experiment.runner --trials 30 --seed 100 --output results/placement-repeat
& .\.venv\Scripts\python.exe -m placement_experiment.runner --config placement_experiment/config.json
```

Outputs: `results/placement/results.csv` (120 trial/method rows), `summary.csv`
(mean, sample SD, count for every metric including CPU/GPU per node),
`results_table.md`, three PNG/SVG figures, full application outcomes, generated
input scenarios, copied configuration and environment versions.

## Methods and heuristic

* Random: random application order, uniform choice among feasible nodes.
* Greedy: largest dominant demand first, then least normalized CPU/GPU/bandwidth
  utilization. This is a competent resource-balancing baseline.
* Shortest latency: input order, lowest estimated post-placement latency among
  feasible nodes. It accounts for current compute utilization and network RTT.
* `sla_weighted_placement`: applications descend by `traffic_load / SLA_ms`;
  greater load or a tighter SLA raises priority. For each feasible node, minimize:

```
r = estimated_latency_ms / application_SLA_ms
cost = 1.0*r + 0.35*mean(projected_CPU_util, projected_GPU_util)
       + 3.0*max(0, r-1)**2
```

Projected utilization penalizes depleted CPU/GPU headroom. The last term penalizes
predicted SLA excess. Node ID resolves ties; the heuristic is deterministic and
uses no future workload or search/tuning. Every method rejects a placement when
CPU, GPU **or bandwidth** would exceed capacity. An application remains unplaced
only when no current node is feasible. The heuristic does not guarantee optimality
or preserve earlier applications' SLAs; all latency metrics are recomputed after
the complete placement.

## Synthetic model and metric definitions

Each application has a randomly selected ingress edge. Pairwise network RTTs are
symmetric with zero diagonal. Bandwidth demand is requests/s × Mbit/request, in
Mbps. CPU/GPU demand and capacity are abstract reserved-resource units.

Estimated latency is ingress-to-target RTT plus
`base_processing_ms * (1 + CPU_util + 0.8*GPU_util + 0.3*bandwidth_util)`.
This transparent static model represents utilization pressure. It has no arrival
events, queueing, topology routing, shared-link contention, dynamic updates or
empirical calibration. All four methods use the same model and identical input
scenarios per seed. Defaults and heuristic weights are fixed before the runs.

Average latency is traffic-weighted over placed applications. `sla_violation_rate`
is failed offered traffic / total offered traffic: both placed applications over
their latency SLA and unplaced applications fail. `placed_sla_violation_rate`
separately measures latency violations conditional on placement. This avoids
claiming a benefit merely from refusing more traffic. Rates in CSV are fractions;
tables and charts display percentages. Node utilization uses final resource totals.
Runtime measures one algorithm call using `perf_counter_ns`; metric computation,
data generation and plotting are excluded. Runtime varies with host/system load.
Standard deviation uses `ddof=1` across seeds; error bars are SD, not confidence
intervals. Missing latency when all applications are unplaced is retained as missing,
never replaced by zero; summary count columns expose this case.

## Code and extension point

`data_generation.py`, `algorithms.py`, `metrics.py`, `runner.py`, `plotting.py`.
Future RL/optimization methods can be added to the `ALGORITHMS` dictionary with
signature `(config, scenario, seed) -> {application_id: node_id_or_None}`.
The metric evaluator independently checks the full allocation for capacity errors.
Only generic AIMCO/VISTA hashing and strict JSON writing are reused from
`catalyst/reused.py`; no earlier controller or scientific assumption is imported.

Tests: install pytest if needed, then run
`python -m pytest tests/test_placement.py -q` from the repository root.
