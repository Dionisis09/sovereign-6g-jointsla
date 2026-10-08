# Motivation

Test whether cold recovery headroom and finite Gold retention can repair the previously observed hardware-grounded QoS/resource trade-off. This is the final algorithmic experiment; no v3.

# Why v2 Was Introduced

Previous seeds1–30 showed DIRECT v1 SLA25.48% vs baseline15.43%, Gold35.97% vs22.63%, and fewer ready replicas before bursts. These historical results motivate design only; all tables below use unseen seeds31–60.

# Prior Failure Mechanism

The earlier exploratory factorial indicated VRAM and cold costs interacting with consolidation. It did not prove a unique cause. Prior preburst readiness was1.03 vs1.66 and recovery breaches36.94% vs21.60%; scale-in counts alone did not explain the reversal.

# Frozen Design

Call v1 controller once; block selected scale-ins below causal warm requirement. Retain v1 dispatch/routing and other decisions. Establish a finite Gold floor through Gold-only repair if nonretiring ready+pending count is below requirement. Preserve cooldown, feasibility, max3 replicas and budget2. Repair precedes retained actions, at most one/service. No independent Silver/Bronze repair.

Parameters: H=1, Gold multiplier1.5, Silver=sqrt(1.5), Bronze1; Gold floor2, other floors1; W=5 derived from class cold readiness.

# Recovery-Aware Headroom

For backlog q, observed λ requests/s, class readiness R seconds, causal estimated serial cycle L seconds, deadline D seconds and slack h=max(D−L,0): required=min(3,max(tier_floor,ceil(tier_factor*max(qL/h,(q+λR)L/(R+h))))). Empty history λ=0; impossible slack with demand or no finite feasible cycle requires3. Cycle includes current nominal or past completion CPU/GPU/network/resource delay, excluding service FIFO wait. It is a fluid retention estimate, not a guarantee, forecast or admission decision.

# Gold Protection

The Gold floor cannot be created by rejecting scale-ins from an initial one-ready placement, so a bounded Gold-only repair is needed. Pending cold replicas count toward planned capacity, while ready capacity is logged separately. Infeasible deficits remain visible; no unlimited resources or altered cold delay.

# Causality / No-Future Information

Recover completed-slot per-service observed counts by algebraically inverting unchanged EWMA telemetry. W contains only prior completed slots. No controller reads arrivals tape, future work factors, expected rates or burst masks. Physical source/worker/dispatch/decisions are inherited; burst identification is exclusively retrospective. Unit tests compare observed history with exports, block future-tape access, verify deterministic routing and same budget.

Independent receipt: {"timestamp": "2026-10-07T16:15:31.757831+00:00", "runs": 180, "requests_verified": 3046965, "subgroup_rows_verified": 1080, "headroom_service_slots_verified": 240000, "paired_tests_independently_verified": 40, "input_hashes": true, "request_components": true, "memory_integrals": true, "controller_quantiles": true, "observed_history_only": true, "seed_gate_and_generation_timestamps_verified": true, "preserved": {"protected_files": 20769, "changed_files": []}}

# Development Seeds

101–105 only,0.5/1/2×,45 simulations. Exactly ONE candidate. Acceptance checked accounting/capacity/Gold guard/stability, wall≤600s,RSS≤4096MiB,drain≤120s,v2 mean step<10ms. No SLA-driven selection, grid search or development statistics promoted as paper evidence. See separate development outputs.

# Freeze Procedure

Freeze UTC 2026-10-07T15:59:44.340749+00:00; config SHA256 `8a535a5ac09d0eba31f0a6aab4ef9e0bc47752071ca6a1a55244ddbf61ad488a`. Source hashes, exact parameters, git state and protected historical manifest are archived. Configuration and source hashes are checked before held-out generation and again after analysis. All generation-ledger timestamps follow freeze. No post-hoc policy/config changes. Implementation commit: None; file hashes identify uncommitted code.

