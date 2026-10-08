# Statistical evaluation for the dynamic placement paper

This separate analysis package calls the existing `dynamic_placement.Simulator`
and its policies directly. No simulator, traffic, deadline, orchestration or
historical experiment files are changed. The only main configuration overrides
are `first_seed=1` and `trials=30`.

From the repository root, Python 3.12 or newer:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-paper.txt
& .\.venv\Scripts\python.exe run_paper_experiments.py --seeds 1:30
```

The complete measured run has already been saved. Analyze it again without
running the simulator:

```powershell
& .\.venv\Scripts\python.exe run_paper_experiments.py --seeds 1:30 --reuse-results
```

For a full main simulation rerun, replace `--reuse-results` with `--force`.
These options are mutually exclusive. Existing main results are not silently
overwritten by the default command. Reuse refuses changed engine/config/seed
inputs and independently validates exported requests after analysis.
`--output` selects another output directory; `--config` selects the existing
configuration file. Run the CLI from anywhere; it resolves repository sources.

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m tools.verify_paper_results
```

Tests require the optional `pytest==9.1.1` package. The supplemental capacity,
admission and prewarming simulations are **never rerun** by the paper command;
their existing full evidence verifiers run before reuse.

## Experimental unit and metric definitions

- One independent generated workload per seed; all four policies share its
  exact traffic tape, topology, service metadata and initial placement.
- Completion-aware accounting retains every offered request and drains accepted
  requests after the arrival horizon. Drops/unplaced requests count as failures.
- `sla_breach_rate`, per-tier breach rates, `drop_rate` and new utilization fields
  are fractions. Legacy `_pct` fields retain percentages.
- `mean_latency_ms` and `mean_request_latency_ms` both mean the completed-request
  arithmetic mean. Legacy `average_latency_ms` remains identical.
- `mean_slot_latency_ms` preserves the equally weighted nonempty arrival-slot
  mean, identical to legacy `time_average_slot_latency_ms`.
- Median/p95/p99 use NumPy `method="linear"` quantiles of completed **request**
  latencies within each run. Their policy summaries average seed-level quantiles;
  they do not pool requests across seeds or take quantiles of slot means.
- End-to-end latency includes service/resource queues, network, all three compute
  stages and lifecycle penalties. No hypothetical latency is assigned to drops.
- Average replicas uses the exact allocated-replica integral over the arrival
  horizon, including cold replicas. Peak replicas is the maximum slot-end
  allocation plus the initial count; transient event-level peaks are unavailable
  from the existing snapshots and are not claimed.
- Average CPU/GPU utilization gives equal weight to node-slots. Separate
  `pool_*_utilization` fields weight by heterogeneous physical capacity. GPU
  compute busy utilization and VRAM residency are distinct.

## Statistical methods

The 30 seeds are the replication units, avoiding request-level pseudoreplication.
Each mean CI uses 10,000 percentile bootstrap samples at 95% confidence. Root
RNG seed is 73001; SHA-256 keys select stable substreams. Bootstrap differences
and ratios of means resample complete matched pairs. These are pointwise CIs,
not simultaneous intervals or a guarantee of finite-sample coverage.

Primary comparisons are SLA-aware versus each of Static, Reactive and Periodic
for SLA failure, request mean latency, p95 and p99: 12 two-sided Wilcoxon tests.
Holm correction controls the familywise testing threshold. Both raw and adjusted
p-values are saved. Tests address signed differences around zero, rather than
mean equality, and assume independent seed pairs with an appropriate symmetry
interpretation. Mean-difference bootstrap CIs provide complementary estimates.

Differences are **baseline minus proposed**, so positive means improvement.
Relative improvement is `100*(mean baseline - mean proposed)/mean baseline`.
Per-seed relative differences use that seed's baseline. Undefined zero-baseline
ratios fail explicitly. Win/tie/loss and Wilcoxon ranks round differences to
12 decimals. The Wilcoxon procedure discards zeros, averages tied ranks, uses
exact p-values without zeros/ties, and uses a tie-corrected asymptotic calculation
otherwise. All-zero pairs are reported as W=0, p=1, effect=0.

Paired rank-biserial effect size is `(W_positive-W_negative)/(W_positive+W_negative)`;
+1 favors SLA-aware. Supported improvement requires positive mean difference,
positive lower paired mean-difference CI and Holm-adjusted p<0.05. Neither raw
significance alone nor a lower numerical mean is labeled a supported improvement.

Supplemental results reuse seeds 0–29, with CIs from their complete raw runs.
They share 29 seeds with the main experiment and are not an independent
replication. Admission reports all-offered and conditional admitted failures
alongside drop rates. Prewarming negative results are retained.

## Artifacts in `results/paper_30seeds`

- `raw_policy_results.csv`: 120 seed/policy rows, all requested counts, rates,
  request quantiles, costs and utilization, plus unchanged legacy metrics.
- `summary_statistics.csv`: long-format mean/SD/median/min/max/95%-CI/count.
- `paired_tests.csv`: 12 comparisons, raw/Holm p-values, difference/relative CIs,
  paired effect sizes and wins/ties/losses.
- `paired_seed_differences.csv`: all 360 paired metric observations, including
  ties and losses. `cost_tradeoffs.csv` discloses higher proposed costs.
- `capacity_raw_results.csv`, `capacity_summary.csv`: existing 180 capacity runs
  and 95% CIs for both request and slot mean latency.
- `scenario_raw_results.csv`, `scenario_summary_statistics.csv`,
  `supplementary_paired_summary.csv`: unchanged intervention evidence and
  descriptive paired summaries.
- `report.md`, `main_results_table.md`, `claim_ledger.csv`: generated exclusively
  from the CSVs, including safe claims, non-winning seeds and limitations.
- `figures/01` through `10`: 300-dpi PNG plus SVG and PDF vectors; all interval
  error bars show 95% bootstrap CIs of means. Paired scatter plots show all seeds.
- `request_outcomes.csv.gz`, per-slot/node trajectories, traffic, inputs and
  action/reservation/lifecycle CSVs preserve complete simulation evidence.
- Simulation/analysis protocols, package versions, supplemental provenance,
  `validation.json` and `artifact_hashes.json` support reproducibility.

Independent verification reconstructs all request latency components, request
quantiles and counts, pairing, resource reservations, summary intervals,
per-seed differences, Wilcoxon p-values (exact DP or tie-corrected normal CDF),
Holm correction, effects and reported improvement claims. Original 76 tests
remain unchanged; added tests cover accounting, inference and causal snapshots.
