# Research Question

Does JointSLA retain a meaningful advantage against a substantially stronger optimization-based joint placement/routing comparator, under the same causal information and physical constraints? The primary comparison is JointSLA–MJO; MJO–SLA-aware is the baseline-strength sanity check. All outcome directions are retained.

# Frozen Verified Baseline

All four previous result trees and verified simulator/controller sources are protected by `protected_hashes.json`. Every new JointSLA run is compared exactly against nine historical scientific CSV families, excluding timing columns only. The optimized JointSLA implementation is inherited unchanged. Scientific SLA-aware measurements are reused for 90 verified runs; its timing measurements remain historical and are not evidence for the fresh primary overhead comparison.

# Strong Baseline Motivation

MJO is a literature-inspired constrained optimization comparator, not an exact reproduction of any published algorithm. It evaluates deployment options through the same current-backlog assignment cost and chooses resource-coupled actions. Its strength label is conditional on predeclared B1. No unsupported technical citations or empirical literature percentages are used. See `strong_baseline/LITERATURE_MAPPING.md`.

# Optimization Formulation

For each service, binary y[q,r,k] assigns each already-arrived waiting request to one ordered capacity slot k of an eligible replica r. Each 64-request block solves a rectangular linear assignment. Blocks process oldest-arrival/request-ID order and accumulate assignments. In-flight work is preserved; within-replica FIFO and physical workers are unchanged.

At a control instant, enumerate no-op, feasible scale-out, idle scale-in and migration menus. Recompute matching under each virtual deployment with cold/downtime availability delays. Binary z[s,a] selects at most one option per service and at most two globally, minimizing additive incremental costs subject to simultaneous reservation headroom. This is exact over the finite additive menu when completed. It does not optimize cross-service interference nonlinearly or the complete stochastic horizon.

# Information Available to the Controller

Current queues, already-arrived request ages, deadlines/priorities, replica lifecycle flags, reservations, CPU/GPU availability, network/bandwidth and completed-work empirical estimates. Identical lifecycle telemetry is added to the new wrappers of both primary policies and charged to observation time. No future arrivals, bursts, completions or hidden per-request work factor are read by optimization. Causality tests alter future traffic and future work without changing prefix decisions.

# Objective

For candidate slot: Q=(existing modeled queue + assignments + k)×observed cycle + remaining busy time; C=request age + availability delay + Q + network + CPU→GPU→CPU execution + observable resource waiting + lifecycle penalty. Routing cost = priority × [max(0,C/deadline−1) + C/deadline] + 0.25 Q/deadline. The convex lateness term is a surrogate, not a calibrated SLA breach probability. Allocation cost adds 0.35 × sum((CPU fraction + VRAM fraction)/2); scale/cold and migration costs add 0.25 × lifecycle delay/deadline. Scale-in has a fixed nominal execution-cost term.

# Constraints

Same finite CPU tokens, GPU compute scheduler, VRAM and bandwidth reservation limits; same max-three-replica/service limit, cooldown, two actions/slot and service compatibility. Cold, retiring and pending-migration replicas cannot receive committed routing. Positive instantaneous reservations are combined across chosen actions; no credit is borrowed from future removal/source release. GPU execution contention remains enforced by the unchanged physical scheduler. All offered requests have exactly one terminal outcome.

# Fixed Hyperparameters / Weights

Before pilot outcomes: SLA=1, latency=1, congestion=0.25, resource=0.35, cold/scale=0.25, migration=0.25; block size=64; deployment pair-work limit=50,000. No coefficient was tuned on pilot or final seeds. Operational competitive screen: upper paired-bootstrap deterioration ≤5% for SLA/tails, predeclared uniformly from the previous p99 tolerance. B5 bounds: replicas/actions +5%, VRAM +2 percentage points. These screens do not prove statistical equivalence. Frozen details: `baseline_configuration.json`.

# Solver

SciPy `linear_sum_assignment` (modified Jonker–Volgenant implementation) solves each matching block. A specialized deterministic budget-two integer enumeration with valid lower-bound pruning chooses deployment actions. 'Optimal' means exact for that finite subproblem, not globally optimal routing of all future requests. Pair-work limit exhaustion is recorded as timeout with deterministic no-op. Routing failure retains prior queued assignments and pending arrivals. There is no JointSLA fallback and no wall-clock decision cutoff.

# Pilot

27 policy runs (three seeds × three scales × three policies) plus nine repeated MJO runs. Corrected export pilot elapsed 4.12 min; maximum sampled RSS 400.5 MiB. All nine MJO semantic trace hashes repeated exactly. Printed estimates before main execution: SMALL: 1.41 min; MEDIUM: 3.38 min; LARGE: 7.17 min; total 11.96 min. Initial pilot export validation rejected nonexistent-node NaNs in the combined table; node profiles now remain in their actual-scale trajectories. Model/objective weights were unchanged.

# Correctness Validation

171 tests passed: the original 160 plus 11 new MJO tests. Full experiment: 180 fresh primary runs + 90 verified SLA-aware runs = 270 paired observations. Main replay/export wall time 19.89 min. Fresh runs account for 2,450,732 request outcomes. `validation.json` independently reconstructs all 270 request exports, components, reservations, lifecycle, tier metrics, batch costs, causal request ages, final routing and inference. Numeric reconstruction tolerances apply to derived sums/quantiles; frozen JointSLA scientific-frame comparison is exact. Causal timestamp comparisons allow 1e-12 seconds for cumulative SimPy floating arithmetic: an initial main attempt detected a 6.94e-18-second discrepancy already present in frozen SMALL seed 15. The guard was corrected and the pilot/main replay restarted; decisions, event timestamps and weights were unchanged. Tests do not prove safety for all possible workloads.