# Held-Out Seeds

31–60 paired across SLA-aware/v1/v2,1× and2×:180 simulations;3,046,965 exported outcomes independently verified. Shared workload/traffic hashes within every seed/load; no lost,duplicate,unplaced or dropped requests. Nodes10,services40,slots100,Δ100ms. These are the frozen existing hardware-grounded scenario, not the original exploratory5-node/20-service setting. No optional1.5×.

# 1.0x Hardware-Grounded Results

| load_multiplier | policy | sla_breach_rate | Gold_breach_rate | mean_request_latency_ms | p95_latency_ms | p99_latency_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | 0.25752 | 0.35613 | 61.517 | 228.2 | 378.42 |
| 1 | joint_sla_v2 | 0.22432 | 0.21998 | 61.288 | 236.15 | 418.05 |
| 1 | sla_aware | 0.14981 | 0.20542 | 48.708 | 189.73 | 422.69 |

# 2.0x High-Pressure Results

| load_multiplier | policy | sla_breach_rate | Gold_breach_rate | mean_request_latency_ms | p95_latency_ms | p99_latency_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | joint_sla_v1 | 0.39541 | 0.48775 | 115.06 | 448.32 | 745.43 |
| 2 | joint_sla_v2 | 0.49968 | 0.42485 | 278.87 | 1311.5 | 2608.4 |
| 2 | sla_aware | 0.39807 | 0.39049 | 166.6 | 764.06 | 1391.6 |

# Aggregate SLA

Rates in tables are fractions; multiply by100 for percent. Differences are v2−comparator (negative favors v2).

| load_multiplier | comparator | metric | delta_v2_minus_comparator | delta_ci95_lower | delta_ci95_upper | p_value | p_value_holm | rank_biserial_correlation | wins | ties | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | sla_breach_rate | -0.033191 | -0.043739 | -0.022236 | 4.4219e-06 | 1.3266e-05 | 0.86667 | 26 | 0 | 4 |
| 2 | joint_sla_v1 | sla_breach_rate | 0.10427 | 0.081062 | 0.128 | 3.7253e-09 | 1.4901e-08 | -0.9957 | 1 | 0 | 29 |
| 1 | sla_aware | sla_breach_rate | 0.074517 | 0.063516 | 0.085813 | 1.8626e-09 | 1.1176e-08 | -1 | 0 | 0 | 30 |
| 2 | sla_aware | sla_breach_rate | 0.10161 | 0.085291 | 0.11819 | 1.8626e-09 | 1.1176e-08 | -1 | 0 | 0 | 30 |

# Gold / Silver / Bronze

| load_multiplier | policy | Gold_breach_rate | Silver_breach_rate | Bronze_breach_rate |
| --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | 0.35613 | 0.24502 | 0.16377 |
| 1 | joint_sla_v2 | 0.21998 | 0.27004 | 0.18132 |
| 1 | sla_aware | 0.20542 | 0.10897 | 0.13121 |
| 2 | joint_sla_v1 | 0.48775 | 0.39215 | 0.29851 |
| 2 | joint_sla_v2 | 0.42485 | 0.54084 | 0.52918 |
| 2 | sla_aware | 0.39049 | 0.34608 | 0.45473 |

