# Myopic Joint Optimization experiment

Independent, causal, training-free comparator for the frozen optimized JointSLA.
No existing simulator, policy, traffic/configuration, statistical helper or
verified output is modified. SciPy is already in `requirements-paper.txt`;
no additional solver dependency is required.

From the repository root (Python 3.12 used for the delivered run):

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_strong_baseline.py --pilot --force
.venv\Scripts\python.exe run_strong_baseline.py --seeds 1:30 --force
.venv\Scripts\python.exe run_strong_baseline.py --seeds 1:30 --reuse-results
```

The first full execution runs the pilot automatically if none is verified.
An existing verified pilot must match current simulation-source hashes. `--force`
replays only the new experiment. `--reuse-results` recomputes analysis, figures
and independent validation without replaying simulations. The publication seed
range is intentionally fixed to `1:30`; an alternate range would be a different
protocol. Repeated host timings vary; semantic traces and bootstrap inference
are deterministic. Previous verified result folders must remain present for
the protected hashes and reuse/exact comparisons.

Outputs: `results/strong_baseline_30seeds/`. See its `report.md` for all numerical
results, intervals, negative seeds, B1–B5 and limitations. Per-run exports include
request outcomes, slot/node trajectories, actions, physical reservations,
lifecycle events, routing changes, full routing batches, solver statuses and
CPU/wall timing. Historical SLA-aware scientific measurements are reused;
new tier latency/median timing fields are reconstructed from its old exports.
Its host timing is explicitly historical. Both primary policies are run freshly
with common current-lifecycle telemetry, whose observation overhead is charged.
The CPU observation counter also includes this common telemetry extension;
wall time and CPU counters have explicitly checked scopes. Causal timestamp
checks allow 1e-12 seconds for floating event arithmetic, while frozen scientific
frame comparisons are exact, without tolerances.

## Model and scope

`optimization.py`: frozen normalized objective, exact rectangular min-cost
matching within oldest-first blocks of 64, and exact binary budget-two menu
selection with a deterministic 50,000-pair work limit. Each deployment option
is evaluated using the same assignment model, with resource/lifecycle cost.
Positive reservation increments are jointly constrained across services.
No-op/previous queued state is the fallback, never JointSLA.

`simulator.py`: routing/deployment adapter around inherited physical SimPy
workers. It reassigns only currently waiting work, preserving in-flight work,
CPU→GPU→CPU execution, per-replica FIFO and original source event ordering.

`protocol.py`: immutable weights/configuration/hypotheses and protected SHA-256
hashes. `experiment.py`: seed pairing, pilot/main runs and audit exports.
`analysis.py`: unchanged seed-level bootstrap/Wilcoxon/Holm helpers.
`presentation.py`: 29-section report and 12 figures in PNG 300 dpi/SVG/PDF.
`validation.py`: request/component/reservation/lifecycle reconstruction, batch
objective checks, exact historical JointSLA comparisons, independent rank/p
and bootstrap calculations, figures and artifact hashes.

Weights: SLA=1, latency=1, congestion=.25, resource=.35, cold/scale=.25,
migration=.25. These are fixed before any pilot outcomes. Lateness is convex
normalized excess deadline, not a calibrated risk probability. Optimal solver
status applies only to the finite subproblem: matching blocks and additive
deployment menu. The complete backlog, nonlinear contention and future horizon
are not globally optimized.

Native MJO routing timings refer to batch callbacks; native JointSLA routing
timings refer to individual dispatches. Use full controller time or total CPU
per offered request for common-denominator comparisons. Audit overhead is
included. RSS is sampled. Pilot runtime estimates exclude later export,
report/statistics and independent validation overhead.
Solver call counts include nonempty assignment attempts and deployment
selection. One assignment event can contain multiple exact matching blocks,
whose count is recorded in the event. An empty assignment has analytically
zero request cost and does not invoke a matching solver or create a solve event.

See [LITERATURE_MAPPING.md](LITERATURE_MAPPING.md) for the generic formulation
and explicit non-replication statement. B1 must pass before labeling this MJO
implementation generally stronger than SLA-aware in the tested model. B2/B3
are operational bootstrap screens, not statistical equivalence proofs. Failed
strength checks and negative outcomes are preserved.