# Small Results

| Policy | SLA % | Mean ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- |
| SLA-aware | 56.87 ± 7.76 [54.12, 59.59] | 296.37 ± 173.71 [240.95, 362.64] | 1315.17 ± 854.36 [1032.94, 1627.86] | 2198.83 ± 1434.36 [1735.27, 2734.24] |
| MJO | 53.92 ± 7.14 [51.41, 56.40] | 255.89 ± 152.47 [207.99, 314.21] | 1190.90 ± 1029.62 [871.02, 1586.09] | 2123.88 ± 2041.77 [1502.49, 2926.31] |
| JointSLA | 50.91 ± 8.96 [47.67, 54.02] | 209.54 ± 146.69 [162.85, 264.15] | 877.26 ± 775.05 [635.85, 1183.09] | 1634.22 ± 1487.20 [1170.75, 2206.47] |

Cells: seed mean ± sample SD [95% bootstrap CI of mean].

# Medium Results

| Policy | SLA % | Mean ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- |
| SLA-aware | 59.72 ± 6.52 [57.42, 61.96] | 296.89 ± 123.58 [256.68, 343.49] | 1197.69 ± 534.28 [1025.72, 1400.28] | 2354.14 ± 1436.65 [1893.40, 2905.70] |
| MJO | 57.50 ± 6.93 [55.06, 59.96] | 253.83 ± 114.36 [216.84, 296.72] | 1007.79 ± 474.29 [854.93, 1190.78] | 1960.58 ± 1067.52 [1604.09, 2356.25] |
| JointSLA | 54.91 ± 7.19 [52.48, 57.48] | 221.95 ± 117.65 [185.10, 267.72] | 871.31 ± 503.99 [708.62, 1060.63] | 1622.58 ± 1051.79 [1273.91, 2008.12] |

Cells: seed mean ± sample SD [95% bootstrap CI of mean].

# Large Results

| Policy | SLA % | Mean ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- |
| SLA-aware | 61.50 ± 4.05 [60.05, 62.86] | 331.54 ± 90.92 [301.03, 364.82] | 1434.21 ± 461.19 [1280.88, 1606.29] | 2602.19 ± 1024.67 [2264.25, 2988.03] |
| MJO | 57.97 ± 4.20 [56.49, 59.43] | 227.35 ± 71.68 [203.97, 254.79] | 893.62 ± 383.12 [769.55, 1037.57] | 1538.91 ± 748.97 [1299.34, 1822.68] |
| JointSLA | 56.71 ± 4.64 [55.10, 58.39] | 240.14 ± 79.63 [214.42, 269.90] | 1006.89 ± 402.88 [873.60, 1159.14] | 1820.91 ± 826.64 [1553.66, 2142.68] |

Cells: seed mean ± sample SD [95% bootstrap CI of mean].

# SLA Comparison

| Scale | Policy | SLA breach % |
| --- | --- | --- |
| SMALL | SLA-aware | 56.87 ± 7.76 [54.12, 59.59] |
| SMALL | MJO | 53.92 ± 7.14 [51.41, 56.40] |
| SMALL | JointSLA | 50.91 ± 8.96 [47.67, 54.02] |
| MEDIUM | SLA-aware | 59.72 ± 6.52 [57.42, 61.96] |
| MEDIUM | MJO | 57.50 ± 6.93 [55.06, 59.96] |
| MEDIUM | JointSLA | 54.91 ± 7.19 [52.48, 57.48] |
| LARGE | SLA-aware | 61.50 ± 4.05 [60.05, 62.86] |
| LARGE | MJO | 57.97 ± 4.20 [56.49, 59.43] |
| LARGE | JointSLA | 56.71 ± 4.64 [55.10, 58.39] |

Every offered request is in the SLA denominator; failed placement/admission counts as breach. No policy admission/drop advantage is introduced.

# Mean / p95 / p99

| Scale | Policy | Mean ms | Median ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- | --- |
| SMALL | SLA-aware | 296.37 ± 173.71 [240.95, 362.64] | 99.52 ± 39.07 [87.08, 114.07] | 1315.17 ± 854.36 [1032.94, 1627.86] | 2198.83 ± 1434.36 [1735.27, 2734.24] |
| SMALL | MJO | 255.89 ± 152.47 [207.99, 314.21] | 86.16 ± 21.16 [78.74, 93.80] | 1190.90 ± 1029.62 [871.02, 1586.09] | 2123.88 ± 2041.77 [1502.49, 2926.31] |
| SMALL | JointSLA | 209.54 ± 146.69 [162.85, 264.15] | 80.39 ± 23.08 [72.49, 88.76] | 877.26 ± 775.05 [635.85, 1183.09] | 1634.22 ± 1487.20 [1170.75, 2206.47] |
| MEDIUM | SLA-aware | 296.89 ± 123.58 [256.68, 343.49] | 108.89 ± 34.89 [97.20, 121.69] | 1197.69 ± 534.28 [1025.72, 1400.28] | 2354.14 ± 1436.65 [1893.40, 2905.70] |
| MEDIUM | MJO | 253.83 ± 114.36 [216.84, 296.72] | 101.02 ± 34.60 [90.14, 114.29] | 1007.79 ± 474.29 [854.93, 1190.78] | 1960.58 ± 1067.52 [1604.09, 2356.25] |
| MEDIUM | JointSLA | 221.95 ± 117.65 [185.10, 267.72] | 94.33 ± 36.98 [83.07, 108.57] | 871.31 ± 503.99 [708.62, 1060.63] | 1622.58 ± 1051.79 [1273.91, 2008.12] |
| LARGE | SLA-aware | 331.54 ± 90.92 [301.03, 364.82] | 113.50 ± 22.76 [105.57, 121.59] | 1434.21 ± 461.19 [1280.88, 1606.29] | 2602.19 ± 1024.67 [2264.25, 2988.03] |
| LARGE | MJO | 227.35 ± 71.68 [203.97, 254.79] | 98.24 ± 17.88 [92.16, 104.68] | 893.62 ± 383.12 [769.55, 1037.57] | 1538.91 ± 748.97 [1299.34, 1822.68] |
| LARGE | JointSLA | 240.14 ± 79.63 [214.42, 269.90] | 94.75 ± 18.03 [88.66, 101.34] | 1006.89 ± 402.88 [873.60, 1159.14] | 1820.91 ± 826.64 [1553.66, 2142.68] |