| load_multiplier | comparator | metric | delta_v2_minus_comparator | delta_ci95_lower | delta_ci95_upper | p_value | p_value_holm | rank_biserial_correlation | wins | ties | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | Gold_breach_rate | -0.13615 | -0.15703 | -0.116 | 1.8626e-09 | 1.1176e-08 | 1 | 30 | 0 | 0 |
| 1 | joint_sla_v1 | Silver_breach_rate | 0.025017 | 0.0096067 | 0.040061 | 0.0037444 | 0.014978 | -0.5914 | 9 | 0 | 21 |
| 1 | joint_sla_v1 | Bronze_breach_rate | 0.017553 | 0.002069 | 0.033298 | 0.038418 | 0.076837 | -0.43226 | 8 | 0 | 22 |
| 2 | joint_sla_v1 | Gold_breach_rate | -0.062908 | -0.083545 | -0.042116 | 9.2201e-06 | 1.844e-05 | 0.84516 | 24 | 0 | 6 |
| 2 | joint_sla_v1 | Silver_breach_rate | 0.14869 | 0.12631 | 0.17108 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 2 | joint_sla_v1 | Bronze_breach_rate | 0.23068 | 0.18831 | 0.27208 | 3.7253e-09 | 2.9802e-08 | -0.9957 | 1 | 0 | 29 |
| 1 | sla_aware | Gold_breach_rate | 0.014561 | -0.0039148 | 0.033122 | 0.18397 | 0.18397 | -0.28172 | 13 | 0 | 17 |
| 1 | sla_aware | Silver_breach_rate | 0.16107 | 0.14555 | 0.17779 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 1 | sla_aware | Bronze_breach_rate | 0.050117 | 0.03459 | 0.065855 | 9.9838e-07 | 8.9854e-06 | -0.90538 | 5 | 0 | 25 |
| 2 | sla_aware | Gold_breach_rate | 0.034361 | 0.015189 | 0.053821 | 0.0020202 | 0.0040404 | -0.62581 | 7 | 0 | 23 |
| 2 | sla_aware | Silver_breach_rate | 0.19476 | 0.17262 | 0.21677 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 2 | sla_aware | Bronze_breach_rate | 0.074456 | 0.038836 | 0.11172 | 0.00095177 | 0.0028553 | -0.66452 | 10 | 0 | 20 |

Class results LIGHT/MEDIUM/HEAVY and their summaries are descriptive, not an additional confirmatory testing family. Tier protection can redistribute queue/resource pressure, so aggregate improvement alone cannot establish fairness.

# Mean / p95 / p99

| load_multiplier | policy | mean_request_latency_ms | median_latency_ms | p95_latency_ms | p99_latency_ms |
| --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | 61.517 | 29.738 | 228.2 | 378.42 |
| 1 | joint_sla_v2 | 61.288 | 29.858 | 236.15 | 418.05 |
| 1 | sla_aware | 48.708 | 23.49 | 189.73 | 422.69 |
| 2 | joint_sla_v1 | 115.06 | 48.074 | 448.32 | 745.43 |
| 2 | joint_sla_v2 | 278.87 | 74.353 | 1311.5 | 2608.4 |
| 2 | sla_aware | 166.6 | 46.442 | 764.06 | 1391.6 |

| load_multiplier | comparator | metric | delta_v2_minus_comparator | delta_ci95_lower | delta_ci95_upper | p_value | p_value_holm | rank_biserial_correlation | wins | ties | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | p95_latency_ms | 7.9455 | -9.1154 | 27.818 | 0.62635 | 0.62635 | -0.10538 | 13 | 0 | 17 |
| 1 | joint_sla_v1 | mean_request_latency_ms | -0.22842 | -3.4315 | 3.4623 | 0.62635 | 0.62635 | 0.10538 | 16 | 0 | 14 |
| 1 | joint_sla_v1 | p99_latency_ms | 39.631 | 6.3895 | 77.538 | 0.02085 | 0.06255 | -0.47957 | 8 | 0 | 22 |
| 2 | joint_sla_v1 | p95_latency_ms | 863.21 | 561.29 | 1227 | 1.8626e-09 | 1.1176e-08 | -1 | 0 | 0 | 30 |
| 2 | joint_sla_v1 | mean_request_latency_ms | 163.81 | 112.66 | 224.46 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 2 | joint_sla_v1 | p99_latency_ms | 1862.9 | 1270.2 | 2528.8 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 1 | sla_aware | p95_latency_ms | 46.425 | 29.507 | 61.501 | 3.4532e-05 | 0.00010359 | -0.80215 | 2 | 0 | 28 |
| 1 | sla_aware | mean_request_latency_ms | 12.581 | 9.7259 | 15.429 | 6.1467e-08 | 6.1467e-07 | -0.96129 | 2 | 0 | 28 |
| 1 | sla_aware | p99_latency_ms | -4.6414 | -45.379 | 33.822 | 0.96767 | 0.96767 | 0.010753 | 15 | 0 | 15 |
| 2 | sla_aware | p95_latency_ms | 547.46 | 309.63 | 822.45 | 9.2201e-06 | 3.688e-05 | -0.84516 | 4 | 0 | 26 |
| 2 | sla_aware | mean_request_latency_ms | 112.27 | 72.671 | 156.31 | 2.6077e-08 | 2.8685e-07 | -0.97419 | 2 | 0 | 28 |
| 2 | sla_aware | p99_latency_ms | 1216.8 | 705.57 | 1787.7 | 9.2201e-06 | 4.61e-05 | -0.84516 | 6 | 0 | 24 |

