# SLA-reduction scenarios

The original simulation, traffic generator and `sla_aware` function are unchanged.
This extension compares three scenario families on **30 paired seeds**, plus a
fresh five-node SLA-aware baseline. Increased capacity has two variants: six
and seven nodes. This gives **150 runs**, each with 100 slots.

```powershell
& .\.venv\Scripts\python.exe -m dynamic_placement.scenarios
& .\.venv\Scripts\python.exe -m tools.verify_dynamic_scenarios
& .\.venv\Scripts\python.exe -m pytest -q
```

Dependencies remain those in `requirements.txt`; tests also need pytest.
The CLI accepts `--config`, `--trials` (minimum 30), `--seed`, `--output` and
`--original`. Defaults use the existing config, seeds 0–29, new exports in
`results/dynamic_scenarios` and the original results in `results/dynamic`.
The scenario protocol requires the original five-node baseline. Parameters and
source hashes are saved in `protocol.json` before measured runs.

## Predictive prewarming

The controller takes a **moving average of the last ten completed slots** of
offered arrivals. When its aggregate rate rises above 1.5 times the declared
mean, it detects a burst episode. It estimates the onset by subtracting half
the moving-average window from the crossing slot, then predicts the next onset
using the configured 30-slot period. Phase and burst duration are not given to
the predictor. The first burst has no learned phase and is handled reactively.

One or two slots before the predicted onset, the controller considers scale-out.
It estimates each service's burst rate from the maximum past ten-slot moving
average in its recent period history. Replica need uses that rate, the existing
replicas' network/compute pipeline time and the 80% threshold. Gold/Silver
priority and load/deadline ranking determine which services are prewarmed.
Feasible targets are scored by network delay, CPU/VRAM headroom and current busy
pressure. Predicted replicas are protected against scale-in through the estimated
burst episode; normal SLA-aware actions fill any remaining action budget.

All existing limits still apply: three replicas per service, two actions per
slot, three-slot cooldown, finite CPU/VRAM/bandwidth, one-slot cold start and
the 5 ms first-request cold penalty. Prediction moves cold starts earlier; it
does **not** delete their cost. Forecasts can be inaccurate, and compound Poisson
request arrivals remain random. Only the periodic rate envelope is forecast.

Exports include causal moving-average/phase forecasts, proposed prewarm actions,
accepted prewarm counts, cold starts, first-request penalty totals, starts
overlapping actual bursts, replica-seconds and VRAM GB-seconds. Actual burst flags
are used only for retrospective measurement, never for policy decisions.

## Increased capacity

One and two extra heterogeneous nodes are appended using independent seeded
streams. The five original nodes and their links, service demands, ingress
locations, priorities, deadlines, noise, bursts, arrivals and request work are
unchanged. The six-node pool is a prefix of the seven-node pool. This avoids the
RNG confounding that would arise from regenerating a scenario with a different
node count.

The same initial greedy algorithm is rerun on the enlarged resource pool, then
the **identical `sla_aware` function and parameters** orchestrate it. Results
therefore measure the expanded pool together with initial placement adapting to
that pool. They do not isolate only a GPU capacity increase. Replica/action
limits and execution times are unchanged. The topology-independent `traffic_hash`
must match across every case for a seed; `workload_hash` also includes topology
and initial placement and therefore differs for capacity variants.

## Tier-based admission control

Only **new Bronze requests** can be rejected. Gold and Silver are never dropped
administratively. The existing queues are unbounded, so 80% requires an explicit
budget. As agreed, the budget is dynamic, not a fixed request count:

```text
compute_pipeline_ms = preprocessing + inference + postprocessing = 14 ms
queue_budget = max(1, ready_replicas) × max(1, ceil(deadline_ms / compute_pipeline_ms))
reject incoming Bronze request if current_waiting_requests / queue_budget > 0.80
```

Ready replicas exclude cold starts, pending migrations and retiring instances.
The strict `>` threshold implements "exceeds 80%"; the incoming request is not
included in the current depth. No already-admitted request is cancelled or lost.
Each arrival saves depth, budget, ready replica count and the drop decision.
The budget is a transparent admission proxy rather than a guarantee that all
accepted requests meet their deadlines; it does not account for every network
or GPU queue wait.

The SLA-aware controller still tracks offered rates, including rejected arrivals;
this keeps its function and telemetry-rate semantics identical to the baseline.
Dropping Bronze changes its queue/completion feedback and physical work, which
can protect higher tiers. It does not automatically free resident VRAM.

## Denominators and the <15% target

- `sla_breach_pct`: failures / **all offered requests**. Drops and any unplaced
  requests count as failures, as in the original experiment.
- `admitted_sla_breach_pct`: deadline misses / completed admitted requests.
  This conditional percentage must be read together with drop percentage.
- `drop_pct`: rejected requests / all offered requests.
- Per-tier SLA failure, admitted breaches and drop rates use that tier's own
  denominator. `gold_silver_sla_breach_pct` weights every Gold/Silver request
  equally rather than averaging their percentages.
- Mean request latency excludes dropped requests because they have no completed
  service delay. Equal-slot latency also excludes drops; they remain in failure
  and drop plots. Admitted requests drain after slot 100 as before.

The goal is evaluated as **mean all-offered SLA failure <15% across the 30 seeds**.
The number of seeds individually below 15% is also saved. Removing Bronze traffic
from the SLA denominator cannot establish success. Weights, deadlines, traffic
and thresholds are not changed after observing the results. Mean ± SD describes
scenario variation; it is not a significance or generalization claim.

## Outputs and preservation

`results/dynamic_scenarios` contains:

- `summary.csv`, `runs.csv`, `results_table.md`: all five paired cases, complete
  mean/SD/count metrics, including cost and per-tier results.
- `request_outcomes.csv.gz`: every offered request, including explicit dropped
  records with missing completion/latency and `breach=True`.
- `admission_events.csv.gz`: one audited admission observation per arrival.
- `slot_trajectories.csv`, `node_trajectories.csv`, `traffic.csv`: complete paths.
- `inputs/seed_*_CASE.json.gz`: full paired evidence for every case.
- `forecast_trajectories.csv`, `prewarm_proposals.csv`, `actions.csv`,
  `reservation_events.csv`, `lifecycle_events.csv`: prediction and lifecycle costs.
- `paired_differences.csv`, `target_evaluation.json`, `protocol.json`,
  `environment.json`, `verification.json`, `export_verification.json`.
- Updated latency, cumulative SLA/drop, and seven-node GPU figures as PNG/SVG.

`results/dynamic/summary.csv` retains the original four policy rows and appends
the four new variants (the three scenario families). A `scenario` column
distinguishes them. Original summary and figures are backed up as
`original_summary.csv` and `original_figures/`. Historical runs, trajectories,
request evidence and the original ZIP remain unchanged. Updated scenario plots
also appear at the original three figure paths. The fresh scenario baseline
is not duplicated in the combined summary.

Columns for nodes absent from a case have missing means/SDs and count zero.
New metrics that were not measured in historical rows remain missing rather
than being invented. The historical verifier reads `original_summary.csv`
when available, so it can still verify the original experiment independently.

The export verifier reconstructs request latency components and SLA/drop/tier
denominators, all summary statistics, the reservation ledger, input/source
hashes, admission thresholds, forecasts from past arrivals, and prewarm lead
times. Tests additionally verify exact baseline preservation, unchanged
paired traffic, causal prediction and tier-specific dropping.