Latencies include network, service and node queues, execution, lifecycle penalties and completions after the arrival horizon. Quantiles are calculated within each run; table intervals describe the mean of these seed-level quantiles.

# Gold / Silver / Bronze

| Scale | Policy | Gold SLA % | Silver SLA % | Bronze SLA % |
| --- | --- | --- | --- | --- |
| SMALL | SLA-aware | 62.04 ± 10.09 [58.53, 65.58] | 54.53 ± 10.82 [50.60, 58.20] | 51.75 ± 12.37 [47.46, 56.09] |
| SMALL | MJO | 57.63 ± 9.07 [54.40, 60.74] | 54.77 ± 9.43 [51.35, 58.13] | 47.35 ± 12.77 [42.98, 51.88] |
| SMALL | JointSLA | 61.96 ± 8.21 [59.00, 64.84] | 48.71 ± 12.40 [44.30, 53.02] | 39.36 ± 13.05 [34.91, 44.12] |
| MEDIUM | SLA-aware | 63.07 ± 7.79 [60.35, 65.81] | 59.14 ± 6.61 [56.88, 61.46] | 56.50 ± 8.40 [53.51, 59.40] |
| MEDIUM | MJO | 60.52 ± 8.46 [57.55, 63.55] | 59.87 ± 7.27 [57.20, 62.32] | 51.37 ± 9.79 [47.94, 54.80] |
| MEDIUM | JointSLA | 64.67 ± 6.93 [62.15, 67.03] | 53.84 ± 7.90 [51.13, 56.69] | 45.10 ± 11.19 [41.30, 49.12] |
| LARGE | SLA-aware | 60.38 ± 4.52 [58.81, 61.97] | 59.40 ± 5.76 [57.34, 61.40] | 64.44 ± 5.90 [62.32, 66.47] |
| LARGE | MJO | 61.04 ± 4.06 [59.65, 62.49] | 57.83 ± 5.40 [55.91, 59.73] | 54.67 ± 6.79 [52.31, 57.07] |
| LARGE | JointSLA | 63.36 ± 4.56 [61.78, 65.00] | 54.28 ± 5.93 [52.30, 56.47] | 52.10 ± 8.43 [49.18, 55.07] |

| Scale | Policy | Gold mean ms | Silver mean ms | Bronze mean ms |
| --- | --- | --- | --- | --- |
| SMALL | SLA-aware | 170.90 ± 83.43 [143.49, 201.30] | 283.12 ± 179.19 [224.85, 351.77] | 439.75 ± 390.86 [317.21, 586.18] |
| SMALL | MJO | 148.46 ± 104.51 [114.14, 188.66] | 245.77 ± 124.56 [204.18, 290.96] | 369.36 ± 416.49 [242.82, 534.84] |
| SMALL | JointSLA | 135.40 ± 56.26 [116.70, 156.08] | 213.13 ± 212.76 [151.96, 299.11] | 286.63 ± 282.34 [196.20, 393.42] |
| MEDIUM | SLA-aware | 157.23 ± 64.45 [137.02, 181.72] | 287.23 ± 131.52 [246.57, 338.31] | 452.17 ± 250.32 [372.16, 548.16] |
| MEDIUM | MJO | 134.34 ± 75.44 [112.09, 164.66] | 280.64 ± 116.52 [241.00, 323.79] | 349.56 ± 216.49 [281.42, 434.15] |
| MEDIUM | JointSLA | 151.64 ± 69.43 [130.47, 178.93] | 209.94 ± 90.27 [181.19, 244.04] | 304.96 ± 220.16 [233.19, 386.71] |
| LARGE | SLA-aware | 144.90 ± 44.69 [131.01, 162.56] | 265.51 ± 98.49 [234.18, 303.08] | 580.92 ± 188.92 [516.72, 650.02] |
| LARGE | MJO | 130.05 ± 36.46 [117.87, 143.23] | 228.91 ± 79.75 [203.22, 258.61] | 321.14 ± 128.14 [279.84, 368.57] |
| LARGE | JointSLA | 140.91 ± 50.22 [126.67, 161.43] | 214.94 ± 80.08 [189.45, 245.07] | 362.09 ± 148.42 [311.90, 416.26] |