Quantiles are first computed per run over all arrivals after drain; then averaged across seeds. They are not pooled request quantiles.

| load_multiplier | comparator | metric | ratio | ci95_lower | ci95_upper | method | resamples |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | mean_request_latency_ms | 0.99629 | 0.94262 | 1.0574 | paired bootstrap ratio of seed means | 10000 |
| 1 | joint_sla_v1 | p95_latency_ms | 1.0348 | 0.95911 | 1.1197 | paired bootstrap ratio of seed means | 10000 |
| 1 | joint_sla_v1 | p99_latency_ms | 1.1047 | 1.0186 | 1.2122 | paired bootstrap ratio of seed means | 10000 |
| 1 | sla_aware | mean_request_latency_ms | 1.2583 | 1.1892 | 1.334 | paired bootstrap ratio of seed means | 10000 |
| 1 | sla_aware | p95_latency_ms | 1.2447 | 1.1458 | 1.349 | paired bootstrap ratio of seed means | 10000 |
| 1 | sla_aware | p99_latency_ms | 0.98902 | 0.90144 | 1.0879 | paired bootstrap ratio of seed means | 10000 |
| 2 | joint_sla_v1 | mean_request_latency_ms | 2.4236 | 1.9897 | 2.9233 | paired bootstrap ratio of seed means | 10000 |
| 2 | joint_sla_v1 | p95_latency_ms | 2.9254 | 2.2792 | 3.6535 | paired bootstrap ratio of seed means | 10000 |
| 2 | joint_sla_v1 | p99_latency_ms | 3.4991 | 2.7068 | 4.3707 | paired bootstrap ratio of seed means | 10000 |
| 2 | sla_aware | mean_request_latency_ms | 1.6738 | 1.4615 | 1.9013 | paired bootstrap ratio of seed means | 10000 |
| 2 | sla_aware | p95_latency_ms | 1.7165 | 1.4278 | 2.0361 | paired bootstrap ratio of seed means | 10000 |
| 2 | sla_aware | p99_latency_ms | 1.8744 | 1.539 | 2.2661 | paired bootstrap ratio of seed means | 10000 |

# Resource Cost

| load_multiplier | policy | average_replicas | peak_replicas | average_vram_residency_gib | peak_pool_vram_gib | average_cpu_utilization | average_gpu_utilization | cold_starts | scale_outs | scale_ins | migrations | total_actions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | 44.025 | 56.5 | 6.4341 | 8.7702 | 0.034404 | 0.263 | 37.567 | 37.567 | 36.3 | 2.6667 | 76.533 |
| 1 | joint_sla_v2 | 65.453 | 73.367 | 9.5124 | 10.888 | 0.034331 | 0.26385 | 61.767 | 61.767 | 33.867 | 0.2 | 95.833 |
| 1 | sla_aware | 68.724 | 75.433 | 10.099 | 11.528 | 0.034271 | 0.26541 | 99.4 | 99.4 | 68.533 | 1.8333 | 169.77 |
| 2 | joint_sla_v1 | 61.211 | 71.767 | 9.1545 | 11.064 | 0.06866 | 0.51651 | 60.233 | 60.233 | 36.333 | 13.967 | 110.53 |
| 2 | joint_sla_v2 | 70.974 | 75.367 | 10.344 | 11.228 | 0.066807 | 0.51127 | 49 | 49 | 14.567 | 0.96667 | 64.533 |
| 2 | sla_aware | 71.709 | 76.2 | 10.623 | 11.655 | 0.067845 | 0.52224 | 60.833 | 60.833 | 26.567 | 3.4667 | 90.867 |

