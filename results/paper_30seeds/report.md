# Experimental Setup

Research question: under identical dynamic AI-edge workloads, does the existing SLA-aware policy reduce SLA violations and latency relative to Static, Reactive and Periodic, and at what resource/reconfiguration cost?

The main experiment uses seeds 1–30: 30 independent generated workloads and 120 successful seed-policy runs. Each has 5 heterogeneous nodes, 20 services and 100 slots of 0.1 s. Every policy receives the same immutable workload, traffic tape and initial greedy placement within its seed. Existing simulator, policy, traffic and SLA parameters are unchanged. Controllers receive past/current snapshots only.

All offered arrival cohorts are retained and admitted requests drain after the arrival horizon. Drops and unplaced requests remain failures. Rates in CSV are fractions unless the legacy name ends in `_pct`; displayed rates are percentages. Each seed, not each request or slot, is the statistical replication unit.

Mean confidence intervals use 10,000 percentile bootstrap resamples of complete seeds at 95% confidence, with fixed root RNG seed 73001 and stable keyed substreams. Paired differences and ratios of means resample aligned policy pairs. Intervals are pointwise, not simultaneous. Wilcoxon tests are two-sided; primary inference uses Holm correction across all 12 baseline/metric comparisons. Zero differences are excluded; differences are rounded to 12 decimals for ranks. Exact p-values are used only without zeros/tied magnitudes; otherwise a tie-corrected asymptotic method is disclosed.

# Main Results

Values are mean [95% bootstrap CI of the mean] across seeds.

