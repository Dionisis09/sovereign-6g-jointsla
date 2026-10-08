# Controlled JointSLA experiment delivery

The verified simulator, its original four policies, traffic generation,
paper_evaluation sources and results/paper_30seeds are unchanged. Their hashes
are checked before simulation, on result reuse, and after independent verification.

## New source files

| File | Role |
|---|---|
| joint_routing/__init__.py | Separate experiment package |
| joint_routing/router.py | Fixed criteria and causal request scoring |
| joint_routing/controller.py | Routing-aware deployment evaluation |
| joint_routing/simulator.py | Per-replica queue facade around the inherited worker |
| joint_routing/experiment.py | Paired runs and read-only baseline reuse |
| joint_routing/analysis.py | Reused inference primitives, resource diagnostics, H1–H5 |
| joint_routing/presentation.py | CSV-backed report and eight exportable figures |
| joint_routing/validation.py | Independent exported-outcome and routing replay |
| joint_routing/README.md | Design and success rules frozen before main outcomes |
| run_joint_routing.py | Reproduction entry point |
| tools/verify_joint_routing.py | Standalone validation entry point |
| tests/test_joint_routing.py | Eligibility, causality, lifecycle, accounting tests |
| tests/test_joint_inference.py | Ties/losses, Holm, resources and overhead gates |
| joint_routing/DELIVERY.md | This inventory |

## Reproduce in PowerShell

```powershell
Set-Location 'C:\Users\dioni\Documents\ChatGPT\6g'
.venv\Scripts\python.exe -m pip install -r requirements-paper.txt
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_joint_routing.py --seeds 1:30 --reuse-results
```

To rerun the five new policies from the unchanged input generation:

```powershell
.venv\Scripts\python.exe run_joint_routing.py --seeds 1:30 --force
```

Standalone full validation:

```powershell
.venv\Scripts\python.exe tools\verify_joint_routing.py
```

`--force` overwrites only the selected new experiment output. The 120 original
baseline runs are reused; 150 new simulations give 270 comparative rows across
nine policies, with exactly 30 common seed pairs per policy. Outcome and routing
choices are deterministic; measured wall-clock overhead depends on the machine
and concurrent instrumentation. No additional dependencies or changed requirements
file are needed.

## Results and interpretation

The output directory is results/joint_routing_30seeds. Read report.md for all
requested sections, claim_ledger.csv for supported primary claims, paired_tests.csv
and paired_seed_differences.csv for inference and every negative seed, and
validation.json for the completed independent checks. The frozen protocol and
artifact_hashes.json establish source and exported-artifact integrity.

JointSLA versus SLA-aware reduces mean SLA failures from 56.87% to 50.91%, mean
request latency from 296.37 to 209.54 ms, p95 from 1315.17 to 877.26 ms and p99
from 2198.83 to 1634.22 ms. All four reductions pass the main 12-test Holm family.
Average replicas fall from 27.09 to 25.93 and VRAM residency from 94.34% to 91.18%.
All predeclared H1–H5 screens pass for the instrumented run.

The experiment strengthens evidence for coupled deployment and queue-aware routing
in this specific model. It does not reach a <15% failure target. Gold failures
are almost unchanged. Removing queue awareness degrades the four primary metrics,
but the full method does not show additional significant benefit over the
no-slack variant. These are important negative findings, not grounds for tuning.

The historical baseline already uses available-worker pull scheduling from a
common FIFO queue. New explicit per-replica queues change that mechanism, and
feedback can change deployments. These comparisons cannot isolate a pure routing
weight effect. The variance/slack risk is uncalibrated; timing excludes audit JSON
and is not added to simulated latency. Publication readiness, first-in-literature
novelty and production generalization require further evidence.

## Export inventory

- raw_policy_results.csv, new_policy_results.csv, summary_statistics.csv
- paired_tests.csv, ablation_tests.csv, paired_seed_differences.csv
- request_outcomes.csv.gz, routing_decisions.csv.gz, routing_attempts.csv
- routing_analysis.csv, replica_request_distribution.csv (served counts)
- resource_normalized_analysis.csv, hypotheses.json, claim_ledger.csv
- slot_trajectories.csv, node_trajectories.csv, actions.csv
- reservation_events.csv, lifecycle_events.csv, deployment_audit.csv
- control_snapshot_times.csv, inputs/seed_001.json.gz through seed_030.json.gz
- protocol.json, analysis_protocol.json, simulation_validation.json, validation.json
- artifact_hashes.json, report.md, main_results_table.md
- figures/01_joint_sla_breaches through 08_joint_controller_overhead,
  each in PNG 300 dpi, SVG and PDF

The request-count CV includes all allocated replicas, including unused instances.
The served-count CSV lists positive-count replica/node combinations; its CV must
not be substituted for the all-allocated-instance CV. Replica lifetimes differ,
so either distribution is descriptive rather than a fairness optimum.