| load_multiplier | comparator | metric | delta_v2_minus_comparator | delta_ci95_lower | delta_ci95_upper | p_value | p_value_holm | rank_biserial_correlation | wins | ties | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | average_replicas | 21.428 | 20.76 | 22.126 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 1 | joint_sla_v1 | average_vram_residency_gib | 3.0783 | 2.9397 | 3.2213 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 1 | joint_sla_v1 | total_actions | 19.3 | 13.6 | 25.234 | 5.7158e-06 | 2.8579e-05 | -0.94839 | 2 | 0 | 28 |
| 2 | joint_sla_v1 | average_replicas | 9.7633 | 8.2133 | 11.351 | 1.8626e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 |
| 2 | joint_sla_v1 | average_vram_residency_gib | 1.1894 | 0.9333 | 1.4356 | 1.3039e-08 | 9.127e-08 | -0.9828 | 2 | 0 | 28 |
| 2 | joint_sla_v1 | total_actions | -46 | -50.467 | -41.367 | 1.7192e-06 | 1.0315e-05 | 1 | 30 | 0 | 0 |
| 1 | sla_aware | average_replicas | -3.271 | -3.881 | -2.6726 | 1.7333e-06 | 1.3676e-05 | 1 | 30 | 0 | 0 |
| 1 | sla_aware | average_vram_residency_gib | -0.58708 | -0.70194 | -0.47108 | 5.5879e-09 | 6.7055e-08 | 0.9914 | 29 | 0 | 1 |
| 1 | sla_aware | total_actions | -73.933 | -80.2 | -67.5 | 1.7203e-06 | 1.3676e-05 | 1 | 30 | 0 | 0 |
| 2 | sla_aware | average_replicas | -0.73467 | -1.1504 | -0.30466 | 0.0026721 | 0.0053443 | 0.62796 | 24 | 0 | 6 |
| 2 | sla_aware | average_vram_residency_gib | -0.27889 | -0.42333 | -0.14243 | 0.00038009 | 0.0015204 | 0.70753 | 24 | 0 | 6 |
| 2 | sla_aware | total_actions | -26.333 | -30.3 | -22.5 | 1.7094e-06 | 1.3676e-05 | 1 | 30 | 0 | 0 |

VRAM is time-integrated residency divided by10s; replica occupancy is integrated over the same horizon, including correct migration accounting. Peak VRAM includes simultaneous migration reservations. CPU/GPU utilization describes the finite physical simulated resources; no claim of overbooking improvement.

# Warm Replica Behavior

| load_multiplier | policy | mean_required_warm_replicas | mean_actual_ready_replicas | prevented_scale_ins_due_to_headroom | prevented_scale_ins_Gold | headroom_deficit_frequency | service_seconds_below_required | scaleouts_during_cold_exposure | gold_repair_scaleouts_proposed | gold_repair_scaleouts_accepted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v2 | 1.5127 | 1.5987 | 100.73 | 100.63 | 0.11467 | 45.867 | 2.6667 | 47.8 | 43.5 |
| 2 | joint_sla_v2 | 1.965 | 1.7421 | 12.8 | 12.767 | 0.31759 | 127.04 | 3.1 | 32.533 | 29.267 |