| Policy | SLA failure (%) | Request mean (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|
| Static | 71.99 [69.93, 73.96] | 841.44 [732.10, 960.88] | 3591.45 [3176.43, 4040.86] | 5438.35 [4834.67, 6059.39] |
| Reactive | 70.97 [68.75, 73.03] | 824.14 [717.49, 939.41] | 3550.69 [3144.50, 3989.76] | 5404.98 [4817.12, 6046.13] |
| Periodic | 72.36 [70.29, 74.24] | 846.62 [744.19, 960.05] | 3626.16 [3202.76, 4067.22] | 5433.76 [4837.84, 6042.25] |
| SLA-aware | 56.87 [54.16, 59.61] | 296.37 [239.94, 361.81] | 1315.17 [1032.23, 1632.42] | 2198.83 [1726.62, 2727.53] |

# SLA Compliance

The all-offered rate counts deadline violations and admission failures. Lower values are better. Relative improvements below are ratios of policy means, not averages of per-seed percentages.

| Baseline | Absolute reduction (percentage points) | Relative reduction (%) [95% CI] | Wins / ties / losses |
|---|---:|---:|---:|
| Static | 15.12 | 21.01 [17.98, 24.23] | 30/0/0 |
| Reactive | 14.10 | 19.87 [16.73, 23.17] | 30/0/0 |
| Periodic | 15.49 | 21.41 [18.41, 24.66] | 30/0/0 |

# Latency

Request latency is service queue waiting + node resource waiting + network delay + CPU preprocessing + GPU inference + CPU postprocessing + lifecycle penalty. The request mean weights all completed requests equally within a seed. The preserved slot mean weights nonempty arrival-slot request means equally. Neither invents latency for dropped/unplaced requests; counts and failures disclose that selection.

| Policy | Request mean (ms) | Slot mean (ms) |
|---|---:|---:|
| Static | 841.44 [732.10, 960.88] | 799.50 [691.09, 919.23] |
| Reactive | 824.14 [717.49, 939.41] | 781.43 [679.79, 893.34] |
| Periodic | 846.62 [744.19, 960.05] | 804.76 [701.82, 919.39] |
| SLA-aware | 296.37 [239.94, 361.81] | 270.72 [216.79, 335.14] |

# Tail Latency

Median, p95 and p99 use NumPy linear quantiles of every completed request's actual end-to-end latency within a run, including late completions. The main table and figures show the mean of 30 per-run quantiles, with CIs across seeds. These are neither pooled-request quantiles nor quantiles of slot averages.

# Per-Tier Analysis

Each tier uses its own offered-request denominator, rather than equal weighting of services.

| Policy | Gold failure (%) | Silver failure (%) | Bronze failure (%) |
|---|---:|---:|---:|
| Static | 81.49 [78.75, 84.13] | 70.19 [66.61, 73.68] | 60.85 [55.73, 65.77] |
| Reactive | 80.29 [77.23, 83.07] | 69.32 [65.71, 72.84] | 59.81 [54.52, 65.12] |
| Periodic | 81.49 [78.70, 84.01] | 70.72 [66.88, 74.19] | 61.38 [56.23, 66.39] |
| SLA-aware | 62.04 [58.41, 65.50] | 54.53 [50.71, 58.28] | 51.75 [47.40, 56.22] |

# Statistical Significance

The signed-rank test assesses whether paired differences are consistent with a distribution symmetric about zero; it is not a direct test of mean equality. Independent seed generation and a defensible symmetry/location interpretation are assumptions. Bootstrap mean-difference CIs provide a separate estimate of average benefit. A supported improvement requires Holm-adjusted p <0.05, positive mean improvement and a positive lower paired mean-difference CI.

| Baseline | Metric | Wilcoxon W | p (raw) | p (Holm) | Method | Supported improvement |
|---|---|---:|---:|---:|---|---|
| Static | SLA breach rate | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Static | Mean request latency | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Static | p95 latency | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Static | p99 latency | 0 | 2.56e-06 | 5.13e-06 | asymptotic | yes |
| Reactive | SLA breach rate | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Reactive | Mean request latency | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Reactive | p95 latency | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Reactive | p99 latency | 0 | 2.56e-06 | 5.13e-06 | asymptotic | yes |
| Periodic | SLA breach rate | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Periodic | Mean request latency | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Periodic | p95 latency | 0 | 1.86e-09 | 2.24e-08 | exact | yes |
| Periodic | p99 latency | 1 | 3.73e-09 | 2.24e-08 | exact | yes |

# Effect Sizes

Matched-pairs rank-biserial correlation = (positive rank sum − negative rank sum) / total nonzero rank sum, where differences are baseline minus SLA-aware. +1 indicates all nonzero ranks favor SLA-aware; −1 favors the baseline. This is a directional paired effect size, not a percentage reduction.

| Baseline | Metric | Rank-biserial | Relative improvement (%) | Wins / ties / losses |
|---|---|---:|---:|---:|
| Static | SLA breach rate | 1.0000 | 21.01 | 30/0/0 |
| Static | Mean request latency | 1.0000 | 64.78 | 30/0/0 |
| Static | p95 latency | 1.0000 | 63.38 | 30/0/0 |
| Static | p99 latency | 1.0000 | 59.57 | 29/1/0 |
| Reactive | SLA breach rate | 1.0000 | 19.87 | 30/0/0 |
| Reactive | Mean request latency | 1.0000 | 64.04 | 30/0/0 |
| Reactive | p95 latency | 1.0000 | 62.96 | 30/0/0 |
| Reactive | p99 latency | 1.0000 | 59.32 | 29/1/0 |
| Periodic | SLA breach rate | 1.0000 | 21.41 | 30/0/0 |
| Periodic | Mean request latency | 1.0000 | 64.99 | 30/0/0 |
| Periodic | p95 latency | 1.0000 | 63.73 | 30/0/0 |
| Periodic | p99 latency | 0.9957 | 59.53 | 29/0/1 |

All non-winning primary observations:

| Seed | Baseline | Metric | Outcome | Baseline value | SLA-aware value |
|---:|---|---|---|---:|---:|
| 13 | Static | p99 latency | tie | 3644.053864 | 3644.053864 |
| 13 | Reactive | p99 latency | tie | 3644.053864 | 3644.053864 |
| 13 | Periodic | p99 latency | loss | 3578.646011 | 3644.053864 |

# Reconfiguration Costs

Average allocated replicas is the exact replica-seconds integral divided by the arrival horizon, including cold replicas. Peak replicas is sampled at slot ends plus the initial allocation; it is not an event-level transient peak. Accepted actions and actual cold-start events are counted separately. Downtime is the sum of triggered replica downtime, not elapsed system-wide outage.

| Policy | Scale-outs | Scale-ins | Migrations | Cold starts | Average replicas |
|---|---:|---:|---:|---:|---:|
| Static | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 20.00 [20.00, 20.00] |
| Reactive | 2.77 [1.93, 3.67] | 1.53 [0.93, 2.20] | 0.00 [0.00, 0.00] | 2.77 [1.97, 3.63] | 20.89 [20.63, 21.17] |
| Periodic | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 1.27 [0.63, 2.00] | 0.00 [0.00, 0.00] | 20.00 [20.00, 20.00] |
| SLA-aware | 29.07 [25.23, 33.07] | 21.90 [18.40, 25.70] | 0.10 [0.00, 0.27] | 29.07 [25.27, 32.97] | 27.09 [26.49, 27.73] |

| Policy | Replica-seconds | VRAM GB-seconds | Decision runtime (ms) |
|---|---:|---:|---:|
| Static | 200.00 [200.00, 200.00] | 898.28 [877.69, 918.72] | 0.0010 [0.0010, 0.0011] |
| Reactive | 208.87 [206.30, 211.73] | 926.34 [904.07, 947.24] | 0.0487 [0.0456, 0.0521] |
| Periodic | 200.00 [200.00, 200.00] | 898.32 [877.55, 918.63] | 0.0042 [0.0037, 0.0048] |
| SLA-aware | 270.93 [264.86, 277.33] | 1179.83 [1160.06, 1199.66] | 0.3435 [0.3245, 0.3616] |

Higher SLA-aware cost metrics (descriptive; not additional primary significance tests):

- Versus Static: `total_actions` rises from 0.000 to 51.067.
- Versus Static: `scale_outs` rises from 0.000 to 29.067.
- Versus Static: `scale_ins` rises from 0.000 to 21.900.
- Versus Static: `cold_starts` rises from 0.000 to 29.067.
- Versus Static: `average_replicas` rises from 20.000 to 27.093.
- Versus Static: `replica_seconds` rises from 200.000 to 270.930.
- Versus Static: `vram_gb_seconds` rises from 898.277 to 1179.828.
- Versus Static: `triggered_downtime_seconds` rises from 0.000 to 2.917.
- Versus Static: `decision_runtime_mean_ms` rises from 0.001 to 0.344.
- Versus Reactive: `total_actions` rises from 4.300 to 51.067.
- Versus Reactive: `scale_outs` rises from 2.767 to 29.067.
- Versus Reactive: `scale_ins` rises from 1.533 to 21.900.
- Versus Reactive: `cold_starts` rises from 2.767 to 29.067.
- Versus Reactive: `average_replicas` rises from 20.887 to 27.093.
- Versus Reactive: `replica_seconds` rises from 208.870 to 270.930.
- Versus Reactive: `vram_gb_seconds` rises from 926.339 to 1179.828.
- Versus Reactive: `triggered_downtime_seconds` rises from 0.277 to 2.917.
- Versus Reactive: `decision_runtime_mean_ms` rises from 0.049 to 0.344.
- Versus Periodic: `total_actions` rises from 1.267 to 51.067.
- Versus Periodic: `scale_outs` rises from 0.000 to 29.067.
- Versus Periodic: `scale_ins` rises from 0.000 to 21.900.
- Versus Periodic: `cold_starts` rises from 0.000 to 29.067.
- Versus Periodic: `average_replicas` rises from 20.000 to 27.093.
- Versus Periodic: `replica_seconds` rises from 200.000 to 270.930.
- Versus Periodic: `vram_gb_seconds` rises from 898.323 to 1179.828.
- Versus Periodic: `triggered_downtime_seconds` rises from 0.127 to 2.917.
- Versus Periodic: `decision_runtime_mean_ms` rises from 0.004 to 0.344.

CPU/GPU utilization averages give equal weight to node-slots over the arrival horizon, then to seeds. Weighted-pool alternatives are exported. Higher busy utilization is not automatically a performance regression; it may shift work out of the post-horizon drain. Reserved VRAM and GPU compute busy time are distinct.

| Policy | CPU busy (%) | GPU busy (%) | VRAM residency (%) |
|---|---:|---:|---:|
| Static | 9.25 [9.00, 9.50] | 43.36 [41.52, 45.26] | 72.11 [70.31, 73.81] |
| Reactive | 9.27 [9.02, 9.53] | 43.52 [41.59, 45.46] | 74.60 [72.60, 76.54] |
| Periodic | 9.24 [8.99, 9.50] | 43.03 [41.25, 44.83] | 71.90 [70.16, 73.58] |
| SLA-aware | 10.07 [9.82, 10.33] | 47.00 [45.20, 48.85] | 94.34 [93.89, 94.79] |

# Capacity Analysis

Existing verified capacity runs are reused: 30 paired seeds 0–29 at each of 5–10 nodes. The unchanged heuristic operates on nested topology pools; initial greedy placement adapts to the pool. These results do not isolate GPU capacity from topology/initial-placement changes. Supplemental workloads share 29 seeds with the main run and are not an independent replication.

| Nodes | SLA failure (%) [95% CI] | Request mean latency (ms) [95% CI] |
|---:|---:|---:|
| 5 | 57.19 [54.53, 59.89] | 299.23 [244.37, 362.83] |
| 6 | 44.49 [41.75, 47.43] | 149.20 [129.03, 175.93] |
| 7 | 34.88 [32.03, 38.13] | 96.26 [86.73, 108.01] |
| 8 | 27.97 [25.59, 30.40] | 70.75 [65.22, 76.31] |
| 9 | 23.19 [21.58, 24.79] | 58.59 [55.52, 61.81] |
| 10 | 21.08 [19.69, 22.54] | 53.06 [51.14, 55.08] |

The lowest observed mean is 21.08% at 10 nodes. The <15% mean target is not met. These CIs quantify seed variability and do not establish an exact physical inflection.

# Admission Control

Existing seeds 0–29 are reused without modifying admission control. All-offered failures include drops; conditional admitted rates cannot establish success alone.

| Case | All-offered failure (%) [95% CI] | Drop (%) [95% CI] | Gold/Silver failure (%) [95% CI] |
|---|---:|---:|---:|
| baseline | 57.19 [54.53, 59.90] | 0.00 [0.00, 0.00] | 59.00 [55.98, 61.96] |
| admission | 53.77 [51.15, 56.41] | 5.13 [4.27, 6.06] | 57.19 [53.81, 60.57] |

Admission's conditional admitted breach rate is 51.30 [48.62, 53.98]%; Bronze drop rate is 16.85 [14.34, 19.48]%. Gold and Silver have no administrative drops in these records.

# Prewarming

Existing prewarming all-offered failure is 57.36 [54.60, 60.12]%, compared with 57.19 [54.53, 59.90]% for its paired baseline. This configuration does not demonstrate a lower mean failure rate. The ten-slot moving-average predictor learns burst phase from past observations and uses the configured period; it does not predict individual Poisson arrivals.

Cold starts: baseline 28.70 [24.87, 32.63], prewarming 29.20 [25.30, 33.27]. Accepted prewarm actions: 1.67 [1.23, 2.10]. Negative results are retained. Supplemental comparisons are exploratory.

# Main Findings

- The SLA-aware policy reduced sla breach rate by 21.01% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced mean request latency by 64.78% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p95 latency by 63.38% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p99 latency by 59.57% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=5.13e-06).
- The SLA-aware policy reduced sla breach rate by 19.87% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced mean request latency by 64.04% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p95 latency by 62.96% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p99 latency by 59.32% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=5.13e-06).
- The SLA-aware policy reduced sla breach rate by 21.41% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced mean request latency by 64.99% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p95 latency by 63.73% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p99 latency by 59.53% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).

