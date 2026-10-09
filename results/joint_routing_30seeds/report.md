# Research Question

Does coupling SLA-aware placement/scaling with queue-aware online routing add SLA/tail-latency benefit over the verified SLA-aware orchestrator at acceptable resource and reconfiguration cost?

# Existing SLA-aware Baseline

The verified baseline uses a common FIFO service queue with available replicas pulling requests. It already adapts assignment to availability; it is not arbitrary/static routing. Its deployment/scaling function, physical worker and all verified results remain unchanged.

# Joint Placement and Routing Design


Eligible means ready, not retiring, not awaiting migration, a feasible resident
reservation, and sufficient physical capacity to execute its service. An active
busy replica may receive queued work; a cold/migrating replica may not.
If none is eligible, requests wait in a pending service queue. They are not
dropped. On replica readiness or migration reallocation, waiting work is
redispatched in arrival order. In-flight work is never moved or interrupted.

For candidate i and request with current age a:

```
queue_wait = waiting_count_i × observed_mean_cycle_i + remaining_busy_estimate_i
resource_wait = CPU_work_ms × rho_CPU/(1-rho_CPU)
              + inference_ms × rho_GPU/(1-rho_GPU)
              + observable_GPU_waiters × inference_ms/GPU_units
completion_estimate = a + queue_wait + resource_wait + network
                    + nominal_compute + applicable_first_request_penalty
slack = deadline - completion_estimate
variance_proxy = observed_cycle_variance × (waiting_count + busy_indicator + 1)
risk_proxy = 1 if slack <= 0 else variance_proxy/(variance_proxy + slack²)
```

The utilization proxy uses previous-slot measured fractions, capped at the
existing 0.98 limit. Cycle mean/variance update from completed requests only,
excluding service queue waiting, using the existing EWMA alpha=0.5. Initial
variance uses nominal compute and the existing work jitter sigma. Migration
resets the source-node observation when the destination differs.

Choose lexicographically by risk proxy, then largest slack, then completion,
then replica ID. The variance/slack expression is Cantelli-inspired, but is
**not a calibrated probability**: estimated moments and dependent resource
waiting do not justify a probabilistic SLA guarantee. Without replica variance
differences this may have the same ordering as minimum predicted completion;
the no-slack ablation tests whether this term adds practical value.

The arriving request's pre-generated work factor is never inspected for scoring.
No future requests or burst flags enter the controller/router. Predictions are
proxies and can be wrong. Routing computation is measured in wall time, as is
existing controller time; neither is injected into simulated request latency.


# Formal Problem Formulation


At unchanged control intervals, tier/SVRS prioritization considers feasible
keep, scale-out, scale-in and migration actions with existing limits, cooldown,
capacity checks and lifecycle penalties. Candidate quality virtually dispatches
up to the first **20 currently waiting requests**, or one nominal probe if none
wait. Virtual queues are a copy; no future arrival is generated. Cold-start or
migration availability delay enters hypothetical target completion estimates.
This bounded greedy evaluation is an approximation, not a solver or oracle.

Write x[s,n,t] for allocated replica count (with eligible count distinguished
by lifecycle state), and r[q,n,t] for a request's current binary assignment.
The service-level r[s,n,t] is the fraction of dispatched requests assigned to
node n during the slot. Routing is permitted only where an eligible replica
exists. Each dispatched admitted request has sum_n r[q,n,t]=1; a temporarily
pending request has no assignment until eligibility returns. Redispatch removes
its previous waiting assignment before replacing it.

Conceptually minimize tier-weighted predicted SLA failure and normalized
end-to-end delay, plus migration, cold-start and resource costs, subject to
CPU/VRAM/bandwidth reservations, finite GPU execution, lifecycle, replica-count
and action-budget limits. The implementation approximates:

```
J = priority × mean(completion_estimate/deadline + risk_proxy)
  + 0.35 × per-service CPU/VRAM pool reservation fraction
  + 0.25 × lifecycle_overhead/(deadline × virtual_batch_size)
```