Metrics apply to v2 only. Prevented scale-ins count selected v1 proposals blocked by the guard, not all hypothetical actions. Accepted repair and proposed repair are distinguished. Deficit frequency denominator4000 service×control slots/run; service seconds=deficit slots×.1. Class cold exposure remains1/2/5 slots; it is never reduced by the policy.

# Burst Recovery

| load_multiplier | policy | preburst_active_replicas | queue_growth | recovery_window_breach_rate | mean_recovery_after_burst_slots | recovery_censored_fraction | scaleout_censored_fraction | scaleout_count | cold_exposure_service_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | 1.0236 | 7.9647 | 0.37122 | 0.85611 | 0 | 0.77028 | 0.26833 | 0.056611 |
| 1 | joint_sla_v2 | 1.5919 | 6.8628 | 0.3327 | 0.92149 | 0.00083333 | 0.72694 | 0.32583 | 0.066111 |
| 1 | sla_aware | 1.6731 | 5.3472 | 0.21283 | 0.65362 | 0.0016667 | 0.65694 | 0.545 | 0.10744 |
| 2 | joint_sla_v1 | 1.4242 | 20.649 | 0.59438 | 3.0709 | 0.023056 | 0.71222 | 0.335 | 0.075667 |
| 2 | joint_sla_v2 | 1.7894 | 22.925 | 0.69944 | 3.8713 | 0.12694 | 0.86722 | 0.14167 | 0.03075 |
| 2 | sla_aware | 1.8058 | 19.678 | 0.58957 | 3.1458 | 0.079167 | 0.83056 | 0.20917 | 0.044611 |

Ready-before-burst is the previous control snapshot. Recovery cohort includes arrivals during burst until queue returns to max(preburst backlog,1) or next burst/horizon. Each seed aggregates its recovery cohorts, then seed means are compared. Conditional recovery/first-scaleout times exclude censored cases; censoring fractions are shown, not imputed as zero. Exposure uses allocated−active at control snapshots (cold/pending/retiring unavailability proxy), not a precise request-level cold penalty. Burst action/exposure windows extend until next burst or horizon.

# Controller Overhead

| load_multiplier | policy | controller_decision_mean_ms | controller_decision_median_ms | controller_decision_p95_ms | controller_total_instrumented_mean_ms | controller_total_instrumented_p95_ms | wall_clock_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | 4.3441 | 3.9301 | 8.3804 | 5.0014 | 9.1328 | 1.7588 |
| 1 | joint_sla_v2 | 2.9202 | 2.6088 | 5.6017 | 3.6217 | 6.4443 | 1.7505 |
| 1 | sla_aware | 0.71087 | 0.55409 | 1.6828 | 0.73957 | 1.7182 | 0.73827 |
| 2 | joint_sla_v1 | 4.4417 | 3.6063 | 10.275 | 5.2681 | 11.198 | 3.392 |
| 2 | joint_sla_v2 | 4.4086 | 4.1301 | 7.6424 | 5.3359 | 8.7804 | 3.516 |
| 2 | sla_aware | 1.1022 | 0.8587 | 2.8408 | 1.1351 | 2.8712 | 1.4335 |

Decision time includes policy+action application. Instrumented total adds snapshot time. Routing cost is exported separately; H5 is the preregistered per-run mean decision-step gate. Means/medians/p95 here average each run statistic, not pooled timing samples. Timing is machine-dependent; exact semantic traces are deterministic.

# Statistical Tests

30 independent paired seeds.10000 paired bootstrap percentile resamples,95% CI,seed73001,keyed streams. Wilcoxon two-sided with original rounding/tie/zero rules. Positive rank-biserial effect favors v2; wins/ties/losses use12-decimal rounded differences. Primary Holm families each comparator:SLA,Gold,p95×2loads=6. Secondary each comparator:mean,p99,Silver,Bronze,replicas,VRAM,actions×2loads=14. No request-level pseudoreplication. Independent DP/tie-adjusted Wilcoxon, bootstrap and Holm reconstructions verify all40 tests. See paired_tests.csv and summary_statistics.csv (mean,SD,CI).