| Scale | Policy | Gold p95 ms | Silver p95 ms | Bronze p95 ms |
| --- | --- | --- | --- | --- |
| SMALL | SLA-aware | 723.12 ± 443.76 [579.18, 891.47] | 1182.01 ± 758.26 [926.73, 1464.57] | 1617.63 ± 1358.69 [1172.23, 2121.71] |
| SMALL | MJO | 641.22 ± 634.41 [447.04, 890.16] | 973.85 ± 590.57 [771.01, 1190.18] | 1418.71 ± 1920.25 [830.50, 2165.21] |
| SMALL | JointSLA | 517.02 ± 268.99 [427.33, 615.30] | 839.51 ± 866.96 [578.00, 1177.25] | 1170.70 ± 1343.22 [755.68, 1694.66] |
| MEDIUM | SLA-aware | 636.59 ± 358.61 [534.94, 781.80] | 1216.35 ± 1055.28 [938.84, 1656.02] | 1776.85 ± 985.05 [1453.20, 2140.32] |
| MEDIUM | MJO | 521.10 ± 400.66 [404.26, 682.48] | 1098.02 ± 623.66 [895.19, 1332.46] | 1334.95 ± 848.50 [1051.69, 1659.36] |
| MEDIUM | JointSLA | 574.60 ± 372.05 [469.07, 724.67] | 818.15 ± 419.63 [685.79, 978.26] | 1219.79 ± 925.74 [915.47, 1562.43] |
| LARGE | SLA-aware | 604.42 ± 215.21 [536.59, 688.65] | 1051.03 ± 478.76 [901.74, 1237.28] | 2169.15 ± 794.99 [1906.54, 2465.79] |
| LARGE | MJO | 480.72 ± 155.52 [426.94, 536.63] | 871.99 ± 429.39 [737.01, 1037.80] | 1144.56 ± 572.57 [957.93, 1361.44] |
| LARGE | JointSLA | 543.72 ± 244.78 [474.75, 640.70] | 858.32 ± 378.05 [737.81, 1001.01] | 1390.21 ± 591.11 [1191.76, 1604.23] |

Tier differences are descriptive; the primary Holm family does not establish tier-specific significance. Gold disadvantages remain visible.

# Resource Cost

| Scale | Policy | Allocated replicas | Peak replicas | Reserved VRAM % |
| --- | --- | --- | --- | --- |
| SMALL | SLA-aware | 27.09 ± 1.75 [26.48, 27.72] | 28.37 ± 2.16 [27.60, 29.13] | 94.34 ± 1.29 [93.88, 94.79] |
| SMALL | MJO | 26.63 ± 1.55 [26.09, 27.17] | 28.33 ± 2.02 [27.63, 29.07] | 92.20 ± 1.95 [91.48, 92.87] |
| SMALL | JointSLA | 25.93 ± 1.11 [25.53, 26.30] | 27.93 ± 1.68 [27.33, 28.50] | 91.18 ± 3.42 [89.93, 92.34] |
| MEDIUM | SLA-aware | 54.59 ± 3.15 [53.42, 55.65] | 56.53 ± 3.66 [55.17, 57.77] | 95.04 ± 1.03 [94.66, 95.38] |
| MEDIUM | MJO | 53.88 ± 3.19 [52.71, 54.96] | 56.50 ± 3.88 [55.10, 57.80] | 93.50 ± 1.75 [92.85, 94.09] |
| MEDIUM | JointSLA | 52.94 ± 2.72 [51.97, 53.87] | 55.67 ± 3.47 [54.43, 56.87] | 93.36 ± 1.72 [92.73, 93.95] |
| LARGE | SLA-aware | 108.65 ± 3.85 [107.27, 110.01] | 112.83 ± 4.69 [111.17, 114.47] | 94.91 ± 0.68 [94.67, 95.15] |
| LARGE | MJO | 108.48 ± 3.60 [107.22, 109.72] | 113.37 ± 4.75 [111.67, 115.07] | 94.07 ± 0.74 [93.80, 94.32] |
| LARGE | JointSLA | 107.38 ± 3.79 [106.07, 108.71] | 112.07 ± 4.77 [110.40, 113.73] | 93.99 ± 0.81 [93.71, 94.28] |

| Scale | Policy | CPU % | GPU % | Replicas/service |
| --- | --- | --- | --- | --- |
| SMALL | SLA-aware | 10.07 ± 0.73 [9.82, 10.34] | 47.00 ± 5.16 [45.21, 48.82] | 1.35 ± 0.09 [1.32, 1.39] |
| SMALL | MJO | 10.10 ± 0.77 [9.84, 10.37] | 46.66 ± 5.76 [44.68, 48.70] | 1.33 ± 0.08 [1.30, 1.36] |
| SMALL | JointSLA | 10.22 ± 0.73 [9.96, 10.48] | 47.15 ± 5.52 [45.26, 49.09] | 1.30 ± 0.06 [1.28, 1.32] |
| MEDIUM | SLA-aware | 9.83 ± 0.78 [9.56, 10.10] | 46.43 ± 2.95 [45.39, 47.48] | 1.36 ± 0.08 [1.34, 1.39] |
| MEDIUM | MJO | 9.84 ± 0.78 [9.56, 10.11] | 46.12 ± 2.99 [45.09, 47.17] | 1.35 ± 0.08 [1.32, 1.37] |
| MEDIUM | JointSLA | 9.94 ± 0.80 [9.65, 10.21] | 46.54 ± 2.87 [45.52, 47.54] | 1.32 ± 0.07 [1.30, 1.35] |
| LARGE | SLA-aware | 9.77 ± 0.47 [9.61, 9.94] | 46.14 ± 1.71 [45.54, 46.75] | 1.36 ± 0.05 [1.34, 1.38] |
| LARGE | MJO | 9.87 ± 0.48 [9.70, 10.04] | 46.26 ± 1.86 [45.63, 46.93] | 1.36 ± 0.04 [1.34, 1.37] |
| LARGE | JointSLA | 9.91 ± 0.48 [9.74, 10.08] | 46.40 ± 1.75 [45.81, 47.03] | 1.34 ± 0.05 [1.33, 1.36] |

