# Research Question

Does the verified JointSLA preserve its advantage over SLA-aware as edge nodes, services, requests and routing decisions increase proportionally?

# Verified JointSLA Baseline

The verified five-node/20-service experiment found SLA failures 56.87% versus 50.91%, mean latency 296.37 versus 209.54 ms, p95 1315.17 versus 877.26 ms and p99 2198.83 versus 1634.22 ms. This study imports its policy and score unchanged, protects both verified output trees and reruns SMALL to establish timing-only instrumentation identity. All SMALL performance/resource metrics agree with the verified values.

# Scalability Methodology

Three policies (SLA-aware, JointSLA, SLA-aware+ShortestQueue) × three scales × seeds 1–30 give 270 freshly simulated main runs. A separate 27-run pilot preceded them. Every scale/seed uses one common hashed traffic tape. No tuning, future traffic, new pipeline, capacity distribution, traffic regime or thresholds are introduced. No optional stress or Static experiment was run.

The fixed generator distributions and algorithm parameters scale only node/service counts. Policy parameters include the SAME two-action budget per 100-ms slot, three-replica limit and cooldown; therefore control opportunities per service decrease with system size. This is an algorithmic bottleneck to investigate, not an increase in exogenous offered pressure. CPU→GPU→CPU stages remain colocated.

All offered requests are counted, including unplaced/drop failures; admitted requests drain after the ten-second arrival horizon. Request means and within-run p95/p99 use completed requests. requests_processed_per_slot denotes completed arrival-cohort volume/T including drain; requests_completed_within_horizon_per_slot separately measures actual completions within T. CIs use 10,000 seed-level bootstrap resamples. Main Holm family=12 across all scales/four metrics; SQ uses a separate 12-test family. Relative improvements are ratios of paired scale-level means.

# Scale-Preserving Configuration

Per-seed evidence is in scale_configuration_summary.csv and the fixed consistency screens in scale_consistency_checks.csv. These screen 30-seed distributional means within 15%, tier fractions within 4pp; they do not establish exact per-seed difficulty equivalence. GPU compute demand is one execution unit for 10 ms; VRAM residency is a distinct resource.

| Scale | Services/node | Requests/service | CPU offered pressure | GPU offered pressure | Initial VRAM pressure | Gold/Silver/Bronze (%) | Burst slots (%) | Mean deadline (ms) |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| SMALL | 4 | 294.09 | 0.1037 | 0.4769 | 0.7189 | 35.00/35.00/30.00 | 22.31 | 85.75 |
| MEDIUM | 4 | 292.19 | 0.1013 | 0.4670 | 0.7226 | 35.00/32.50/32.50 | 22.36 | 86.75 |
| LARGE | 4 | 290.95 | 0.1006 | 0.4660 | 0.7198 | 33.75/33.75/32.50 | 22.59 | 86.87 |

# Small Results

Means [95% CI of seed-level mean]:

| Policy | SLA failure (%) | Mean (ms) | Median (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 56.87 [54.12, 59.59] | 296.37 [240.95, 362.64] | 99.52 [87.08, 114.07] | 1315.17 [1032.94, 1627.86] | 2198.83 [1735.27, 2734.24] |
| JointSLA | 50.91 [47.67, 54.02] | 209.54 [162.85, 264.15] | 80.39 [72.49, 88.76] | 877.26 [635.85, 1183.09] | 1634.22 [1170.75, 2206.47] |
| SLA-aware+ShortestQueue | 57.12 [54.50, 59.76] | 299.75 [235.90, 381.72] | 103.56 [88.36, 123.25] | 1320.08 [996.67, 1722.32] | 2131.62 [1599.85, 2776.31] |

# Medium Results

Means [95% CI of seed-level mean]:

| Policy | SLA failure (%) | Mean (ms) | Median (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 59.72 [57.42, 61.96] | 296.89 [256.68, 343.49] | 108.89 [97.20, 121.69] | 1197.69 [1025.72, 1400.28] | 2354.14 [1893.40, 2905.70] |
| JointSLA | 54.91 [52.48, 57.48] | 221.95 [185.10, 267.72] | 94.33 [83.07, 108.57] | 871.31 [708.62, 1060.63] | 1622.58 [1273.91, 2008.12] |
| SLA-aware+ShortestQueue | 61.36 [59.06, 63.62] | 322.85 [279.47, 371.42] | 116.06 [104.05, 129.32] | 1330.67 [1134.96, 1547.59] | 2476.98 [2028.83, 2980.36] |

# Large Results

Means [95% CI of seed-level mean]:

| Policy | SLA failure (%) | Mean (ms) | Median (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 61.50 [60.05, 62.86] | 331.54 [301.03, 364.82] | 113.50 [105.57, 121.59] | 1434.21 [1280.88, 1606.29] | 2602.19 [2264.25, 2988.03] |
| JointSLA | 56.71 [55.10, 58.39] | 240.14 [214.42, 269.90] | 94.75 [88.66, 101.34] | 1006.89 [873.60, 1159.14] | 1820.91 [1553.66, 2142.68] |
| SLA-aware+ShortestQueue | 62.66 [61.54, 63.73] | 360.04 [326.75, 398.06] | 118.29 [111.47, 125.60] | 1552.61 [1372.72, 1770.71] | 2951.97 [2584.53, 3352.06] |

# SLA Generalization

| Scale | SLA relative gain (%) [95% CI] | Absolute reduction (pp) [95% CI] | Holm p | Wins/ties/losses |
|---|---:|---:|---:|---|
| SMALL | 10.48 [8.09, 12.92] | 5.96 [4.64, 7.27] | 2.48e-07 | 28/0/2 |
| MEDIUM | 8.06 [6.33, 9.74] | 4.82 [3.80, 5.81] | 8.38e-08 | 29/0/1 |
| LARGE | 7.79 [6.43, 9.22] | 4.79 [3.94, 5.67] | 2.24e-08 | 30/0/0 |

# Mean and Tail Latency

All p95/p99 are computed from raw end-to-end request outcomes within runs, then summarized across seeds. No quantiles of slot averages or pooled cross-seed requests are used.

| Scale | Metric | Relative gain (%) [95% CI] | Absolute reduction (ms) [95% CI] |
|---|---|---:|---:|
| SMALL | Mean request latency | 29.30 [20.98, 37.56] | 86.83 [59.22, 116.98] |
| SMALL | p95 latency | 33.30 [21.32, 45.32] | 437.91 [265.43, 632.08] |
| SMALL | p99 latency | 25.68 [13.11, 38.75] | 564.60 [290.08, 849.67] |
| MEDIUM | Mean request latency | 25.24 [17.02, 33.23] | 74.94 [49.10, 101.03] |
| MEDIUM | p95 latency | 27.25 [17.09, 36.21] | 326.39 [201.84, 449.27] |
| MEDIUM | p99 latency | 31.08 [15.65, 46.09] | 731.56 [331.54, 1240.91] |
| LARGE | Mean request latency | 27.57 [24.25, 30.71] | 91.40 [79.31, 102.88] |
| LARGE | p95 latency | 29.80 [25.48, 34.16] | 427.33 [359.15, 494.62] |
| LARGE | p99 latency | 30.02 [23.65, 35.85] | 781.29 [592.32, 985.23] |

# Per-Tier Generalization

Tier means are descriptive; no per-tier significance claim is drawn from the primary test family.

SMALL:

| Policy | Gold failures (%) | Silver failures (%) | Bronze failures (%) |
|---|---:|---:|---:|
| SLA-aware | 62.04 [58.53, 65.58] | 54.53 [50.60, 58.20] | 51.75 [47.46, 56.09] |
| JointSLA | 61.96 [59.00, 64.84] | 48.71 [44.30, 53.02] | 39.36 [34.91, 44.12] |
| SLA-aware+ShortestQueue | 61.01 [57.63, 64.41] | 55.12 [51.36, 58.81] | 53.18 [49.05, 57.68] |

MEDIUM:

| Policy | Gold failures (%) | Silver failures (%) | Bronze failures (%) |
|---|---:|---:|---:|
| SLA-aware | 63.07 [60.35, 65.81] | 59.14 [56.88, 61.46] | 56.50 [53.51, 59.40] |
| JointSLA | 64.67 [62.15, 67.03] | 53.84 [51.13, 56.69] | 45.10 [41.30, 49.12] |
| SLA-aware+ShortestQueue | 63.25 [60.90, 65.62] | 61.72 [59.19, 64.23] | 58.57 [54.95, 62.13] |

LARGE:

| Policy | Gold failures (%) | Silver failures (%) | Bronze failures (%) |
|---|---:|---:|---:|
| SLA-aware | 60.38 [58.81, 61.97] | 59.40 [57.34, 61.40] | 64.44 [62.32, 66.47] |
| JointSLA | 63.36 [61.78, 65.00] | 54.28 [52.30, 56.47] | 52.10 [49.18, 55.07] |
| SLA-aware+ShortestQueue | 61.44 [59.91, 62.98] | 61.16 [59.42, 62.80] | 65.12 [63.16, 67.03] |

# Resource Scaling

Means [95% CI]; GPU busy time and VRAM residency are distinct. Allocated replicas include cold/retiring instances; eligible counts are slot-end sampled. The controller cannot exceed 200 accepted actions during the 100-slot horizon. Normalized actions can decrease mechanically as request counts grow; this alone is not evidence of efficiency.

Routing diagnostics:

SMALL:

| Policy | Successful assignments | Differs from no-queue score (%) | Multi-eligible requests (%) |
|---|---:|---:|---:|
| JointSLA | 6173.4333 [6004.3642, 6335.3033] | 11.87 [10.98, 12.74] | 31.23 [29.10, 33.25] |
| SLA-aware+ShortestQueue | 6144.1000 [5980.1308, 6307.7675] | 17.17 [15.52, 18.85] | 33.94 [30.72, 37.22] |

| Policy | All-allocated replica request CV | Sampled eligible replicas | Requests / avg eligible replica |
|---|---:|---:|---:|
| SLA-aware | 0.50 [0.44, 0.55] | 26.80 [26.23, 27.39] | 220.33 [212.10, 228.69] |
| JointSLA | 0.53 [0.45, 0.60] | 25.67 [25.27, 26.04] | 229.29 [222.65, 236.21] |
| SLA-aware+ShortestQueue | 0.53 [0.46, 0.60] | 26.80 [26.19, 27.40] | 220.50 [211.90, 229.43] |

MEDIUM:

| Policy | Successful assignments | Differs from no-queue score (%) | Multi-eligible requests (%) |
|---|---:|---:|---:|
| JointSLA | 12195.9000 [11951.6000, 12422.9017] | 13.31 [12.38, 14.19] | 34.22 [31.64, 36.61] |
| SLA-aware+ShortestQueue | 12205.4000 [11956.5317, 12440.7708] | 18.11 [16.71, 19.45] | 34.76 [32.09, 37.17] |

| Policy | All-allocated replica request CV | Sampled eligible replicas | Requests / avg eligible replica |
|---|---:|---:|---:|
| SLA-aware | 0.37 [0.34, 0.39] | 54.14 [53.04, 55.21] | 216.51 [210.94, 222.27] |
| JointSLA | 0.43 [0.39, 0.48] | 52.52 [51.58, 53.43] | 222.97 [217.71, 228.33] |
| SLA-aware+ShortestQueue | 0.38 [0.34, 0.41] | 54.36 [53.23, 55.43] | 215.73 [209.71, 221.91] |

LARGE:

| Policy | Successful assignments | Differs from no-queue score (%) | Multi-eligible requests (%) |
|---|---:|---:|---:|
| JointSLA | 24216.2000 [23925.8425, 24517.4100] | 14.80 [14.18, 15.40] | 37.88 [35.99, 39.71] |
| SLA-aware+ShortestQueue | 24295.8667 [24005.7633, 24589.1425] | 18.06 [17.24, 18.85] | 34.37 [32.88, 35.80] |

| Policy | All-allocated replica request CV | Sampled eligible replicas | Requests / avg eligible replica |
|---|---:|---:|---:|
| SLA-aware | 0.25 [0.24, 0.26] | 108.00 [106.67, 109.36] | 215.72 [212.47, 219.13] |
| JointSLA | 0.31 [0.29, 0.32] | 106.76 [105.45, 108.08] | 218.21 [215.03, 221.52] |
| SLA-aware+ShortestQueue | 0.26 [0.25, 0.27] | 108.07 [106.86, 109.28] | 215.54 [212.37, 218.74] |

The observed imbalance includes all allocated/retired IDs and unused replicas for every policy, reconstructed from initial creation order and scale-out actions. Unequal lifetimes make it descriptive. Queue-change fractions describe first assignments under a same-state score counterfactual, not a causal effect. The preserved legacy baseline router-only CV sentinel is separate from the newly observed replica_load_imbalance_cv field.

SMALL:

| Policy | Avg replicas | Sampled peak | Replicas/service | VRAM (%) | Cold starts | Migrations | Actions |
|---|---:|---:|---:|---:|---:|---:|---:|
| SLA-aware | 27.09 [26.48, 27.72] | 28.37 [27.60, 29.13] | 1.35 [1.32, 1.39] | 94.34 [93.88, 94.79] | 29.07 [25.27, 33.07] | 0.10 [0.00, 0.27] | 51.07 [43.67, 58.60] |
| JointSLA | 25.93 [25.53, 26.30] | 27.93 [27.33, 28.50] | 1.30 [1.28, 1.32] | 91.18 [89.93, 92.34] | 25.20 [21.47, 28.83] | 0.00 [0.00, 0.00] | 44.00 [36.63, 51.53] |
| SLA-aware+ShortestQueue | 27.08 [26.44, 27.76] | 28.27 [27.47, 29.10] | 1.35 [1.32, 1.39] | 94.40 [93.90, 94.86] | 28.30 [23.93, 32.83] | 0.23 [0.00, 0.70] | 49.43 [41.20, 58.13] |

| Policy | Scale-outs | Scale-ins | CPU busy (%) | GPU busy (%) | Actions/1000 requests |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 29.07 [25.17, 33.07] | 21.90 [18.50, 25.60] | 10.07 [9.82, 10.34] | 47.00 [45.21, 48.82] | 8.87 [7.51, 10.32] |
| JointSLA | 25.20 [21.47, 28.90] | 18.80 [15.07, 22.67] | 10.22 [9.96, 10.48] | 47.15 [45.26, 49.09] | 7.67 [6.30, 9.04] |
| SLA-aware+ShortestQueue | 28.30 [23.97, 32.77] | 20.90 [17.13, 24.80] | 10.05 [9.80, 10.30] | 46.94 [45.08, 48.82] | 8.62 [7.06, 10.25] |

MEDIUM:

| Policy | Avg replicas | Sampled peak | Replicas/service | VRAM (%) | Cold starts | Migrations | Actions |
|---|---:|---:|---:|---:|---:|---:|---:|
| SLA-aware | 54.59 [53.42, 55.65] | 56.53 [55.17, 57.77] | 1.36 [1.34, 1.39] | 95.04 [94.66, 95.38] | 44.27 [40.47, 47.83] | 0.30 [0.03, 0.67] | 74.27 [67.80, 80.67] |
| JointSLA | 52.94 [51.97, 53.87] | 55.67 [54.43, 56.87] | 1.32 [1.30, 1.35] | 93.36 [92.73, 93.95] | 41.70 [37.37, 46.00] | 0.07 [0.00, 0.17] | 69.33 [61.40, 76.93] |
| SLA-aware+ShortestQueue | 54.78 [53.60, 55.88] | 56.60 [55.23, 57.93] | 1.37 [1.34, 1.40] | 95.35 [94.95, 95.72] | 42.27 [38.13, 46.20] | 0.20 [0.03, 0.40] | 69.53 [62.33, 76.43] |

| Policy | Scale-outs | Scale-ins | CPU busy (%) | GPU busy (%) | Actions/1000 requests |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 44.27 [40.40, 47.77] | 29.70 [26.80, 32.47] | 9.83 [9.56, 10.10] | 46.43 [45.39, 47.48] | 6.40 [5.77, 6.99] |
| JointSLA | 41.70 [37.33, 45.87] | 27.57 [24.00, 30.93] | 9.94 [9.65, 10.21] | 46.54 [45.52, 47.54] | 5.97 [5.27, 6.64] |
| SLA-aware+ShortestQueue | 42.27 [38.17, 46.27] | 27.07 [23.73, 30.37] | 9.79 [9.51, 10.05] | 46.24 [45.22, 47.29] | 5.98 [5.32, 6.61] |

LARGE:

| Policy | Avg replicas | Sampled peak | Replicas/service | VRAM (%) | Cold starts | Migrations | Actions |
|---|---:|---:|---:|---:|---:|---:|---:|
| SLA-aware | 108.65 [107.27, 110.01] | 112.83 [111.17, 114.47] | 1.36 [1.34, 1.38] | 94.91 [94.67, 95.15] | 64.10 [61.80, 66.40] | 0.40 [0.13, 0.73] | 97.67 [94.10, 101.13] |
| JointSLA | 107.38 [106.07, 108.71] | 112.07 [110.40, 113.73] | 1.34 [1.33, 1.36] | 93.99 [93.71, 94.28] | 62.23 [59.10, 65.30] | 0.03 [0.00, 0.10] | 94.23 [89.27, 99.13] |
| SLA-aware+ShortestQueue | 108.71 [107.48, 109.93] | 112.97 [111.40, 114.47] | 1.36 [1.34, 1.37] | 94.88 [94.64, 95.12] | 62.83 [60.40, 65.17] | 0.53 [0.23, 0.93] | 94.53 [90.87, 98.10] |

| Policy | Scale-outs | Scale-ins | CPU busy (%) | GPU busy (%) | Actions/1000 requests |
|---|---:|---:|---:|---:|---:|
| SLA-aware | 64.10 [61.77, 66.33] | 33.17 [31.67, 34.53] | 9.77 [9.61, 9.94] | 46.14 [45.54, 46.75] | 4.21 [4.03, 4.37] |
| JointSLA | 62.23 [59.13, 65.23] | 31.97 [29.77, 34.10] | 9.91 [9.74, 10.08] | 46.40 [45.81, 47.03] | 4.06 [3.82, 4.29] |
| SLA-aware+ShortestQueue | 62.83 [60.37, 65.17] | 31.17 [29.83, 32.53] | 9.72 [9.56, 9.89] | 45.96 [45.37, 46.56] | 4.07 [3.90, 4.24] |

Paired resource differences (JointSLA minus SLA-aware; positive = additional cost):

| Scale | Metric | Difference [95% CI] |
|---|---|---:|
| SMALL | average_replicas | -1.17 [-1.59, -0.76] |
| SMALL | mean_gpu_vram_reserved_pct | -3.16 [-4.26, -2.18] |
| SMALL | cold_starts | -3.87 [-5.67, -2.17] |
| SMALL | total_actions | -7.07 [-10.80, -3.60] |
| SMALL | migrations | -0.10 [-0.27, 0.00] |
| MEDIUM | average_replicas | -1.65 [-2.05, -1.26] |
| MEDIUM | mean_gpu_vram_reserved_pct | -1.68 [-2.16, -1.26] |
| MEDIUM | cold_starts | -2.57 [-4.60, -0.47] |
| MEDIUM | total_actions | -4.93 [-8.97, -0.73] |
| MEDIUM | migrations | -0.23 [-0.60, 0.03] |
| LARGE | average_replicas | -1.26 [-1.85, -0.70] |
| LARGE | mean_gpu_vram_reserved_pct | -0.92 [-1.10, -0.74] |
| LARGE | cold_starts | -1.87 [-3.47, -0.23] |
| LARGE | total_actions | -3.43 [-6.50, -0.33] |
| LARGE | migrations | -0.37 [-0.70, -0.10] |

Relative counter/resource intervals are explicitly undefined when any bootstrap baseline mean is zero (notably rare migrations). All absolute differences/CIs remain available; no resamples are dropped.

# Controller Overhead Scaling

All policies were freshly instrumented, including baseline snapshot time. Process CPU time is the sum of control-start snapshot, policy, action application and explicit routing dispatch CPU; nested routing inside migration application is subtracted from control-only CPU to avoid double counting. Dispatch CPU includes audit creation; the verified routing wall timer excludes JSON. Windows process CPU timers can be quantized, and sampled RSS covers the entire process. Timing is not injected into simulated latency. It does not establish a production hardware budget.

SMALL:

| Policy | Policy/apply mean ms | Policy/apply p95 ms | Full control mean ms | Full control p95 ms |
|---|---:|---:|---:|---:|
| SLA-aware | 0.3037 [0.2825, 0.3256] | 0.4510 [0.4198, 0.4837] | 0.32 [0.30, 0.34] | 0.47 [0.43, 0.50] |
| JointSLA | 0.8752 [0.8272, 0.9256] | 1.2826 [1.2026, 1.3622] | 2.52 [2.37, 2.68] | 3.12 [2.92, 3.31] |
| SLA-aware+ShortestQueue | 0.3112 [0.2910, 0.3330] | 0.4684 [0.4348, 0.5056] | 0.42 [0.40, 0.44] | 0.58 [0.55, 0.62] |

| Policy | Routing mean ms | Routing p95 ms |
|---|---:|---:|
| JointSLA | 0.0313 [0.0297, 0.0330] | 0.0508 [0.0474, 0.0544] |
| SLA-aware+ShortestQueue | 0.0308 [0.0292, 0.0325] | 0.0502 [0.0475, 0.0531] |

| Policy | Wall seconds/run | Seconds/100k requests | Controller CPU ms/run | Controller CPU ms/request |
|---|---:|---:|---:|---:|
| SLA-aware | 0.27 [0.25, 0.29] | 4.59 [4.34, 4.85] | 31.25 [23.96, 39.06] | 0.01 [0.00, 0.01] |
| JointSLA | 0.85 [0.81, 0.90] | 14.49 [13.83, 15.21] | 526.04 [493.75, 559.38] | 0.09 [0.08, 0.10] |
| SLA-aware+ShortestQueue | 0.63 [0.60, 0.66] | 10.75 [10.29, 11.25] | 293.23 [271.86, 315.10] | 0.05 [0.05, 0.05] |

MEDIUM:

| Policy | Policy/apply mean ms | Policy/apply p95 ms | Full control mean ms | Full control p95 ms |
|---|---:|---:|---:|---:|
| SLA-aware | 0.8891 [0.8556, 0.9295] | 1.3012 [1.2280, 1.3806] | 0.91 [0.88, 0.95] | 1.33 [1.25, 1.40] |
| JointSLA | 1.7718 [1.7121, 1.8412] | 2.7565 [2.6173, 2.9025] | 6.93 [6.67, 7.24] | 8.60 [8.13, 9.13] |
| SLA-aware+ShortestQueue | 0.9521 [0.9088, 1.0017] | 1.4054 [1.3022, 1.5301] | 1.25 [1.20, 1.31] | 1.72 [1.62, 1.84] |

| Policy | Routing mean ms | Routing p95 ms |
|---|---:|---:|
| JointSLA | 0.0302 [0.0290, 0.0315] | 0.0476 [0.0452, 0.0503] |
| SLA-aware+ShortestQueue | 0.0303 [0.0291, 0.0318] | 0.0500 [0.0473, 0.0530] |

| Policy | Wall seconds/run | Seconds/100k requests | Controller CPU ms/run | Controller CPU ms/request |
|---|---:|---:|---:|---:|
| SLA-aware | 0.55 [0.53, 0.57] | 4.68 [4.55, 4.83] | 83.85 [70.83, 96.88] | 0.01 [0.01, 0.01] |
| JointSLA | 1.85 [1.79, 1.93] | 15.86 [15.35, 16.47] | 1186.98 [1134.38, 1241.67] | 0.10 [0.10, 0.11] |
| SLA-aware+ShortestQueue | 1.29 [1.24, 1.34] | 11.01 [10.67, 11.39] | 640.62 [607.29, 675.00] | 0.05 [0.05, 0.06] |

LARGE:

| Policy | Policy/apply mean ms | Policy/apply p95 ms | Full control mean ms | Full control p95 ms |
|---|---:|---:|---:|---:|
| SLA-aware | 4.1464 [3.8557, 4.4379] | 8.0193 [7.1357, 8.9278] | 4.19 [3.90, 4.48] | 8.06 [7.19, 8.99] |
| JointSLA | 4.5084 [4.2272, 4.7949] | 8.0745 [7.5807, 8.5701] | 26.84 [25.37, 28.30] | 33.50 [31.44, 35.47] |
| SLA-aware+ShortestQueue | 4.3689 [4.0722, 4.6647] | 8.2699 [7.3662, 9.2532] | 5.34 [5.02, 5.65] | 9.00 [8.13, 9.97] |

| Policy | Routing mean ms | Routing p95 ms |
|---|---:|---:|
| JointSLA | 0.0365 [0.0350, 0.0381] | 0.0579 [0.0551, 0.0608] |
| SLA-aware+ShortestQueue | 0.0362 [0.0345, 0.0379] | 0.0611 [0.0575, 0.0648] |

| Policy | Wall seconds/run | Seconds/100k requests | Controller CPU ms/run | Controller CPU ms/request |
|---|---:|---:|---:|---:|
| SLA-aware | 1.48 [1.40, 1.55] | 6.33 [6.04, 6.62] | 417.71 [376.04, 458.85] | 0.02 [0.02, 0.02] |
| JointSLA | 5.41 [5.16, 5.65] | 23.22 [22.24, 24.22] | 3813.54 [3607.80, 4016.16] | 0.16 [0.16, 0.17] |
| SLA-aware+ShortestQueue | 3.23 [3.09, 3.38] | 13.89 [13.32, 14.44] | 1713.54 [1609.90, 1815.62] | 0.07 [0.07, 0.08] |

controller_overhead_scaling.csv contains nodes, services, mean eligible replicas, requests and routing decisions. Baseline has no explicit routing timer; its zero router fields denote absence of the added mechanism, not measured cost of its shared-FIFO scheduler. Controller CPU/explicit routing-decision is explicitly undefined for baseline. Fits are descriptive: nodes/services are perfectly collinear and per-service candidate count is capped at three, so no asymptotic complexity proof follows.

# Negative Seeds

No outlier or loss seed was removed. Positive difference below means JointSLA is worse (the negative-case export retains comparator-minus-JointSLA sign).

| Scale | Seed | Metric | SLA-aware | JointSLA | Joint minus baseline |
|---|---:|---|---:|---:|---:|
| SMALL | 15 | SLA failure | 0.538778 | 0.542893 | 0.004115 |
| SMALL | 22 | SLA failure | 0.614416 | 0.641014 | 0.026597 |
| SMALL | 7 | Mean request latency | 213.383282 | 263.348068 | 49.964786 |
| SMALL | 22 | Mean request latency | 357.766082 | 412.291477 | 54.525395 |
| SMALL | 30 | Mean request latency | 153.253094 | 154.676011 | 1.422917 |
| SMALL | 6 | p95 latency | 3857.271936 | 3879.868567 | 22.596631 |
| SMALL | 7 | p95 latency | 844.426057 | 1253.065435 | 408.639378 |
| SMALL | 8 | p95 latency | 1039.251743 | 1168.925850 | 129.674107 |
| SMALL | 22 | p95 latency | 1992.514308 | 2136.130678 | 143.616370 |
| SMALL | 30 | p95 latency | 604.854173 | 611.465134 | 6.610961 |
| SMALL | 6 | p99 latency | 5377.702356 | 6033.041568 | 655.339213 |
| SMALL | 7 | p99 latency | 1444.176705 | 2560.985150 | 1116.808445 |
| SMALL | 8 | p99 latency | 1382.480600 | 1681.044197 | 298.563597 |
| SMALL | 12 | p99 latency | 6600.308434 | 6779.354536 | 179.046102 |
| SMALL | 22 | p99 latency | 2821.120883 | 3083.471055 | 262.350172 |
| MEDIUM | 3 | SLA failure | 0.737338 | 0.743786 | 0.006448 |
| MEDIUM | 1 | Mean request latency | 312.702999 | 440.613757 | 127.910758 |
| MEDIUM | 4 | Mean request latency | 315.140194 | 337.304920 | 22.164726 |
| MEDIUM | 1 | p95 latency | 1234.020068 | 1966.219882 | 732.199814 |
| MEDIUM | 4 | p95 latency | 1209.866108 | 1483.211187 | 273.345079 |
| MEDIUM | 1 | p99 latency | 1786.529050 | 3679.950599 | 1893.421550 |
| MEDIUM | 4 | p99 latency | 3147.705504 | 3351.536674 | 203.831170 |
| MEDIUM | 16 | p99 latency | 2795.572031 | 2832.881935 | 37.309904 |
| MEDIUM | 21 | p99 latency | 1724.802908 | 1825.950527 | 101.147618 |
| LARGE | 12 | p99 latency | 1612.590334 | 1931.145783 | 318.555449 |

# Statistical Significance

Two-sided paired Wilcoxon assumes independent seed pairs and a suitable signed-difference distribution; bootstrap mean CIs complement the location test. Supported benefit requires positive mean, positive lower paired CI and Holm p<0.05.

| Scale | Metric | Raw p | Holm p | Rank-biserial | Wins/ties/losses | Supported |
|---|---|---:|---:|---:|---|---|
| SMALL | SLA failure | 3.54e-08 | 2.48e-07 | 0.9699 | 28/0/2 | yes |
| SMALL | Mean request latency | 1.42e-06 | 8.52e-06 | 0.8968 | 27/0/3 | yes |
| SMALL | p95 latency | 6.92e-06 | 2.77e-05 | 0.8538 | 25/0/5 | yes |
| SMALL | p99 latency | 0.000345 | 0.000345 | 0.7118 | 25/0/5 | yes |
| MEDIUM | SLA failure | 9.31e-09 | 8.38e-08 | 0.9871 | 29/0/1 | yes |
| MEDIUM | Mean request latency | 2.76e-06 | 1.38e-05 | 0.8796 | 28/0/2 | yes |
| MEDIUM | p95 latency | 1.06e-05 | 3.18e-05 | 0.8409 | 28/0/2 | yes |
| MEDIUM | p99 latency | 2.08e-05 | 4.16e-05 | 0.8194 | 26/0/4 | yes |
| LARGE | SLA failure | 1.86e-09 | 2.24e-08 | 1.0000 | 30/0/0 | yes |
| LARGE | Mean request latency | 1.86e-09 | 2.24e-08 | 1.0000 | 30/0/0 | yes |
| LARGE | p95 latency | 1.86e-09 | 2.24e-08 | 1.0000 | 30/0/0 | yes |
| LARGE | p99 latency | 2.61e-08 | 2.09e-07 | 0.9742 | 29/0/1 | yes |

Secondary ShortestQueue comparisons (separate 12-test Holm family):

| Scale | Metric | Relative gain (%) | Holm p | Supported |
|---|---|---:|---:|---|
| SMALL | SLA failure | 10.87 | 1.15e-06 | yes |
| SMALL | Mean request latency | 30.10 | 3.99e-06 | yes |
| SMALL | p95 latency | 33.55 | 3.99e-06 | yes |
| SMALL | p99 latency | 23.33 | 0.000153 | yes |
| MEDIUM | SLA failure | 10.51 | 7.45e-08 | yes |
| MEDIUM | Mean request latency | 31.25 | 2.31e-06 | yes |
| MEDIUM | p95 latency | 34.52 | 3.46e-06 | yes |
| MEDIUM | p99 latency | 34.49 | 5.38e-05 | yes |
| LARGE | SLA failure | 9.49 | 2.24e-08 | yes |
| LARGE | Mean request latency | 33.30 | 2.24e-08 | yes |
| LARGE | p95 latency | 35.15 | 2.24e-08 | yes |
| LARGE | p99 latency | 38.32 | 2.24e-08 | yes |

# Does the JointSLA Advantage Persist?

| Hypothesis | Predeclared rule supported |
|---|---|
| H1 | yes |
| H2 | yes |
| H3 | yes |
| H4 | no |
| H5 | yes |

H1/H2 require SLA/p95 benefit at all scales. H3 requires both at >=2 scales plus nonnegative LARGE means and <=15 loss seeds. H4 requires mean full control <=10ms, mean per-seed control p95 <=100ms and routing p95 <=1ms at every scale. H5 requires upper paired bounds for replicas <=5%, VRAM <=2pp and normalized actions <=5%. These separate performance persistence from computational feasibility and comparable resources.

| Scale | Full controller mean (ms) | Mean seed control p95 (ms) | Mean seed routing p95 (ms) | H4 scale screen |
|---|---:|---:|---:|---|
| SMALL | 2.517 | 3.115 | 0.051 | pass |
| MEDIUM | 6.933 | 8.603 | 0.048 | pass |
| LARGE | 26.836 | 33.496 | 0.058 | fail |

Relative gain is compared directly across scales in joint_relative_gain_by_scale.csv. A positive statistically supported LARGE result does not imply unchanged magnitude or linear scaling. If gain diminishes or budgets fail, fixed action budget, full node/service snapshot construction, queue-estimation error, scarce VRAM and lifecycle bottlenecks are plausible mechanisms, not identified causal explanations.

Observed mean-gain movement (descriptive; no additional trend significance test):

| Metric | SMALL relative gain (%) | MEDIUM relative gain (%) | LARGE relative gain (%) | LARGE minus SMALL (pp) |
|---|---:|---:|---:|---:|
| SLA failure | 10.48 | 8.06 | 7.79 | -2.69 |
| Mean request latency | 29.30 | 25.24 | 27.57 | -1.73 |
| p95 latency | 33.30 | 27.25 | 29.80 | -3.50 |
| p99 latency | 25.68 | 31.08 | 30.02 | 4.35 |

# Threats to Validity

- One synthetic model and horizon; no real workloads, hardware profiling, carrier-scale network or external-validation seeds.
- Independent size-dependent topology/service draws preserve distributions, not identical per-seed instances or exact offered pressure. Tier rounding changes fractions slightly.
- Two actions/slot is global and fixed; resource residency/action bottlenecks may intensify as service count rises.
- Original SLA-aware uses a work-conserving shared FIFO; explicit queues and feedback-dependent deployments differ. Benefit cannot be attributed solely to one routing term.
- The prior no-slack ablation did not establish an additional variance/slack benefit. This study does not change or rehabilitate that claim.
- Latency includes after-horizon drain, while utilization/residency measure the arrival horizon. Eligible and peak replicas are sampled; allocated replica-seconds are exact.
- Wall time includes online audit creation; exports/validation are excluded. Process CPU quantization, monitoring, filesystem and shared-machine activity limit timing interpretation.
- Per-scale confidence intervals are pointwise; the fixed main Holm family controls 12 primary tests. Trends/fits/resources are diagnostic, not causal/asymptotic proofs.

# Safe Paper Claims

- The unchanged verified mechanisms were evaluated on common hashed tapes at three proportional scales, with protected baseline artifacts and no post-outcome tuning.
- At SMALL, JointSLA reduced sla failure by 10.48% relative to SLA-aware across 30 paired synthetic workloads (Holm p=2.48e-07).
- At SMALL, JointSLA reduced mean request latency by 29.30% relative to SLA-aware across 30 paired synthetic workloads (Holm p=8.52e-06).
- At SMALL, JointSLA reduced p95 latency by 33.30% relative to SLA-aware across 30 paired synthetic workloads (Holm p=2.77e-05).
- At SMALL, JointSLA reduced p99 latency by 25.68% relative to SLA-aware across 30 paired synthetic workloads (Holm p=0.000345).
- At MEDIUM, JointSLA reduced sla failure by 8.06% relative to SLA-aware across 30 paired synthetic workloads (Holm p=8.38e-08).
- At MEDIUM, JointSLA reduced mean request latency by 25.24% relative to SLA-aware across 30 paired synthetic workloads (Holm p=1.38e-05).
- At MEDIUM, JointSLA reduced p95 latency by 27.25% relative to SLA-aware across 30 paired synthetic workloads (Holm p=3.18e-05).
- At MEDIUM, JointSLA reduced p99 latency by 31.08% relative to SLA-aware across 30 paired synthetic workloads (Holm p=4.16e-05).
- At LARGE, JointSLA reduced sla failure by 7.79% relative to SLA-aware across 30 paired synthetic workloads (Holm p=2.24e-08).
- At LARGE, JointSLA reduced mean request latency by 27.57% relative to SLA-aware across 30 paired synthetic workloads (Holm p=2.24e-08).
- At LARGE, JointSLA reduced p95 latency by 29.80% relative to SLA-aware across 30 paired synthetic workloads (Holm p=2.24e-08).
- At LARGE, JointSLA reduced p99 latency by 30.02% relative to SLA-aware across 30 paired synthetic workloads (Holm p=2.09e-07).
- JointSLA preserved statistically supported reductions in all four primary metrics over SLA-aware across all tested synthetic system scales.

# Claims We Cannot Make

- Production scalable, carrier-grade, globally optimal, real-world validated or linearly scalable.
- Constant gain magnitude, universal resource efficiency, calibrated SLA-risk probability, or additional slack-term benefit without supporting evidence.
- Acceptable computational overhead at a scale that fails the predeclared H4 budget.

# Implications for B-Level Publication

Performance generalization screen H3 is supported; operational overhead screen H4 is not supported; resource fairness H5 is supported. Positive persistence strengthens empirical evidence for the coupled mechanism in this model. Failed budgets, loss seeds or shrinking gains qualify that evidence; they are not hidden or repaired by tuning. Publication readiness and first-in-literature novelty still require broader evaluation and independently verified literature positioning.

Reproduce: `python run_scalability_experiments.py --seeds 1:30 --reuse-results`; rerun with `--force`. Pilot uses `--pilot`. All detailed exports are local to the new scalability directory.