# Performance-Resource Frontier

| load_multiplier | policy | sla_breach_rate | Gold_breach_rate | p95_latency_ms | average_replicas | average_vram_residency_gib | total_actions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | 0.25752 | 0.35613 | 228.2 | 44.025 | 6.4341 | 76.533 |
| 1 | joint_sla_v2 | 0.22432 | 0.21998 | 236.15 | 65.453 | 9.5124 | 95.833 |
| 1 | sla_aware | 0.14981 | 0.20542 | 189.73 | 68.724 | 10.099 | 169.77 |
| 2 | joint_sla_v1 | 0.39541 | 0.48775 | 448.32 | 61.211 | 9.1545 | 110.53 |
| 2 | joint_sla_v2 | 0.49968 | 0.42485 | 1311.5 | 70.974 | 10.344 | 64.533 |
| 2 | sla_aware | 0.39807 | 0.39049 | 764.06 | 71.709 | 10.623 | 90.867 |

Pareto figures show per-seed clouds, policy means and marginal95% bootstrap CIs for both loads; no continuous frontier fit or global optimality claim. Direct replica ratio(v2/baseline)=0.9524038181712355,VRAM ratio=0.9418701242770082. QoS gap reduction=0.3081572879750092.

# V2-H1 to V2-H6

| hypothesis | passed |
| --- | --- |
| V2-H1 | 1 |
| V2-H2 | 1 |
| V2-H3 | 0 |
| V2-H4 | 0 |
| V2-H5 | 1 |
| V2-H6 | 1 |

{
  "hypotheses": {
    "V2-H1": true,
    "V2-H2": true,
    "V2-H3": false,
    "V2-H4": false,
    "V2-H5": true,
    "V2-H6": true
  },
  "overall_success": false,
  "partial_success": true,
  "failure_criterion_triggered": true,
  "baseline_sla_gap_reduction_fraction": 0.3081572879750092,
  "residual_sla_gap_pp": 7.451723871893454,
  "materially_worse_than_baseline": true,
  "approximately_baseline_resource_cost": true,
  "direct_replica_ratio": 0.9524038181712355,
  "direct_vram_ratio": 0.9418701242770082,
  "latency_guardrail": "95% paired ratio upper <=1.05 plus supported baseline benefit; diagnostic, not formal powered noninferiority",
  "stop": true,
  "no_v3": true
}

H3 requires≥50% gap reduction and both resources≤95% baseline. H4 requires ratio upper≤1.05 for mean/p95/p99 relative to v1 plus supported advantage vs baseline; this is a declared diagnostic guardrail, not formal powered noninferiority.

# Negative Results

All worse-seed outcomes against both comparators are exported in negative_seed_cases.csv. Unsupported comparisons remain unsupported even when sample means improve. Retention spends more resources, Gold repair may consume action opportunities otherwise used by other tiers, and infeasible headroom is disclosed. No failed hypothesis is removed. Failure flags and partial-success flags can coexist under the preregistered criteria. Approximately-baseline resource cost is flagged if either replica or VRAM ratio reaches0.95; material resource saving requires both below the declared bound.