Allocated integral includes cold/retiring replicas. Utilization averages equally weight node-slots; capacity-weighted pool utilization is also exported. Resource diagnostic inference is explicitly exploratory.

# Reconfiguration Cost

| Scale | Policy | Total actions | Cold starts | Migrations | Actions/1,000 |
| --- | --- | --- | --- | --- | --- |
| SMALL | SLA-aware | 51.07 ± 21.19 [43.67, 58.60] | 29.07 ± 11.02 [25.27, 33.07] | 0.10 ± 0.40 [0.00, 0.27] | 8.87 ± 4.02 [7.51, 10.32] |
| SMALL | MJO | 45.43 ± 20.97 [38.50, 53.33] | 26.53 ± 10.94 [22.90, 30.60] | 0.03 ± 0.18 [0.00, 0.10] | 7.76 ± 3.56 [6.56, 9.06] |
| SMALL | JointSLA | 44.00 ± 21.21 [36.63, 51.53] | 25.20 ± 10.57 [21.47, 28.83] | 0.00 ± 0.00 [0.00, 0.00] | 7.67 ± 3.93 [6.30, 9.04] |
| MEDIUM | SLA-aware | 74.27 ± 18.28 [67.80, 80.67] | 44.27 ± 10.42 [40.47, 47.83] | 0.30 ± 0.92 [0.03, 0.67] | 6.40 ± 1.73 [5.77, 6.99] |
| MEDIUM | MJO | 83.63 ± 30.69 [73.10, 94.40] | 49.57 ± 16.48 [43.77, 55.37] | 0.07 ± 0.25 [0.00, 0.17] | 7.20 ± 2.76 [6.25, 8.18] |
| MEDIUM | JointSLA | 69.33 ± 21.88 [61.40, 76.93] | 41.70 ± 12.13 [37.37, 46.00] | 0.07 ± 0.25 [0.00, 0.17] | 5.97 ± 1.97 [5.27, 6.64] |
| LARGE | SLA-aware | 97.67 ± 9.92 [94.10, 101.13] | 64.10 ± 6.46 [61.80, 66.40] | 0.40 ± 0.89 [0.13, 0.73] | 4.21 ± 0.49 [4.03, 4.37] |
| LARGE | MJO | 144.47 ± 31.18 [133.10, 155.00] | 88.23 ± 16.77 [82.33, 93.87] | 0.13 ± 0.43 [0.00, 0.30] | 6.21 ± 1.36 [5.73, 6.68] |
| LARGE | JointSLA | 94.23 ± 14.36 [89.27, 99.13] | 62.23 ± 8.74 [59.10, 65.30] | 0.03 ± 0.18 [0.00, 0.10] | 4.06 ± 0.68 [3.82, 4.29] |

# Controller and Solver Overhead

| Scale | Policy | Full controller mean ms | Median ms | p95 ms |
| --- | --- | --- | --- | --- |
| SMALL | JointSLA | 1.07 ± 0.13 [1.02, 1.12] | 1.05 ± 0.13 [1.00, 1.10] | 1.49 ± 0.21 [1.42, 1.57] |
| SMALL | MJO | 1.31 ± 0.26 [1.23, 1.41] | 1.25 ± 0.28 [1.15, 1.35] | 2.10 ± 0.43 [1.95, 2.25] |
| MEDIUM | JointSLA | 2.24 ± 0.12 [2.20, 2.28] | 2.25 ± 0.12 [2.21, 2.29] | 3.10 ± 0.27 [3.02, 3.20] |
| MEDIUM | MJO | 3.42 ± 0.35 [3.30, 3.55] | 3.05 ± 0.30 [2.94, 3.16] | 5.81 ± 0.83 [5.51, 6.10] |
| LARGE | JointSLA | 6.85 ± 1.03 [6.49, 7.21] | 6.55 ± 1.04 [6.19, 6.91] | 10.22 ± 1.68 [9.60, 10.80] |
| LARGE | MJO | 13.75 ± 2.12 [13.02, 14.50] | 10.91 ± 1.46 [10.39, 11.42] | 30.10 ± 8.28 [27.31, 33.12] |

| Scale | Policy | Total CPU ms/request | Total CPU ms/1,000 | Solver mean ms | Solver p95 ms |
| --- | --- | --- | --- | --- | --- |
| SMALL | JointSLA | 0.05 ± 0.01 [0.05, 0.06] | 54.20 ± 10.34 [50.72, 58.01] | 0.00 ± 0.00 [0.00, 0.00] | 0.00 ± 0.00 [0.00, 0.00] |
| SMALL | MJO | 0.25 ± 0.07 [0.23, 0.28] | 254.92 ± 69.17 [232.24, 280.65] | 0.05 ± 0.02 [0.05, 0.06] | 0.17 ± 0.13 [0.13, 0.22] |
| MEDIUM | JointSLA | 0.05 ± 0.01 [0.05, 0.05] | 50.98 ± 6.05 [48.87, 53.13] | 0.00 ± 0.00 [0.00, 0.00] | 0.00 ± 0.00 [0.00, 0.00] |
| MEDIUM | MJO | 0.26 ± 0.04 [0.25, 0.27] | 259.83 ± 39.12 [246.99, 274.56] | 0.05 ± 0.01 [0.04, 0.05] | 0.15 ± 0.07 [0.13, 0.17] |
| LARGE | JointSLA | 0.07 ± 0.01 [0.07, 0.07] | 69.33 ± 9.88 [65.90, 72.84] | 0.00 ± 0.00 [0.00, 0.00] | 0.00 ± 0.00 [0.00, 0.00] |
| LARGE | MJO | 0.32 ± 0.04 [0.31, 0.33] | 320.56 ± 37.22 [307.51, 333.75] | 0.05 ± 0.01 [0.05, 0.05] | 0.14 ± 0.06 [0.13, 0.17] |