The corresponding per-seed outcomes and complete cost tradeoffs remain visible; aggregate improvements do not imply every seed or metric improves.

# Limitations

- Synthetic, uncalibrated workload and service throughput; one default operating configuration and finite seed count.
- This is retrospective statistical evaluation of an existing heuristic, not a preregistered independent confirmatory study; 29 main seeds overlap previous experiments.
- Gold/Silver/Bronze priorities and deadlines vary together, so tier comparisons do not isolate priority alone.
- Service components remain colocated; FIFO queues and serial replica pipelines constrain throughput. No real network, GPU interference, failures or deployed telco system is tested.
- Static/Periodic do not scale; the proposed method may use more replicas and memory. Comparisons assess full policy behavior, not equal-resource algorithm efficiency.
- Bootstrap intervals describe means across generated seeds; n=30 does not guarantee nominal coverage for heavy tails. They are pointwise and do not include model uncertainty.
- Wilcoxon assumes independent seed pairs and a symmetry/location interpretation; it does not prove mean equality, causal mechanisms or real-world generalization.
- p95/p99 are averages of per-run completed-request quantiles. Completion selection, all-offered failure and drop counts must be read together.
- Utilization covers arrival slots only; latency includes drained requests. Runtime is machine-dependent and not a production benchmark.
- Sampled replica peaks can miss transient within-slot peaks. Higher utilization is not by itself evidence of inefficiency.