| load_multiplier | comparator | metric | delta_v2_minus_comparator | delta_ci95_lower | delta_ci95_upper | p_value | p_value_holm | rank_biserial_correlation | wins | ties | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | joint_sla_v1 | sla_breach_rate | -0.033191 | -0.043739 | -0.022236 | 4.4219e-06 | 1.3266e-05 | 0.86667 | 26 | 0 | 4 |
| 1 | joint_sla_v1 | Gold_breach_rate | -0.13615 | -0.15703 | -0.116 | 1.8626e-09 | 1.1176e-08 | 1 | 30 | 0 | 0 |
| 2 | joint_sla_v1 | sla_breach_rate | 0.10427 | 0.081062 | 0.128 | 3.7253e-09 | 1.4901e-08 | -0.9957 | 1 | 0 | 29 |
| 2 | joint_sla_v1 | Gold_breach_rate | -0.062908 | -0.083545 | -0.042116 | 9.2201e-06 | 1.844e-05 | 0.84516 | 24 | 0 | 6 |
| 1 | sla_aware | sla_breach_rate | 0.074517 | 0.063516 | 0.085813 | 1.8626e-09 | 1.1176e-08 | -1 | 0 | 0 | 30 |
| 1 | sla_aware | Gold_breach_rate | 0.014561 | -0.0039148 | 0.033122 | 0.18397 | 0.18397 | -0.28172 | 13 | 0 | 17 |
| 2 | sla_aware | sla_breach_rate | 0.10161 | 0.085291 | 0.11819 | 1.8626e-09 | 1.1176e-08 | -1 | 0 | 0 | 30 |
| 2 | sla_aware | Gold_breach_rate | 0.034361 | 0.015189 | 0.053821 | 0.0020202 | 0.0040404 | -0.62581 | 7 | 0 | 23 |

# Threats to Validity

One laptop GPU calibration, three measured vision model classes mapped to40 synthetic services; not a real distributed telco deployment. Fixed10-node topology,100-slot horizon,synthetic traffic/work variance/network/migration costs, class-average hardware times. Global v1 nominal estimator remains inherited. Cold readiness can exceed strict deadlines. Fluid headroom uses serial cycle estimates and retrospective latency telemetry, not a queue stability theorem. Five engineering seeds and one candidate do not prove universality. Held-out seeds control tuning leakage, not external validity. Multiple testing families are explicit; secondary/class/mechanism interpretations remain limited. Controller clocks/RSS are host-dependent.

# Safe Paper Claims

Only the following held-out supported lower-is-better comparisons may be claimed with their declared family/CI: 

| load_multiplier | comparator | metric |
| --- | --- | --- |
| 1 | joint_sla_v1 | sla_breach_rate |
| 1 | joint_sla_v1 | Gold_breach_rate |
| 2 | joint_sla_v1 | Gold_breach_rate |
| 2 | joint_sla_v1 | total_actions |
| 1 | sla_aware | average_replicas |
| 1 | sla_aware | average_vram_residency_gib |
| 1 | sla_aware | total_actions |
| 2 | sla_aware | average_replicas |
| 2 | sla_aware | average_vram_residency_gib |
| 2 | sla_aware | total_actions |

The fixed causal extension and its measured resource trade-offs are reproducible; historical negative results remain part of the contribution. No external literature percentages were used.

# Claims We Cannot Make

No forecasting/oracle claim; no universally best scheduler, guaranteed deadlines, global Pareto optimum, real5G/6G deployment validation, universal Gold fairness or proven general noninferiority. No undisclosed dropped traffic. Do not claim novelty from implementation alone; final literature/novelty review is a separate next stage.

# Final B-Level Assessment

The full declared success criterion is not met. This study can inform a B-level systems paper as a bounded performance/resource contribution with hardware-grounded negative validation; venue suitability is conditional on literature differentiation, contribution framing and review. A positive aggregate result cannot hide tier/resource/tail failures. STOP algorithmic experiments now regardless of result. No v3, no retuning. Next stages:final literature/novelty check,contribution framing,SOVEREIGN mapping,paper writing,venue selection.

Reproduce:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_jointsla_v2.py --development --reuse-results
.venv\Scripts\python.exe run_jointsla_v2.py --freeze
.venv\Scripts\python.exe run_jointsla_v2.py --held-out --reuse-results
```

To regenerate the same frozen simulations use --development --force and --held-out --force sequentially; --force does not bypass source/config/seed guards or erase previous validation history. Fresh checkout:complete development first,then freeze,then held-out. Development after existing freeze is replication only; no redesign.