Full controller wall time is snapshot + policy + apply at each control instant; total controller CPU also includes event-time routing and audit instrumentation. MJO routing callbacks optimize batches/reassign backlog; JointSLA callbacks assign individual requests. Native routing callback mean/p95 have different units of work and must not be directly interpreted as per-request speed. The common offered-request CPU denominator is exported. Historical SLA-aware host timings are excluded from fresh overhead claims.

# Performance-Complexity Trade-Off

| Scale | Policy | SLA % | p95 ms | Full controller ms | CPU ms/request | SLA gain pp/controller ms |
| --- | --- | --- | --- | --- | --- | --- |
| SMALL | JointSLA | 50.91 | 877.26 | 1.069 | 0.0542 | 5.577 |
| SMALL | MJO | 53.92 | 1190.90 | 1.314 | 0.2549 | 2.243 |
| MEDIUM | JointSLA | 54.91 | 871.31 | 2.239 | 0.0510 | 2.151 |
| MEDIUM | MJO | 57.50 | 1007.79 | 3.423 | 0.2598 | 0.651 |
| LARGE | JointSLA | 56.71 | 1006.89 | 6.851 | 0.0693 | 0.699 |
| LARGE | MJO | 57.97 | 893.62 | 13.748 | 0.3206 | 0.257 |

The last column is descriptive against historical SLA-aware outcomes. Audit-heavy batch processing and Python overhead are included; it is not a universal efficiency law or a scalability bound.

# Statistical Tests

30 paired seeds per scale; 10,000 seed-bootstrap percentile resamples; two-sided Wilcoxon with differences rounded to 12 decimals; exact p without ties/zeros, otherwise tie-adjusted asymptotic p; Holm families of 12 primary, 12 strength-sanity, three overhead tests. Positive B−A, relative gain and rank-biserial effect indicate policy A improvement. SLA absolute differences here use fractions; ×100 converts to percentage points.

Primary A=JointSLA, B=MJO:

| Scale | Metric | B−A [95% CI] | Relative gain % [95% CI] | Wilcoxon W | p | Holm p | RBC | W/T/L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMALL | sla_breach_rate | 0.0301297 [0.0159079, 0.0460213] | 5.59 [2.86, 8.56] | 71 | 0.000505488 | 0.00556037 | 0.695 | 22/0/8 |
| SMALL | mean_request_latency_ms | 46.3528 [-11.9953, 109.48] | 18.11 [-5.30, 37.19] | 113 | 0.0128337 | 0.0513349 | 0.514 | 22/0/8 |
| SMALL | p95_latency_ms | 313.643 [-73.6508, 752.965] | 26.34 [-6.27, 49.52] | 103 | 0.00663954 | 0.0331977 | 0.557 | 22/0/8 |
| SMALL | p99_latency_ms | 489.655 [-187.677, 1246.94] | 23.05 [-11.69, 47.42] | 149 | 0.138556 | 0.138556 | 0.315 | 18/1/11 |
| MEDIUM | sla_breach_rate | 0.0258861 [0.0165721, 0.0350844] | 4.50 [2.90, 6.11] | 40 | 1.59778e-05 | 0.000191733 | 0.828 | 24/0/6 |
| MEDIUM | mean_request_latency_ms | 31.8767 [12.3487, 49.9404] | 12.56 [5.14, 19.53] | 74 | 0.000666553 | 0.00666553 | 0.682 | 23/0/7 |
| MEDIUM | p95_latency_ms | 136.486 [36.725, 226.81] | 13.54 [3.46, 22.54] | 78 | 0.000951774 | 0.00856597 | 0.665 | 21/0/9 |
| MEDIUM | p99_latency_ms | 338.001 [91.721, 586.69] | 17.24 [4.82, 28.84] | 115 | 0.014538 | 0.0513349 | 0.505 | 19/0/11 |
| LARGE | sla_breach_rate | 0.0125918 [0.00499141, 0.019926] | 2.17 [0.84, 3.45] | 96 | 0.00403179 | 0.0282226 | 0.587 | 23/0/7 |
| LARGE | mean_request_latency_ms | -12.786 [-27.4867, 3.87723] | -5.62 [-12.18, 1.48] | 131 | 0.036435 | 0.07287 | -0.437 | 10/0/20 |
| LARGE | p95_latency_ms | -113.265 [-203.416, 0.445317] | -12.67 [-23.96, 0.12] | 78 | 0.000951774 | 0.00856597 | -0.665 | 7/0/23 |
| LARGE | p99_latency_ms | -281.999 [-477.065, -72.4365] | -18.32 [-32.92, -4.54] | 99 | 0.00501261 | 0.0300757 | -0.574 | 7/0/23 |

Secondary A=MJO, B=SLA-aware:

| Scale | Metric | B−A [95% CI] | Relative gain % [95% CI] | Wilcoxon W | p | Holm p | RBC | W/T/L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMALL | sla_breach_rate | 0.0294707 [0.0169073, 0.0411783] | 5.18 [3.02, 7.15] | 60 | 0.000169897 | 0.00118928 | 0.742 | 25/0/5 |
| SMALL | mean_request_latency_ms | 40.4782 [-14.312, 101.56] | 13.66 [-5.61, 29.85] | 159 | 0.134735 | 0.41936 | 0.316 | 18/0/12 |
| SMALL | p95_latency_ms | 124.271 [-214.59, 460.375] | 9.45 [-16.83, 31.98] | 178 | 0.271006 | 0.542011 | 0.234 | 18/0/12 |
| SMALL | p99_latency_ms | 74.9474 [-612.321, 697.515] | 3.41 [-29.37, 29.83] | 201 | 0.529105 | 0.542011 | 0.135 | 18/0/12 |
| MEDIUM | sla_breach_rate | 0.0222669 [0.0137013, 0.0307301] | 3.73 [2.30, 5.13] | 43 | 2.36668e-05 | 0.000189334 | 0.815 | 25/0/5 |
| MEDIUM | mean_request_latency_ms | 43.0606 [22.2812, 65.09] | 14.50 [7.77, 21.41] | 82 | 0.0013406 | 0.00804362 | 0.647 | 23/0/7 |
| MEDIUM | p95_latency_ms | 189.902 [73.2129, 316.413] | 15.86 [6.85, 24.91] | 100 | 0.00538278 | 0.0269139 | 0.570 | 24/0/6 |
| MEDIUM | p99_latency_ms | 393.559 [25.6939, 850.882] | 16.72 [0.14, 31.59] | 153 | 0.10484 | 0.41936 | 0.342 | 18/0/12 |
| LARGE | sla_breach_rate | 0.0352971 [0.0288911, 0.0416166] | 5.74 [4.72, 6.73] | 0 | 1.86265e-09 | 2.23517e-08 | 1.000 | 30/0/0 |
| LARGE | mean_request_latency_ms | 104.188 [83.9686, 123.576] | 31.43 [26.36, 35.86] | 4 | 1.30385e-08 | 1.43424e-07 | 0.983 | 29/0/1 |
| LARGE | p95_latency_ms | 540.591 [414.012, 655.654] | 37.69 [30.11, 43.83] | 15 | 2.55182e-07 | 2.29664e-06 | 0.935 | 29/0/1 |
| LARGE | p99_latency_ms | 1063.28 [796.336, 1341.33] | 40.86 [32.84, 48.03] | 9 | 6.14673e-08 | 6.14673e-07 | 0.961 | 28/0/2 |

Overhead A=JointSLA, B=MJO:

| Scale | Metric | B−A [95% CI] | Relative gain % [95% CI] | Wilcoxon W | p | Holm p | RBC | W/T/L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMALL | controller_total_instrumented_mean_ms | 0.245235 [0.168262, 0.330816] | 18.67 [13.41, 23.74] | 19 | 5.71832e-07 | 5.71832e-07 | 0.918 | 26/0/4 |
| MEDIUM | controller_total_instrumented_mean_ms | 1.18411 [1.07199, 1.30284] | 34.59 [32.30, 36.81] | 0 | 1.86265e-09 | 5.58794e-09 | 1.000 | 30/0/0 |
| LARGE | controller_total_instrumented_mean_ms | 6.89723 [6.27124, 7.57087] | 50.17 [47.44, 52.89] | 0 | 1.86265e-09 | 5.58794e-09 | 1.000 | 30/0/0 |

Rank-test significance and a bootstrap CI for the mean difference need not agree: they summarize different aspects of these seed differences. The unchanged supported-improvement rule requires both Holm p<.05 and a positive paired mean lower bound. For LARGE p95 the mean favors MJO and Holm p<.05, but its paired mean CI includes zero; this remains mixed evidence. LARGE p99 has both a negative paired mean CI and Holm p<.05, supporting the MJO advantage in that metric.

# Negative Seeds

141 metric/seed losses for JointSLA across 360 primary paired metric observations; all are retained in `negative_seed_cases.csv`. Counts below refer to metric cases, not distinct seeds.

| Scale | Metric | Joint W/T/L |
| --- | --- | --- |
| SMALL | sla_breach_rate | 22/0/8 |
| SMALL | mean_request_latency_ms | 22/0/8 |
| SMALL | p95_latency_ms | 22/0/8 |
| SMALL | p99_latency_ms | 18/1/11 |
| MEDIUM | sla_breach_rate | 24/0/6 |
| MEDIUM | mean_request_latency_ms | 23/0/7 |
| MEDIUM | p95_latency_ms | 21/0/9 |
| MEDIUM | p99_latency_ms | 19/0/11 |
| LARGE | sla_breach_rate | 23/0/7 |
| LARGE | mean_request_latency_ms | 10/0/20 |
| LARGE | p95_latency_ms | 7/0/23 |
| LARGE | p99_latency_ms | 7/0/23 |

# Solver Failures / Timeouts

| Scale | Calls | Optimal | Feasible | Timeout | Infeasible | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| SMALL | 361629 | 361629 | 0 | 0 | 0 | 0 |
| MEDIUM | 743065 | 743065 | 0 | 0 | 0 | 0 |
| LARGE | 1627739 | 1627739 | 0 | 0 | 0 | 0 |

No-eligible-replica matching is classified as infeasible and preserves queued/pending work. Every other failure is also recorded, not discarded. Consult per-run `solver.csv.gz` for context, reason, matrix/block sizes and deterministic work limits.

# B1-B5 Results

| Hypothesis | Result |
| --- | --- |
| B1 | NOT SUPPORTED |
| B2 | PASS |
| B3 | NOT SUPPORTED |
| B4 | PASS |
| B5 | NOT SUPPORTED |

| Scale | Replica increase upper % | VRAM increase upper pp | Action increase upper % | B5 screen |
| --- | --- | --- | --- | --- |
| SMALL | 4.12 | 1.90 | 20.55 | False |
| MEDIUM | 2.34 | 0.54 | 32.49 | False |
| LARGE | 1.44 | 0.28 | 65.07 | False |