## Safe Paper Claims

- The SLA-aware policy reduced sla breach rate by 21.01% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced mean request latency by 64.78% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p95 latency by 63.38% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p99 latency by 59.57% relative to Static across 30 paired synthetic workloads (Holm-adjusted p=5.13e-06).
- The SLA-aware policy reduced sla breach rate by 19.87% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced mean request latency by 64.04% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p95 latency by 62.96% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p99 latency by 59.32% relative to Reactive across 30 paired synthetic workloads (Holm-adjusted p=5.13e-06).
- The SLA-aware policy reduced sla breach rate by 21.41% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced mean request latency by 64.99% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p95 latency by 63.73% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).
- The SLA-aware policy reduced p99 latency by 59.53% relative to Periodic across 30 paired synthetic workloads (Holm-adjusted p=2.24e-08).

## Claims We Cannot Make

- First-ever SLA-aware edge orchestrator or established bibliographic novelty.
- Globally optimal placement, universal SLA guarantee or production-ready telco system.
- A mean SLA failure rate below 15% in the tested configurations.
- Improvement for every seed in every metric, free improvement at identical resource cost, or successful prewarming in this configuration.

## Reproducibility and Method References

Run `python run_paper_experiments.py --seeds 1:30`; use `--reuse-results` to analyze existing verified main outcomes, or `--force` for a full main rerun. Supplemental simulations are never rerun by this command. Install `requirements-paper.txt` first.

Statistical implementation follows [SciPy Wilcoxon documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html) and the [percentile bootstrap definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html). All empirical values come from CSVs in this output directory. `claim_ledger.csv` maps supported claims to comparison results; `validation.json` records independent checks.
