# Frozen scalability/generalization protocol

Research question: Does the verified JointSLA preserve benefit as system size
increases proportionally? No new algorithm, score, threshold or tuned parameter
is introduced. SMALL=5 nodes/20 services, MEDIUM=10/40, LARGE=20/80. Seeds 1–30,
100 slots of 0.1 s, unchanged CPU→GPU→CPU colocated stages and lifecycle.

## Generation and comparability

Use the unchanged generate_workload with only node_count and service_count
changed through dataclasses.replace. Every distribution, traffic parameter,
burst, deadline mapping and capacity distribution is identical. Service tier
assignment is the verified ID modulo three; finite-size fractions differ by
at most 3.34 percentage points. Node/service/request draws are not tiled copies.
Within each scale/seed, all policies receive exactly the same immutable tape.
SMALL must exactly reproduce the existing verified performance metrics.

Before pilot outcomes, check all 90 scale/seed workloads. Four services per node
and burst multiplier three are exact. Across 30-seed scale means, demand,
deadline quantiles and per-tier means, requests/service, rates/node, burst
frequency and expected CPU/GPU/bandwidth pressure must differ by <=15% from
SMALL; tier fractions must differ by <=4pp. All initial services must fit.
These predetermined tolerances screen stochastic distribution consistency,
not exact difficulty matching for each seed. Export every per-seed value.
GPU execution demand is one unit for 10 ms per request; gpu_vram_gb is
residency, not a separate GPU compute-demand distribution.

The common action budget remains TWO actions per control slot at every scale,
as required by frozen algorithmic parameters. Thus action opportunities per
service decline with scale. Max replicas/service remains three. This is an
algorithmic scalability constraint, not increased exogenous offered pressure;
it must be disclosed when interpreting larger-scale results.

## Policies, pilot and output protection

Freshly run SLA-aware, JointSLA and SLA-aware+ShortestQueue at all three scales.
The original policy functions, physical worker, routed queue facade and score
are imported unchanged. Instrumentation adds CPU/snapshot timing only.
Before main execution run seeds 1,2,3 (27 simulations), sequentially. Require
all requests accounted, finite primary metrics, identical tapes, bounded
physical utilization/reservations, <=4096 MiB sampled process RSS, <=600 s
wall time/run and <=120 s simulated queue-drain time. These generous execution
guards detect malfunction/resource infeasibility; they are not performance
success criteria. If a guard fails, do not weaken workloads or retune policy.
Full execution freshly runs 30 seeds × 3 scales × 3 policies=270 simulations;
pilot results are kept separately and are not selected into the main sample.

Protect all verified source files and every byte under results/paper_30seeds
and results/joint_routing_30seeds with before/after hashes. New outputs go only
under results/scalability_30seeds. Refuse a protected destination, even --force.
Freeze source hashes, configs and this document before pilot outcomes. No
post-outcome parameter or hypothesis changes, including after pilot results.

## Statistics and predeclared hypotheses

Use unchanged paper_evaluation bootstrap/signed-rank/Holm functions: 10,000
seed-level paired bootstrap samples, two-sided Wilcoxon, Holm, rank-biserial.
One primary Holm family spans THREE scales × FOUR metrics=12 tests, comparing
JointSLA with SLA-aware. A separate 12-test secondary family compares with SQ.
Positive difference means comparator minus JointSLA. Supported improvement
requires positive mean and lower paired mean-difference CI and Holm p<0.05.
Relative improvement is a ratio of scale-level seed means, with paired-seed
bootstrap CIs. Quantiles are request-level within runs, never slot quantiles.

- H1: supported SLA improvement at all three scales.
- H2: supported p95 improvement at all three scales.
- H3: SLA AND p95 supported in at least two scales; LARGE mean gains in both
  are nonnegative and JointSLA loses in no more than 15/30 seeds for either.
  This operational screen follows the requested majority-scales/no-systematic-
  reversal definition. It does not imply equal relative gain or linear scaling.
- H4: at ALL scales JointSLA mean full controller including snapshot <=10 ms
  (10% of the 100-ms control slot), mean per-seed controller p95 <=100 ms,
  and mean per-seed routing-attempt p95 <=1 ms. Budgets are operational screens,
  not hardware profiling or a mathematical complexity claim. If LARGE exceeds
  them, report failure rather than tune. Report normalized times regardless.
- H5: at ALL scales upper paired bootstrap bounds for average-replica increase
  <=5%, VRAM-residency increase <=2pp, and actions/1000-request increase <=5%.
  This is a measured-resource comparability screen, not causal efficiency proof.

No optional LARGE-STRESS run is part of the primary protocol; prioritize the
complete scale-preserving study. Static adds little to this specific comparison
and is omitted. No outliers, loss seeds or failing hypotheses are removed.

## Timing and denominators

Wall runtime measures the audited simulation, including routing audit creation,
but excludes workload generation, export and post-run validation. Routing-attempt
timing reuses verified scope: construction/scoring/counterfactuals, excluding JSON.
Full controller wall timing adds control-start snapshot to compute/apply time.
CPU time measures snapshot, policy and apply separately with process_time_ns;
it is process CPU in the sequential instrumented run, not isolated thread CPU.
RAM is sampled process working-set/RSS, not a per-policy allocation proof.

Total controller CPU includes control-start snapshot/policy/apply CPU plus all
routing-dispatch CPU (including failed eligibility, redispatch and audit creation); separate
fields retain control-only and routing-only costs. Controller ms/request uses
all offered requests. Controller ms/routing-decision uses successful assignments;
baseline has no explicit router, so that ratio is undefined with an availability
flag, never an invented measured zero. Decisions/simulation wall-second and
decisions/routing-CPU-second are separate, explicitly scoped diagnostics.
Replicas/service uses allocated replica-seconds/horizon/service count. Eligible
replica counts are sampled at the existing slot-end snapshots and exclude cold,
retiring and pending migration states; their mean is a sampled time-average,
not an exact continuous integral. No per-SimPy-event instrumentation is introduced;
requests/eligible-replica divides completed requests by their time-average eligible
count. VRAM per node is both mean reserved fraction (%) and mean reserved GiB;
busy GPU execution utilization remains separate.

## Reproduce

```powershell
.venv\Scripts\python.exe run_scalability_experiments.py --pilot
.venv\Scripts\python.exe run_scalability_experiments.py --seeds 1:30 --force
.venv\Scripts\python.exe run_scalability_experiments.py --seeds 1:30 --reuse-results
.venv\Scripts\python.exe tools\verify_scalability.py
```

Per-run gzip exports bound accumulated memory; simulation/audit logic is unchanged.
All 113 existing tests must pass, plus scale, accounting, causality, timing identity,
normalization and trend tests. Reports/figures contain actual means and CIs,
negative seeds and safe conditional claims, including Gold-tier and no-slack
limitations inherited from the previous mechanism experiment.