MJO does not satisfy the predeclared all-scale stronger-baseline gate. This is a baseline-design limitation/failure, not evidence that JointSLA defeated a verified strong optimizer.

Failed strength-gate components (A=MJO, B=SLA-aware):

| Scale | Metric | B−A [95% CI] | Relative gain % [95% CI] | Wilcoxon W | p | Holm p | RBC | W/T/L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMALL | p95_latency_ms | 124.271 [-214.59, 460.375] | 9.45 [-16.83, 31.98] | 178 | 0.271006 | 0.542011 | 0.234 | 18/0/12 |

Queue-component diagnostics:

| Scale | Policy | Service queue mean ms | Node queue mean ms |
| --- | --- | --- | --- |
| SMALL | SLA-aware | 271.51 ± 172.75 [216.28, 335.09] | 0.72 ± 0.30 [0.62, 0.83] |
| SMALL | MJO | 232.31 ± 151.73 [184.03, 289.24] | 0.67 ± 0.35 [0.56, 0.81] |
| SMALL | JointSLA | 187.18 ± 145.39 [140.74, 242.80] | 0.75 ± 0.38 [0.63, 0.90] |
| MEDIUM | SLA-aware | 270.90 ± 122.83 [231.52, 318.66] | 0.70 ± 0.24 [0.62, 0.78] |
| MEDIUM | MJO | 228.96 ± 113.19 [192.16, 270.93] | 0.63 ± 0.23 [0.55, 0.71] |
| MEDIUM | JointSLA | 197.84 ± 116.31 [161.92, 242.92] | 0.64 ± 0.21 [0.57, 0.72] |
| LARGE | SLA-aware | 305.07 ± 90.40 [274.39, 338.21] | 0.64 ± 0.13 [0.59, 0.68] |
| LARGE | MJO | 202.04 ± 71.12 [178.82, 228.10] | 0.61 ± 0.12 [0.57, 0.65] |
| LARGE | JointSLA | 215.13 ± 78.88 [188.88, 244.37] | 0.62 ± 0.10 [0.58, 0.66] |

These observed waiting components and tier/resource trade-offs describe where delays differ; they do not identify a causal mechanism. Candidate estimates hold observed shared-resource waiting fixed, action deltas are additive, and no future request demand is optimized. Consequently exact subproblem solutions can still be inferior under later nonlinear contention. The convex priority-weighted objective targets neither the unweighted breach indicator nor p95/p99 directly. Further improvements require a separately preregistered experiment, not retuning these results. Secondary metric/seed losses are retained in `baseline_strength_negative_cases.csv`.

# Threats to Validity

Three synthetic scales and 30 seeds do not represent live telco infrastructure. A current-state convex lateness surrogate can misestimate stochastic contention; oldest-first matching decomposition and additive deployment deltas omit cross-service nonlinear interference. Current-backlog reoptimization does more routing work than JointSLA, preserving workers but changing destination choices. Weights are fixed, not empirically optimal. Pilot seeds overlap the final 30 but are used only for correctness/runtime, without tuning. Timing is sequential on one laptop with instrumentation and host variability; no cross-policy repeated timing crossover was performed. RSS is sampled, not an exact peak. Failure classification includes transient no-eligible states. B2/B3/B5 are predeclared operational bootstrap screens, not formal equivalence/causal mediation tests.

# Safe Paper Claims

At SMALL, JointSLA improves sla_breach_rate over this MJO implementation by 5.59% (Holm p=0.00556037, positive paired lower CI).

At MEDIUM, JointSLA improves sla_breach_rate over this MJO implementation by 4.50% (Holm p=0.000191733, positive paired lower CI).

At MEDIUM, JointSLA improves mean_request_latency_ms over this MJO implementation by 12.56% (Holm p=0.00666553, positive paired lower CI).

At MEDIUM, JointSLA improves p95_latency_ms over this MJO implementation by 13.54% (Holm p=0.00856597, positive paired lower CI).

At LARGE, JointSLA improves sla_breach_rate over this MJO implementation by 2.17% (Holm p=0.0282226, positive paired lower CI).

At LARGE, MJO improves p99_latency_ms; JointSLA relative gain is -18.32% (Holm p=0.0300757, negative paired upper CI).

JointSLA has lower full-controller mean at all tested scales in the separate Holm-corrected overhead family.

The stronger-baseline sanity gate failed; comparisons characterize this implementation, not verified superiority over a strong optimization baseline.

# Claims We Cannot Make

Global stochastic optimality, state-of-the-art performance, universal superiority, carrier-grade/production readiness, exact paper replication, formally proved equivalence, causal resource explanations or a guaranteed B-level acceptance. No post-results JointSLA or MJO tuning occurred. A failed B1 cannot be turned into a strong-baseline victory.

# Implications for B-Level Publication

This experiment supplies reproducible adversarial evidence but does not establish the requested stronger-baseline comparison. The baseline design and surrogate need independent further study in a separately preregistered experiment; the present negative results must remain unchanged. Acceptance depends on external review, novelty, model validity and broader evidence. Existing frozen results remain valid for their previous comparisons.

Reproduce:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_strong_baseline.py --pilot --force
.venv\Scripts\python.exe run_strong_baseline.py --seeds 1:30 --force
.venv\Scripts\python.exe run_strong_baseline.py --seeds 1:30 --reuse-results
```

All 12 figures are provided as 300-dpi PNG and vector SVG/PDF. All numeric tables have seed-level mean ± SD and bootstrap intervals; raw/request/audit data remain available.