The risk and normalized-delay coefficients are fixed at one. Resource/lifecycle
weights reuse existing headroom/overhead parameters. No weights or criteria are
tuned on seeds 1–30. Resource accounting retains temporary double reservations
for migration, through the unchanged physical engine.


# Experimental Setup

The same five-node, 20-service, 100×0.1-s verified scenario uses seeds 1–30. There are 270 comparative runs: 120 verified baseline runs reused read-only and 150 newly simulated runs across five routing policies. Each policy has exactly 30 common traffic tapes. Static/Reactive/Periodic are retained for context; no capacity sweep or new workload is run.

All admitted requests drain after arrivals end. All-offered failures retain the existing denominator; no new admission control is introduced. Request quantiles use completed end-to-end request latencies. The slot mean remains a separate preserved metric. Policy means and 95% percentile bootstrap CIs use seeds as units with 10,000 reproducible resamples. Main Holm family=12, ablation family=8. No parameters were tuned after main outcomes.

# SLA Results

| Policy | SLA failures (%) | Request mean (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|
| SLA-aware | 56.87 [54.16, 59.61] | 296.37 [239.94, 361.81] | 1315.17 [1032.23, 1632.42] | 2198.83 [1726.62, 2727.53] |
| SLA-aware+RR | 58.21 [55.78, 60.66] | 330.36 [272.10, 403.30] | 1432.30 [1165.29, 1727.35] | 2372.98 [1914.34, 2910.20] |
| SLA-aware+ShortestQueue | 57.12 [54.42, 59.79] | 299.75 [236.15, 382.35] | 1320.08 [998.71, 1718.39] | 2131.62 [1605.00, 2784.41] |
| JointSLA | 50.91 [47.76, 54.10] | 209.54 [162.83, 265.57] | 877.26 [634.04, 1177.44] | 1634.22 [1171.95, 2217.55] |

# Mean and Tail Latency

Latency includes service waiting, node-resource waiting, network, CPU→GPU→CPU execution and lifecycle penalties. Per-run p95/p99 are request-level quantiles, then averaged across seeds; no quantiles of slot means or pooled cross-seed requests are reported.

| Metric vs SLA-aware | Relative improvement (%) [95% CI] | Absolute reduction [95% CI] |
|---|---:|---:|
| SLA failure | 10.48 [8.05, 12.92] | 5.96 [4.60, 7.29] |
| Request mean latency | 29.30 [21.05, 37.76] | 86.83 [58.26, 116.71] |
| p95 latency | 33.30 [21.12, 45.78] | 437.91 [268.09, 633.56] |
| p99 latency | 25.68 [12.76, 38.72] | 564.60 [285.85, 846.24] |

SLA absolute reductions are percentage points; latency reductions are ms. Positive means JointSLA is better.

# Per-Tier Results

| Policy | Gold failure (%) | Silver failure (%) | Bronze failure (%) |
|---|---:|---:|---:|
| SLA-aware | 62.04 [58.41, 65.50] | 54.53 [50.71, 58.28] | 51.75 [47.40, 56.22] |
| SLA-aware+RR | 61.41 [58.16, 64.41] | 57.24 [53.56, 60.90] | 53.69 [49.10, 58.53] |
| SLA-aware+ShortestQueue | 61.01 [57.53, 64.40] | 55.12 [51.42, 58.71] | 53.18 [49.04, 57.58] |
| JointSLA | 61.96 [58.99, 64.80] | 48.71 [44.38, 52.99] | 39.36 [34.99, 44.14] |

# Routing Behavior

Only eligible active replicas receive assignments. When none exists, requests wait; cold or migrating instances do not receive new work. Waiting requests can be reassigned on readiness/migration, but in-flight requests remain on their original worker. Every successful choice records observable candidates and scores.

| Policy | Away from min network (%) | Differs from no-queue score (%) | Multi-eligible (%) |
|---|---:|---:|---:|
| SLA-aware+RR | 15.17 [13.71, 16.63] | 17.45 [15.79, 19.12] | 32.46 [29.52, 35.59] |
| SLA-aware+ShortestQueue | 13.98 [12.66, 15.30] | 17.17 [15.56, 18.85] | 33.94 [30.60, 37.15] |
| JointSLA | 10.84 [9.98, 11.68] | 11.87 [10.97, 12.73] | 31.23 [29.12, 33.28] |

These fractions use the first successful assignment per request. The no-queue alternative is a same-state score counterfactual, not a simulated alternate outcome. For RR/SQ it does not establish that queue awareness caused the difference. Replica request-count CV includes idle allocated instances; replica lifetimes differ and the distribution is descriptive. Full counts are in replica_request_distribution.csv.

# Resource Cost

| Policy | Avg replicas | VRAM residency (%) | Cold starts | Migrations | Actions |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 27.09 [26.49, 27.73] | 94.34 [93.89, 94.79] | 29.07 [25.27, 32.97] | 0.10 [0.00, 0.27] | 51.07 [43.67, 58.60] |
| SLA-aware+RR | 27.24 [26.62, 27.88] | 94.59 [94.14, 94.99] | 26.97 [23.13, 30.90] | 0.10 [0.00, 0.20] | 46.43 [39.17, 53.77] |
| SLA-aware+ShortestQueue | 27.08 [26.44, 27.75] | 94.40 [93.90, 94.86] | 28.30 [23.97, 32.87] | 0.23 [0.00, 0.70] | 49.43 [41.17, 57.93] |
| JointSLA | 25.93 [25.53, 26.31] | 91.18 [89.93, 92.35] | 25.20 [21.43, 28.90] | 0.00 [0.00, 0.00] | 44.00 [36.53, 51.50] |

| Policy | Scale-outs | Scale-ins | Sampled peak replicas | CPU busy (%) | GPU busy (%) |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 29.07 [25.23, 33.07] | 21.90 [18.40, 25.70] | 28.37 [27.63, 29.17] | 10.07 [9.82, 10.33] | 47.00 [45.20, 48.85] |
| SLA-aware+RR | 26.97 [23.20, 30.83] | 19.37 [16.00, 22.87] | 28.43 [27.67, 29.17] | 10.00 [9.74, 10.26] | 46.66 [44.81, 48.54] |
| SLA-aware+ShortestQueue | 28.30 [23.97, 32.77] | 20.90 [17.13, 24.93] | 28.27 [27.43, 29.10] | 10.05 [9.80, 10.30] | 46.94 [45.05, 48.86] |
| JointSLA | 25.20 [21.57, 28.93] | 18.80 [15.10, 22.63] | 27.93 [27.33, 28.50] | 10.22 [9.97, 10.48] | 47.15 [45.25, 49.12] |

Resource-normalized ratios are exploratory ratios of mean improvement to additional resources/actions. A nonpositive denominator yields an explicitly undefined ratio; it is not replaced with infinity or an invented efficiency value. Comparable measured resources alone cannot prove resource-independent causality. See resource_normalized_analysis.csv.

JointSLA versus SLA-aware: replica increase 95% CI -5.81% to -2.87%; VRAM residency increase CI -4.27 to -2.16 percentage points.

# Controller Overhead

Legacy decision time measures policy computation and action application, excluding snapshots. The new instrumented total also includes control-start snapshot construction. Historical baseline snapshot time is unavailable; zero new-router fields in baseline rows denote no explicit added routing mechanism, not a timing measurement of shared-FIFO dispatch.

| Policy | Legacy decision mean (ms) |
|---|---:|
| SLA-aware | 0.3435 [0.3244, 0.3617] |
| SLA-aware+RR | 0.8231 [0.7247, 0.9171] |
| SLA-aware+ShortestQueue | 0.7797 [0.6843, 0.8742] |
| JointSLA | 2.1231 [1.8814, 2.3578] |

| Policy | Total incl. snapshot (ms) | Routing mean (ms) | Routing p95 (ms) |
|---|---:|---:|---:|
| SLA-aware+RR | 1.08 [0.96, 1.19] | 0.0812 [0.0717, 0.0903] | 0.1479 [0.1308, 0.1652] |
| SLA-aware+ShortestQueue | 1.02 [0.90, 1.13] | 0.0787 [0.0694, 0.0876] | 0.1345 [0.1190, 0.1499] |
| JointSLA | 6.29 [5.53, 7.02] | 0.0764 [0.0674, 0.0851] | 0.1310 [0.1154, 0.1470] |

Routing times include failed eligibility attempts and observational counterfactual selection but exclude audit JSON serialization. Reassignment can make multiple decisions per request. The overhead is measured wall time, not added to simulated request delay. H5 uses mean full controller time and the mean of per-seed routing-attempt p95 values. These are local instrumented measurements, not hardware profiling.

# Statistical Significance

Two-sided paired Wilcoxon tests assess signed differences around zero, subject to independent seed pairs and symmetry/location assumptions. Mean difference bootstrap CIs provide complementary estimates. Significant benefit requires Holm p<0.05, positive mean reduction and a positive lower mean-difference CI.

| Comparator | Metric | Raw p | Holm p | Rank-biserial | Supported improvement |
|---|---|---:|---:|---:|---|
| SLA-aware | SLA failure | 3.54e-08 | 3.19e-07 | 0.9699 | yes |
| SLA-aware | Request mean latency | 1.42e-06 | 5.99e-06 | 0.8968 | yes |
| SLA-aware | p95 latency | 6.92e-06 | 2.08e-05 | 0.8538 | yes |
| SLA-aware | p99 latency | 0.000345 | 0.000345 | 0.7118 | yes |
| SLA-aware+RR | SLA failure | 5.59e-09 | 6.15e-08 | 0.9914 | yes |
| SLA-aware+RR | Request mean latency | 1.86e-09 | 2.24e-08 | 1.0000 | yes |
| SLA-aware+RR | p95 latency | 5.59e-09 | 6.15e-08 | 0.9914 | yes |
| SLA-aware+RR | p99 latency | 8.01e-08 | 6.41e-07 | 0.9570 | yes |
| SLA-aware+ShortestQueue | SLA failure | 1.64e-07 | 1.15e-06 | 0.9441 | yes |
| SLA-aware+ShortestQueue | Request mean latency | 9.98e-07 | 5.99e-06 | 0.9054 | yes |
| SLA-aware+ShortestQueue | p95 latency | 9.98e-07 | 5.99e-06 | 0.9054 | yes |
| SLA-aware+ShortestQueue | p99 latency | 0.000153 | 0.000306 | 0.7462 | yes |

Exploratory fast-routing ablations (separate Holm family):

| Ablation comparator | Metric | Relative improvement (%) | Holm p |
|---|---|---:|---:|
| JointSLA-no-queue | SLA failure | 13.86 | 1.49e-08 |
| JointSLA-no-queue | Request mean latency | 27.76 | 1.3e-07 |
| JointSLA-no-queue | p95 latency | 26.59 | 7.15e-06 |
| JointSLA-no-queue | p99 latency | 20.09 | 0.0233 |
| JointSLA-no-slack | SLA failure | 0.54 | 1 |
| JointSLA-no-slack | Request mean latency | -3.98 | 1 |
| JointSLA-no-slack | p95 latency | -1.71 | 1 |
| JointSLA-no-slack | p99 latency | -5.71 | 1 |

Full JointSLA shows supported benefit on 4/4 metrics versus the no-queue ablation, and 0/4 versus the no-slack ablation. The latter provides no evidence that the added variance/slack risk ranking improves on queue-aware predicted completion in this experiment. Feedback-dependent deployments prevent pure fixed-placement attribution.

# Wins / Ties / Losses

| Comparator | Metric | Wins | Ties | Losses |
|---|---|---:|---:|---:|
| SLA-aware | SLA failure | 28 | 0 | 2 |
| SLA-aware | Request mean latency | 27 | 0 | 3 |
| SLA-aware | p95 latency | 25 | 0 | 5 |
| SLA-aware | p99 latency | 25 | 0 | 5 |
| SLA-aware+RR | SLA failure | 29 | 0 | 1 |
| SLA-aware+RR | Request mean latency | 30 | 0 | 0 |
| SLA-aware+RR | p95 latency | 29 | 0 | 1 |
| SLA-aware+RR | p99 latency | 28 | 0 | 2 |
| SLA-aware+ShortestQueue | SLA failure | 27 | 0 | 3 |
| SLA-aware+ShortestQueue | Request mean latency | 24 | 0 | 6 |
| SLA-aware+ShortestQueue | p95 latency | 26 | 0 | 4 |
| SLA-aware+ShortestQueue | p99 latency | 24 | 0 | 6 |

# Negative Results

Every non-winning main comparison is retained:

| Seed | Comparator | Metric | Outcome | Baseline value | JointSLA value |
|---:|---|---|---|---:|---:|
| 15 | SLA-aware | SLA failure | loss | 0.538778 | 0.542893 |
| 22 | SLA-aware | SLA failure | loss | 0.614416 | 0.641014 |
| 7 | SLA-aware | Request mean latency | loss | 213.383282 | 263.348068 |
| 22 | SLA-aware | Request mean latency | loss | 357.766082 | 412.291477 |
| 30 | SLA-aware | Request mean latency | loss | 153.253094 | 154.676011 |
| 6 | SLA-aware | p95 latency | loss | 3857.271936 | 3879.868567 |
| 7 | SLA-aware | p95 latency | loss | 844.426057 | 1253.065435 |
| 8 | SLA-aware | p95 latency | loss | 1039.251743 | 1168.925850 |
| 22 | SLA-aware | p95 latency | loss | 1992.514308 | 2136.130678 |
| 30 | SLA-aware | p95 latency | loss | 604.854173 | 611.465134 |
| 6 | SLA-aware | p99 latency | loss | 5377.702356 | 6033.041568 |
| 7 | SLA-aware | p99 latency | loss | 1444.176705 | 2560.985150 |
| 8 | SLA-aware | p99 latency | loss | 1382.480600 | 1681.044197 |
| 12 | SLA-aware | p99 latency | loss | 6600.308434 | 6779.354536 |
| 22 | SLA-aware | p99 latency | loss | 2821.120883 | 3083.471055 |
| 22 | SLA-aware+RR | SLA failure | loss | 0.636135 | 0.641014 |
| 6 | SLA-aware+RR | p95 latency | loss | 3832.697601 | 3879.868567 |
| 6 | SLA-aware+RR | p99 latency | loss | 5965.570017 | 6033.041568 |
| 12 | SLA-aware+RR | p99 latency | loss | 6597.826174 | 6779.354536 |
| 8 | SLA-aware+ShortestQueue | SLA failure | loss | 0.545316 | 0.563578 |
| 11 | SLA-aware+ShortestQueue | SLA failure | loss | 0.608902 | 0.615019 |
| 23 | SLA-aware+ShortestQueue | SLA failure | loss | 0.456788 | 0.496995 |
| 7 | SLA-aware+ShortestQueue | Request mean latency | loss | 257.486657 | 263.348068 |
| 8 | SLA-aware+ShortestQueue | Request mean latency | loss | 245.205139 | 255.569233 |
| 11 | SLA-aware+ShortestQueue | Request mean latency | loss | 233.144392 | 246.956921 |
| 22 | SLA-aware+ShortestQueue | Request mean latency | loss | 396.625902 | 412.291477 |
| 23 | SLA-aware+ShortestQueue | Request mean latency | loss | 121.786021 | 128.200857 |
| 28 | SLA-aware+ShortestQueue | Request mean latency | loss | 202.707903 | 216.129726 |
| 7 | SLA-aware+ShortestQueue | p95 latency | loss | 1135.917652 | 1253.065435 |
| 8 | SLA-aware+ShortestQueue | p95 latency | loss | 991.586764 | 1168.925850 |
| 22 | SLA-aware+ShortestQueue | p95 latency | loss | 1957.501781 | 2136.130678 |
| 28 | SLA-aware+ShortestQueue | p95 latency | loss | 703.791791 | 816.146941 |
| 7 | SLA-aware+ShortestQueue | p99 latency | loss | 2493.133719 | 2560.985150 |
| 8 | SLA-aware+ShortestQueue | p99 latency | loss | 1478.185965 | 1681.044197 |
| 11 | SLA-aware+ShortestQueue | p99 latency | loss | 1311.947658 | 2447.681098 |
| 12 | SLA-aware+ShortestQueue | p99 latency | loss | 6639.230299 | 6779.354536 |
| 22 | SLA-aware+ShortestQueue | p99 latency | loss | 2896.364064 | 3083.471055 |
| 28 | SLA-aware+ShortestQueue | p99 latency | loss | 995.651705 | 1236.154792 |

# Interpretation

Predeclared overall decision: **supports additional coupled value in this model**.

| Hypothesis | Supported under its predeclared rule |
|---|---|
| H1 | yes |
| H2 | yes |
| H3 | yes |
| H4 | yes |
| H5 | yes |

The overall SLA mean is 50.91%; this experiment does not achieve the earlier <15% aspiration. Gold failures remain 62.04% versus 61.96% for JointSLA; aggregate benefit must not be presented as an established Gold-tier benefit. Per-tier rows are descriptive and are not covered by the primary significance family.

This strengthens the empirical case for a coupled deployment/routing contribution within this synthetic model. It does not by itself establish publication readiness or first-in-literature novelty, and it does not establish additional benefit from the SLA/slack risk term.

H1/H2 require statistically supported improvements over SLA-aware. H3 uses supported improvement or its predeclared descriptive 5% noninferiority margin. H4 also requires comparable-resource bounds (replicas <=5% increase, VRAM <=2pp). H5 screens 10-ms control and 1-ms routing budgets. Failing any rule does not trigger retuning.

Possible mechanisms must be treated as hypotheses: per-replica pinned queues can add head-of-line waiting relative to the already work-conserving central FIFO; network cost, scarce replica residency and conservative lifecycle/uncertainty proxies may limit routing gain. Routing baselines and ablations constrain interpretation, but do not isolate every mechanism. Negative outcomes are retained.

# Threats to Validity

- Synthetic uncalibrated workloads and service timings; one verified configuration, no scalability or real-hardware study.
- Baseline is shared-FIFO pull scheduling; new policies introduce explicit queues. Routing-only baselines use the same deployment function but feedback-dependent actions can differ.
- Variance/slack and node waiting estimates are uncalibrated proxies; no global optimization or probabilistic deadline guarantee is established.
- Queue/slack ablations affect subsequent feedback and deployment; they are exploratory and not pure replay with fixed placements.
- Requests awaiting eligibility are retained. Mean/tail latency uses completed requests; all-offered SLA failures preserve accounting. Replica peaks remain slot-sampled.
- Observed memory/resources and diagnostic ratios do not isolate a causal resource effect or universal efficiency metric.
- Seed-level CIs are pointwise and finite-sample; model uncertainty and Wilcoxon assumptions remain. Previously inspected baseline seeds are not independent external validation.
- Old/new wall-clock timing scopes differ for snapshots; new instrumentation includes counterfactual ranking and excludes audit serialization. Computational overhead is not injected into simulated request latency.

# Safe Paper Claims

- The experiment preserves identical traffic tapes and the verified physical model while evaluating explicit online routing and coupled deployment.
- JointSLA reduced sla failure by 10.48% relative to existing SLA-aware across 30 paired synthetic workloads (Holm p=3.19e-07).
- JointSLA reduced request mean latency by 29.30% relative to existing SLA-aware across 30 paired synthetic workloads (Holm p=5.99e-06).
- JointSLA reduced p95 latency by 33.30% relative to existing SLA-aware across 30 paired synthetic workloads (Holm p=2.08e-05).
- JointSLA reduced p99 latency by 25.68% relative to existing SLA-aware across 30 paired synthetic workloads (Holm p=0.000345).

# Claims We Cannot Make

- Globally optimal, first-ever coupled edge orchestrator, or production-ready telco controller.
- A calibrated SLA-risk probability, general superiority, or benefits isolated exclusively to queue awareness.
- Free improvement at identical resource cost, significance where Holm p>=0.05, or success when H1–H5 criteria fail.

Reproduce with `python run_joint_routing.py --seeds 1:30 --reuse-results`; use `--force` to rerun only the new policies. Baseline artifacts are protected by before/after hashes.
