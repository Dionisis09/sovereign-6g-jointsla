# Research Question

How does JointSLA relative performance change with increasing hardware-grounded offered load? No statistically supported SLA-breach crossover was observed on the predefined 0.50×–2.00× grid.

# Frozen Hardware Baseline

The DIRECT result and all old profiles/controllers remain frozen. 1× reproduces DIRECT seeds 1/2/3: 54 exported physical/event trace tables, exact traffic/workload hashes; only nondeterministic timings excluded. No hardware was profiled again. One laptop GPU grounds isolated model stages, not ten physical deployed GPUs.

# Load Scaling Method

Conditional intensity λ_m=mλ_original. Thin whole existing compound-Poisson batches with independent shared uniform marks for m<1; superpose independent compound-Poisson batches at (m−1)λ for m>1. Keep original seeded noise and burst masks exactly. 1× returns the exact original tape. Separate keyed adapter RNG streams; original streams untouched. Service base rates, reservations and initial controller rates remain frozen. Thus changed offered arrivals, rather than updated initial priors, drive adaptation. Expected service/tier/model traffic proportions preserved, observed proportions retain sampling noise.

# Fairness and Hash Validation

All 210 multiplier/seed pairs use identical request tapes across policies. Per-pair traffic/workload hashes and full generated inputs retained. Every exported outcome re-read and independently checked against request, work, deadline, network and pipeline sums; every routing score/choice audited by the frozen independent reference. Protected baseline hashes verified before and after. See `validation.json`, `direct_reproduction.json`, `statistical_validation.json`.

# Pressure Characterization

| load_multiplier | policy | offered_requests_per_slot | completed_requests_per_slot_within_horizon | arrival_cohort_completed_per_slot | average_active_replicas_per_service | mean_queue_per_service | resource_saturation_frequency | fraction_slots_no_feasible_scaleout | fraction_slots_no_capacity_feasible_scaleout | realized_request_wait_fraction | realized_node_contention_fraction | routing_under_contention_fraction | action_budget_exhausted_fraction | mean_free_cpu_cores | mean_free_gpu_units | mean_free_vram_gib | average_cpu_utilization | average_gpu_utilization | pool_vram_occupancy_fraction | expected_gpu_offered_pressure | expected_cpu_offered_pressure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.5 | joint_sla | 58.62 | 58.46 | 58.62 | 1.026 | 0.5353 | 0.0004 | 0 | 0 | 0.6779 | 0.04662 | 0.9804 | 0.066 | 10.39 | 2.19 | 24.54 | 0.01803 | 0.138 | 0.0238 | 0.1329 | 0.01803 |
| 0.5 | sla_aware | 58.62 | 58.49 | 58.62 | 1.536 | 0.2869 | 0.0007 | 0.01233 | 0.012 | 0.5411 | 0.07771 | NA | 0.886 | 10.38 | 2.183 | 24.2 | 0.01798 | 0.1392 | 0.03719 | 0.1329 | 0.01803 |
| 0.75 | joint_sla | 87.83 | 87.61 | 87.83 | 1.052 | 0.9189 | 0.0061 | 0 | 0 | 0.7244 | 0.08872 | 0.9915 | 0.163 | 10.29 | 2.022 | 24.52 | 0.02703 | 0.2059 | 0.02467 | 0.1993 | 0.02704 |
| 0.75 | sla_aware | 87.83 | 87.62 | 87.83 | 1.6 | 0.5678 | 0.005233 | 0.03833 | 0.03567 | 0.594 | 0.1264 | NA | 0.8137 | 10.29 | 2.017 | 24.16 | 0.02697 | 0.2082 | 0.03892 | 0.1993 | 0.02704 |
| 1 | joint_sla | 116.9 | 116.6 | 116.9 | 1.086 | 1.427 | 0.0206 | 0 | 0 | 0.7587 | 0.1316 | 0.9952 | 0.2757 | 10.2 | 1.862 | 24.49 | 0.03597 | 0.272 | 0.02568 | 0.2658 | 0.03606 |
| 1 | sla_aware | 116.9 | 116.6 | 116.9 | 1.648 | 0.9889 | 0.01883 | 0.08767 | 0.08167 | 0.6412 | 0.1712 | NA | 0.7347 | 10.2 | 1.86 | 24.13 | 0.0359 | 0.2759 | 0.04007 | 0.2658 | 0.03606 |
| 1.25 | joint_sla | 146.3 | 146 | 146.3 | 1.147 | 2.25 | 0.04633 | 0 | 0 | 0.7911 | 0.1755 | 0.9969 | 0.3987 | 10.1 | 1.7 | 24.44 | 0.04504 | 0.3398 | 0.02767 | 0.3322 | 0.04507 |
| 1.25 | sla_aware | 146.3 | 145.9 | 146.3 | 1.688 | 1.914 | 0.04567 | 0.2053 | 0.1963 | 0.6984 | 0.2262 | NA | 0.63 | 10.11 | 1.701 | 24.11 | 0.0449 | 0.3446 | 0.04095 | 0.3322 | 0.04507 |
| 1.5 | joint_sla | 175.3 | 174.9 | 175.3 | 1.229 | 3.389 | 0.082 | 0 | 0 | 0.8193 | 0.2243 | 0.9976 | 0.4667 | 10.01 | 1.536 | 24.39 | 0.05408 | 0.4056 | 0.0299 | 0.3986 | 0.05408 |
| 1.5 | sla_aware | 175.3 | 174.6 | 175.3 | 1.705 | 3.185 | 0.0866 | 0.305 | 0.2857 | 0.7521 | 0.2814 | NA | 0.5387 | 10.01 | 1.541 | 24.1 | 0.05377 | 0.4121 | 0.04123 | 0.3986 | 0.05408 |
| 1.75 | joint_sla | 204.7 | 204 | 204.7 | 1.392 | 4.68 | 0.1303 | 0.008667 | 0.008667 | 0.8364 | 0.2801 | 0.998 | 0.4793 | 9.92 | 1.372 | 24.29 | 0.06306 | 0.4723 | 0.03388 | 0.4651 | 0.0631 |
| 1.75 | sla_aware | 204.7 | 203 | 204.7 | 1.722 | 5.66 | 0.1345 | 0.43 | 0.4027 | 0.795 | 0.3322 | NA | 0.4333 | 9.915 | 1.383 | 24.08 | 0.06253 | 0.4772 | 0.04205 | 0.4651 | 0.0631 |
| 2 | joint_sla | 234.2 | 232.8 | 234.2 | 1.554 | 6.679 | 0.1863 | 0.1023 | 0.1013 | 0.8581 | 0.3416 | 0.9982 | 0.3917 | 9.829 | 1.214 | 24.19 | 0.07192 | 0.5376 | 0.03781 | 0.5315 | 0.07211 |
| 2 | sla_aware | 234.2 | 230.3 | 234.2 | 1.733 | 10.38 | 0.1867 | 0.5693 | 0.5657 | 0.8365 | 0.3781 | NA | 0.3233 | 9.834 | 1.22 | 24.08 | 0.07093 | 0.5399 | 0.04207 | 0.5315 | 0.07211 |

Expected offered pressure uses exact class times and conditional rates, with mean work factor1; it is not a queueing prediction. Utilization measured by actual finite-resource integrals, not global-estimator offered diagnostic ratios. Slot-end waiting queues; decision-start active replicas/headroom. Queue occupancy is an absolute count because queues are unbounded. Pure capacity and cooldown/max-replica feasible scale-out flags are separate. Missing baseline routing-contention fraction is NA because it uses FIFO service dispatch, not explicit candidate routing. Shared realized node/service wait measures remain comparable. Per-node profiles in `node_pressure_characterization.csv`; full per-slot CPU/GPU/VRAM in each run.

# SLA Results Across Load

| load_multiplier | policy | sla_breach_rate |
| --- | --- | --- |
| 0.5 | joint_sla | 0.231 |
| 0.5 | sla_aware | 0.1026 |
| 0.75 | joint_sla | 0.2401 |
| 0.75 | sla_aware | 0.1258 |
| 1 | joint_sla | 0.2548 |
| 1 | sla_aware | 0.1543 |
| 1.25 | joint_sla | 0.2892 |
| 1.25 | sla_aware | 0.2084 |
| 1.5 | joint_sla | 0.3362 |
| 1.5 | sla_aware | 0.2725 |
| 1.75 | joint_sla | 0.3677 |
| 1.75 | sla_aware | 0.3434 |
| 2 | joint_sla | 0.4153 |
| 2 | sla_aware | 0.431 |

SLA fractions over all offered requests; multiply by 100 for percent. No statistically supported SLA-breach crossover was observed on the predefined 0.50×–2.00× grid.

# Mean Latency

| load_multiplier | policy | mean_request_latency_ms |
| --- | --- | --- |
| 0.5 | joint_sla | 53.28 |
| 0.5 | sla_aware | 34.83 |
| 0.75 | joint_sla | 56.28 |
| 0.75 | sla_aware | 40.94 |
| 1 | joint_sla | 61.89 |
| 1 | sla_aware | 48.77 |
| 1.25 | joint_sla | 74.03 |
| 1.25 | sla_aware | 67.79 |
| 1.5 | joint_sla | 89.79 |
| 1.5 | sla_aware | 88.65 |
| 1.75 | joint_sla | 104.5 |
| 1.75 | sla_aware | 128.6 |
| 2 | joint_sla | 129.1 |
| 2 | sla_aware | 206 |

Request-weighted within seed, seed-weighted across Monte Carlo trials.

# p95 / p99

| load_multiplier | policy | p95_latency_ms | p99_latency_ms |
| --- | --- | --- | --- |
| 0.5 | joint_sla | 172.9 | 256.3 |
| 0.5 | sla_aware | 113.2 | 215 |
| 0.75 | joint_sla | 197.4 | 302.2 |
| 0.75 | sla_aware | 147.4 | 317.5 |
| 1 | joint_sla | 226.4 | 377.1 |
| 1 | sla_aware | 188.7 | 410.3 |
| 1.25 | joint_sla | 280.7 | 480.6 |
| 1.25 | sla_aware | 290.7 | 614.8 |
| 1.5 | joint_sla | 343.4 | 574.3 |
| 1.5 | sla_aware | 387.1 | 737.9 |
| 1.75 | joint_sla | 404.1 | 666.3 |
| 1.75 | sla_aware | 572.2 | 1096 |
| 2 | joint_sla | 499.2 | 866.6 |
| 2 | sla_aware | 975.8 | 1785 |

Linear request quantiles, averaged across seeds; tail improvements may disagree with mean/SLA. Metric-specific supported crossover brackets: {"mean_request_latency_ms": {"equivalence_claim": false, "observed_mean_sign_crossing_intervals": [[1.5, 1.75]], "supported_crossing_intervals": [[1.25, 1.75]], "supported_crossover": true, "threshold": "exploratory observed grid bracket; no interpolated threshold"}, "p95_latency_ms": {"equivalence_claim": false, "observed_mean_sign_crossing_intervals": [[1.0, 1.25]], "supported_crossing_intervals": [[1.0, 1.75]], "supported_crossover": true, "threshold": "exploratory observed grid bracket; no interpolated threshold"}, "p99_latency_ms": {"equivalence_claim": false, "observed_mean_sign_crossing_intervals": [[0.5, 0.75]], "supported_crossing_intervals": [[0.5, 1.25]], "supported_crossover": true, "threshold": "exploratory observed grid bracket; no interpolated threshold"}, "sla_breach_rate": {"equivalence_claim": false, "observed_mean_sign_crossing_intervals": [[1.75, 2.0]], "supported_crossing_intervals": [], "supported_crossover": false, "threshold": "exploratory observed grid bracket; no interpolated threshold"}}. Brackets span opposite supported grid points, allowing statistically unresolved intermediate points; no exact continuous threshold is estimated.

# Crossover Analysis

No statistically supported SLA-breach crossover was observed on the predefined 0.50×–2.00× grid.

{
  "PS1_low_load_SLA_aware_supported": true,
  "PS4_descriptive_supported": true,
  "PS4_lower_resource_regime_counts": {
    "average_replicas": 7,
    "average_vram_residency_gib": 7,
    "total_actions": 5
  },
  "PS5_equal_tapes_and_profiles": true,
  "delta_sla_trend_slope_per_load_unit": -0.09271748292826726,
  "equivalence_claim": false,
  "metric_specific_crossovers": {
    "mean_request_latency_ms": {
      "equivalence_claim": false,
      "observed_mean_sign_crossing_intervals": [
        [
          1.5,
          1.75
        ]
      ],
      "supported_crossing_intervals": [
        [
          1.25,
          1.75
        ]
      ],
      "supported_crossover": true,
      "threshold": "exploratory observed grid bracket; no interpolated threshold"
    },
    "p95_latency_ms": {
      "equivalence_claim": false,
      "observed_mean_sign_crossing_intervals": [
        [
          1.0,
          1.25
        ]
      ],
      "supported_crossing_intervals": [
        [
          1.0,
          1.75
        ]
      ],
      "supported_crossover": true,
      "threshold": "exploratory observed grid bracket; no interpolated threshold"
    },
    "p99_latency_ms": {
      "equivalence_claim": false,
      "observed_mean_sign_crossing_intervals": [
        [
          0.5,
          0.75
        ]
      ],
      "supported_crossing_intervals": [
        [
          0.5,
          1.25
        ]
      ],
      "supported_crossover": true,
      "threshold": "exploratory observed grid bracket; no interpolated threshold"
    },
    "sla_breach_rate": {
      "equivalence_claim": false,
      "observed_mean_sign_crossing_intervals": [
        [
          1.75,
          2.0
        ]
      ],
      "supported_crossing_intervals": [],
      "supported_crossover": false,
      "threshold": "exploratory observed grid bracket; no interpolated threshold"
    }
  },
  "observed_mean_sign_crossing_intervals": [
    [
      1.75,
      2.0
    ]
  ],
  "representative_seeds": {
    "best": 28,
    "median": 25,
    "worst": 21
  },
  "supported_crossing_intervals": [],
  "supported_crossover": false,
  "threshold": "exploratory observed grid bracket; no interpolated threshold",
  "trend_ci95": [
    -0.10485418327964574,
    -0.08094115884770545
  ]
}

A narrower gap is not a crossover. Observed sign-only transitions, if any, are exploratory without both supported directions.

# Tier-Specific Behavior

| load_multiplier | tier | delta_joint_minus_sla | delta_ci95_lower | delta_ci95_upper | p_value_holm | supported_direction |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | Bronze | 0.04916 | 0.0413 | 0.05736 | 3.912e-08 | SLA-aware |
| 0.5 | Gold | 0.1865 | 0.1686 | 0.2063 | 3.912e-08 | SLA-aware |
| 0.5 | Silver | 0.1442 | 0.1315 | 0.1567 | 3.912e-08 | SLA-aware |
| 0.75 | Bronze | 0.03879 | 0.02301 | 0.05451 | 0.0009574 | SLA-aware |
| 0.75 | Gold | 0.1583 | 0.1375 | 0.1795 | 3.912e-08 | SLA-aware |
| 0.75 | Silver | 0.1418 | 0.1272 | 0.1561 | 3.912e-08 | SLA-aware |
| 1 | Bronze | 0.03025 | 0.01264 | 0.04631 | 0.002666 | SLA-aware |
| 1 | Gold | 0.1334 | 0.1153 | 0.1511 | 3.912e-08 | SLA-aware |
| 1 | Silver | 0.1343 | 0.119 | 0.1492 | 3.912e-08 | SLA-aware |
| 1.25 | Bronze | 0.003772 | -0.01705 | 0.02386 | 0.5291 | unresolved |
| 1.25 | Gold | 0.1304 | 0.1083 | 0.1524 | 3.912e-08 | SLA-aware |
| 1.25 | Silver | 0.1047 | 0.08541 | 0.1233 | 7.451e-08 | SLA-aware |
| 1.5 | Bronze | -0.02493 | -0.05084 | -7.914e-06 | 0.3012 | unresolved |
| 1.5 | Gold | 0.1135 | 0.09388 | 0.1326 | 3.912e-08 | SLA-aware |
| 1.5 | Silver | 0.09714 | 0.07124 | 0.1224 | 2.699e-06 | SLA-aware |
| 1.75 | Bronze | -0.1074 | -0.1352 | -0.08171 | 3.912e-08 | JointSLA |
| 1.75 | Gold | 0.1084 | 0.09311 | 0.1238 | 3.912e-08 | SLA-aware |
| 1.75 | Silver | 0.0648 | 0.03777 | 0.09114 | 0.0005942 | SLA-aware |
| 2 | Bronze | -0.1679 | -0.2029 | -0.1333 | 3.912e-08 | JointSLA |
| 2 | Gold | 0.09454 | 0.07695 | 0.1123 | 3.912e-08 | SLA-aware |
| 2 | Silver | 0.01771 | -0.002485 | 0.03764 | 0.3012 | unresolved |

Exploratory family of 21 tests. All Gold/Silver/Bronze retained; different signs are disclosed without claiming a continuous threshold.

# Model-Class Behavior

| load_multiplier | model_class | delta_joint_minus_sla | delta_ci95_lower | delta_ci95_upper | p_value_holm | supported_direction |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | HEAVY | 0.1384 | 0.122 | 0.155 | 3.912e-08 | SLA-aware |
| 0.5 | LIGHT | 0.1266 | 0.1163 | 0.1373 | 3.912e-08 | SLA-aware |
| 0.5 | MEDIUM | 0.1249 | 0.1119 | 0.1388 | 3.912e-08 | SLA-aware |
| 0.75 | HEAVY | 0.1252 | 0.09638 | 0.1531 | 5.122e-07 | SLA-aware |
| 0.75 | LIGHT | 0.1079 | 0.09187 | 0.1238 | 3.912e-08 | SLA-aware |
| 0.75 | MEDIUM | 0.1156 | 0.1008 | 0.1302 | 3.912e-08 | SLA-aware |
| 1 | HEAVY | 0.1253 | 0.1015 | 0.1502 | 3.912e-08 | SLA-aware |
| 1 | LIGHT | 0.0924 | 0.07477 | 0.1084 | 2.235e-07 | SLA-aware |
| 1 | MEDIUM | 0.09788 | 0.08198 | 0.1143 | 3.912e-08 | SLA-aware |
| 1.25 | HEAVY | 0.1182 | 0.097 | 0.1411 | 3.912e-08 | SLA-aware |
| 1.25 | LIGHT | 0.06686 | 0.04972 | 0.08375 | 9.22e-07 | SLA-aware |
| 1.25 | MEDIUM | 0.0748 | 0.05804 | 0.09147 | 6.147e-07 | SLA-aware |
| 1.5 | HEAVY | 0.1033 | 0.08234 | 0.1248 | 4.843e-08 | SLA-aware |
| 1.5 | LIGHT | 0.0607 | 0.03571 | 0.08598 | 0.000494 | SLA-aware |
| 1.5 | MEDIUM | 0.04737 | 0.02755 | 0.0663 | 0.000494 | SLA-aware |
| 1.75 | HEAVY | 0.084 | 0.05289 | 0.1142 | 0.0001278 | SLA-aware |
| 1.75 | LIGHT | 0.004905 | -0.01663 | 0.02622 | 1 | unresolved |
| 1.75 | MEDIUM | 0.01205 | -0.01324 | 0.03785 | 1 | unresolved |
| 2 | HEAVY | 0.005868 | -0.02778 | 0.03877 | 1 | unresolved |
| 2 | LIGHT | -0.01748 | -0.03941 | 0.004117 | 0.6824 | unresolved |
| 2 | MEDIUM | -0.02409 | -0.05001 | 0.002686 | 0.502 | unresolved |

LIGHT/MEDIUM/HEAVY mapping remains 16/16/8. These describe architecture/memory classes; actual measured GPU execution ordering need not increase with class.

# Replica Scaling

| load_multiplier | policy | average_replicas | peak_replicas | cold_starts | scale_outs | scale_ins |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | joint_sla | 41.41 | 45.97 | 16.77 | 16.77 | 16.27 |
| 0.5 | sla_aware | 63.78 | 71.93 | 106.5 | 106.5 | 81.47 |
| 0.75 | joint_sla | 42.71 | 52.53 | 28.27 | 28.27 | 27.2 |
| 0.75 | sla_aware | 66.37 | 73.5 | 103.9 | 103.9 | 75.4 |
| 1 | joint_sla | 44.31 | 57.87 | 38.83 | 38.83 | 37.73 |
| 1 | sla_aware | 68.13 | 74.77 | 97.9 | 97.9 | 67.33 |
| 1.25 | joint_sla | 47.08 | 61.47 | 50.9 | 50.9 | 47.17 |
| 1.25 | sla_aware | 69.57 | 75.2 | 88.93 | 88.93 | 56.8 |
| 1.5 | joint_sla | 50.57 | 64.13 | 58.33 | 58.33 | 49.57 |
| 1.5 | sla_aware | 70.11 | 75.07 | 80.53 | 80.53 | 47.8 |
| 1.75 | joint_sla | 57.29 | 69 | 62.73 | 62.73 | 43.43 |
| 1.75 | sla_aware | 70.61 | 75.27 | 69.57 | 69.57 | 35.8 |
| 2 | joint_sla | 63.71 | 73.1 | 57.9 | 57.9 | 29.3 |
| 2 | sla_aware | 70.78 | 74.97 | 55.63 | 55.63 | 22 |

Average allocated count is exact integral, including cold/retiring replicas; ready replicas separately observed. Peak allocated count sampled at slot ends, unchanged definition.

# VRAM and Resource Use

| load_multiplier | policy | average_vram_residency_gib | peak_pool_vram_gib | average_cpu_utilization | average_gpu_utilization | total_actions | migrations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.5 | joint_sla | 5.974 | 6.997 | 0.01803 | 0.138 | 33.1 | 0.06667 |
| 0.5 | sla_aware | 9.344 | 10.92 | 0.01798 | 0.1392 | 188.1 | 0.1333 |
| 0.75 | joint_sla | 6.194 | 8.05 | 0.02703 | 0.2059 | 56.73 | 1.267 |
| 0.75 | sla_aware | 9.774 | 11.28 | 0.02697 | 0.2082 | 180.2 | 0.9667 |
| 1 | joint_sla | 6.447 | 8.805 | 0.03597 | 0.272 | 80.1 | 3.533 |
| 1 | sla_aware | 10.06 | 11.43 | 0.0359 | 0.2759 | 167.5 | 2.267 |
| 1.25 | joint_sla | 6.948 | 9.534 | 0.04504 | 0.3398 | 105.8 | 7.7 |
| 1.25 | sla_aware | 10.28 | 11.5 | 0.0449 | 0.3446 | 148.8 | 3.067 |
| 1.5 | joint_sla | 7.505 | 10.04 | 0.05408 | 0.4056 | 119.5 | 11.57 |
| 1.5 | sla_aware | 10.35 | 11.51 | 0.05377 | 0.4121 | 131.6 | 3.233 |
| 1.75 | joint_sla | 8.507 | 10.64 | 0.06306 | 0.4723 | 120 | 13.87 |
| 1.75 | sla_aware | 10.56 | 11.7 | 0.06253 | 0.4772 | 108.7 | 3.3 |
| 2 | joint_sla | 9.493 | 11.16 | 0.07192 | 0.5376 | 100.2 | 13 |
| 2 | sla_aware | 10.56 | 11.52 | 0.07093 | 0.5399 | 80.6 | 2.967 |

VRAM integral and simultaneous peak include double reservation during migration. Compute/free-token headroom is different from reserved-capacity headroom.

# Queue Behavior

| load_multiplier | policy | mean_queue_delay_ms | p95_queue_delay_ms | average_queue_length | peak_queue_length |
| --- | --- | --- | --- | --- | --- |
| 0.5 | joint_sla | 36.42 | 151.6 | 21.51 | 91.1 |
| 0.5 | sla_aware | 19.58 | 92.25 | 11.55 | 50.67 |
| 0.75 | joint_sla | 41.76 | 178.4 | 36.9 | 164.3 |
| 0.75 | sla_aware | 26.07 | 126.8 | 22.82 | 90.4 |
| 1 | joint_sla | 48.87 | 209.3 | 57.25 | 254.2 |
| 1 | sla_aware | 33.99 | 169.1 | 39.7 | 155.2 |
| 1.25 | joint_sla | 61.69 | 264.5 | 90.19 | 371.8 |
| 1.25 | sla_aware | 52.83 | 271.8 | 76.85 | 256.9 |
| 1.5 | joint_sla | 77.57 | 328 | 135.8 | 510.6 |
| 1.5 | sla_aware | 73.53 | 368.3 | 127.9 | 385.7 |
| 1.75 | joint_sla | 92 | 388.1 | 187.7 | 664.8 |
| 1.75 | sla_aware | 113.7 | 554.2 | 227.8 | 605.7 |
| 2 | joint_sla | 116 | 482.2 | 268.3 | 844.9 |
| 2 | sla_aware | 191 | 957.1 | 418.6 | 960.6 |

Service and node queue delay summed per request. Unlimited queues fully drained; recovery/queues at the observation horizon remain separately disclosed.

# Burst Recovery

| load_multiplier | policy | bursts | preburst_active_replicas | queue_growth | mean_first_scaleout_delay_slots | scaleout_censored_fraction | mean_cold_delay_ms | mean_recovery_after_burst_slots | recovery_censored_fraction | recovery_window_requests | recovery_window_breaches | recovery_window_breach_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.5 | joint_sla | 120 | 1.011 | 3.934 | 5.803 | 0.8861 | 228.8 | 0.3967 | 0 | 2779 | 831.2 | 0.2986 |
| 0.5 | sla_aware | 120 | 1.536 | 2.388 | 8.763 | 0.6394 | 220.1 | 0.1859 | 0.0002778 | 2746 | 333.5 | 0.121 |
| 0.75 | joint_sla | 120 | 1.016 | 5.906 | 5.077 | 0.8211 | 222.3 | 0.6264 | 0 | 4199 | 1402 | 0.3327 |
| 0.75 | sla_aware | 120 | 1.611 | 3.803 | 9.312 | 0.6414 | 224.6 | 0.3997 | 0.0005556 | 4160 | 696.9 | 0.1664 |
| 1 | joint_sla | 120 | 1.026 | 8.194 | 4.783 | 0.7664 | 221.2 | 0.9217 | 0 | 5670 | 2103 | 0.3694 |
| 1 | sla_aware | 120 | 1.661 | 5.582 | 10.47 | 0.6619 | 216.5 | 0.6913 | 0.0005556 | 5609 | 1221 | 0.216 |
| 1.25 | joint_sla | 120 | 1.061 | 11.23 | 5.077 | 0.7122 | 224.4 | 1.356 | 0.0005556 | 7238 | 3142 | 0.4327 |
| 1.25 | sla_aware | 120 | 1.724 | 8.34 | 11.82 | 0.6967 | 212.5 | 1.294 | 0.006667 | 7232 | 2255 | 0.3094 |
| 1.5 | joint_sla | 120 | 1.129 | 14.79 | 5.306 | 0.6858 | 217.9 | 1.996 | 0.003611 | 8959 | 4571 | 0.5085 |
| 1.5 | sla_aware | 120 | 1.754 | 11.77 | 13.47 | 0.7303 | 215.9 | 1.971 | 0.01889 | 8980 | 3718 | 0.4093 |
| 1.75 | joint_sla | 120 | 1.3 | 18.33 | 5.691 | 0.6817 | 215.6 | 2.647 | 0.01194 | 1.081e+04 | 6031 | 0.5557 |
| 1.75 | sla_aware | 120 | 1.772 | 16.12 | 15.38 | 0.7792 | 214 | 2.736 | 0.05139 | 1.1e+04 | 5673 | 0.512 |
| 2 | joint_sla | 120 | 1.496 | 22.33 | 6.242 | 0.7314 | 204.8 | 3.501 | 0.03778 | 1.289e+04 | 7973 | 0.6168 |
| 2 | sla_aware | 120 | 1.8 | 21.66 | 16.34 | 0.8583 | 213.2 | 3.535 | 0.1072 | 1.334e+04 | 8399 | 0.6254 |

Each service burst is a diagnostic event. Threshold=max(preburst queue,1); recovery searched after burst end before next burst/horizon. Delay means are conditional on observed recovery/scale-out; censoring fractions are mandatory and not imputed. SLA window start→recovery/next burst; overlapping service windows do not duplicate requests across services. Best/median/worst examples selected by sorted DIRECT paired SLA differences, seed as tie-breaker; representative seeds {'best': 28, 'median': 25, 'worst': 21}.

# Performance-Resource Frontier

Three observed traces: SLA vs replicas, p95 vs VRAM, SLA vs actions. Each marker is a distinct load, not an optimized point at equal QoS. Lower cost alongside worse SLA demonstrates a trade-off, not dominance. No convex optimal frontier or budget-matched controller superiority is established.

# Statistical Results

30 paired seeds at every load; seed arithmetic means ± sample SD and percentile bootstrap 95% CI, 10,000 resamples, RNG seed 73001. Wilcoxon two-sided; 12-decimal tie rule, positive rank-biserial effect favors JointSLA. Δ=Joint−SLA, positive worse. Holm: SLA+p95 across seven loads (14 primary), mean+p99 (14 secondary), tier SLA (21 exploratory), class SLA (21 exploratory). No equivalence margin or post-hoc threshold. `summary_statistics.csv` contains means, SD and CIs for all numeric metrics. All arrival-cohort requests including drain are counted; no drops/unplaced requests.

| load_multiplier | metric | delta_joint_minus_sla | delta_ci95_lower | delta_ci95_upper | p_value | p_value_holm | rank_biserial_correlation | wins | ties | losses | supported_direction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.5 | sla_breach_rate | 0.128445 | 0.120392 | 0.136435 | 1.86265e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 | SLA-aware |
| 0.5 | mean_request_latency_ms | 18.4582 | 17.226 | 19.6566 | 1.86265e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 | SLA-aware |
| 0.5 | p95_latency_ms | 59.6469 | 56.2089 | 63.101 | 1.86265e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 | SLA-aware |
| 0.5 | p99_latency_ms | 41.3094 | 28.1337 | 53.4749 | 2.3488e-06 | 1.87904e-05 | -0.883871 | 6 | 0 | 24 | SLA-aware |
| 0.75 | sla_breach_rate | 0.114223 | 0.10221 | 0.125433 | 1.86265e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 | SLA-aware |
| 0.75 | mean_request_latency_ms | 15.341 | 12.5418 | 18.0899 | 9.31323e-09 | 1.11759e-07 | -0.987097 | 2 | 0 | 28 | SLA-aware |
| 0.75 | p95_latency_ms | 49.9846 | 36.2597 | 62.3793 | 1.99117e-06 | 1.1947e-05 | -0.888172 | 3 | 0 | 27 | SLA-aware |
| 0.75 | p99_latency_ms | -15.2828 | -49.4294 | 14.8771 | 0.761065 | 0.879934 | 0.0666667 | 12 | 0 | 18 | unresolved |
| 1 | sla_breach_rate | 0.100539 | 0.0884591 | 0.111758 | 1.86265e-09 | 2.6077e-08 | -1 | 0 | 0 | 30 | SLA-aware |
| 1 | mean_request_latency_ms | 13.1164 | 10.0409 | 16.0964 | 1.30385e-07 | 1.17347e-06 | -0.948387 | 2 | 0 | 28 | SLA-aware |
| 1 | p95_latency_ms | 37.7036 | 20.7473 | 52.6121 | 0.000231637 | 0.00115818 | -0.729032 | 7 | 0 | 23 | SLA-aware |
| 1 | p99_latency_ms | -33.1615 | -78.6616 | 8.1051 | 0.262122 | 0.786367 | 0.23871 | 18 | 0 | 12 | unresolved |
| 1.25 | sla_breach_rate | 0.0807517 | 0.069164 | 0.0926251 | 3.72529e-09 | 3.35276e-08 | -0.995699 | 1 | 0 | 29 | SLA-aware |
| 1.25 | mean_request_latency_ms | 6.23762 | 1.83681 | 10.3934 | 0.00761214 | 0.0304485 | -0.548387 | 8 | 0 | 22 | SLA-aware |
| 1.25 | p95_latency_ms | -9.98208 | -36.5607 | 14.5216 | 0.776569 | 0.776569 | 0.0623656 | 13 | 0 | 17 | unresolved |
| 1.25 | p99_latency_ms | -134.236 | -189.445 | -80.9581 | 6.28661e-05 | 0.000377197 | 0.780645 | 23 | 0 | 7 | JointSLA |
| 1.5 | sla_breach_rate | 0.0636385 | 0.0466699 | 0.0802727 | 5.71832e-07 | 4.00282e-06 | -0.91828 | 3 | 0 | 27 | SLA-aware |
| 1.5 | mean_request_latency_ms | 1.14698 | -6.90305 | 8.29247 | 0.439967 | 0.879934 | -0.165591 | 10 | 0 | 20 | unresolved |
| 1.5 | p95_latency_ms | -43.6311 | -87.0591 | -2.87569 | 0.0961016 | 0.288305 | 0.350538 | 19 | 0 | 11 | unresolved |
| 1.5 | p99_latency_ms | -163.586 | -245.061 | -85.135 | 0.000169897 | 0.000849487 | 0.741935 | 25 | 0 | 5 | JointSLA |
| 1.75 | sla_breach_rate | 0.0243519 | 0.00905565 | 0.03954 | 0.00761214 | 0.0304485 | -0.548387 | 10 | 0 | 20 | SLA-aware |
| 1.75 | mean_request_latency_ms | -24.1017 | -34.1228 | -14.5494 | 2.68854e-05 | 0.000188198 | 0.810753 | 24 | 0 | 6 | JointSLA |
| 1.75 | p95_latency_ms | -168.07 | -219.592 | -120.44 | 1.02445e-07 | 8.19564e-07 | 0.952688 | 28 | 0 | 2 | JointSLA |
| 1.75 | p99_latency_ms | -429.285 | -517.511 | -341.883 | 9.31323e-09 | 1.11759e-07 | 0.987097 | 29 | 0 | 1 | JointSLA |
| 2 | sla_breach_rate | -0.0156815 | -0.0332766 | 0.00258112 | 0.129353 | 0.288305 | 0.32043 | 19 | 0 | 11 | unresolved |
| 2 | mean_request_latency_ms | -76.9108 | -104.763 | -51.3041 | 4.65661e-08 | 4.65661e-07 | 0.965591 | 27 | 0 | 3 | JointSLA |
| 2 | p95_latency_ms | -476.582 | -666.802 | -314.134 | 1.86265e-09 | 2.6077e-08 | 1 | 30 | 0 | 0 | JointSLA |
| 2 | p99_latency_ms | -918.479 | -1251.14 | -625.845 | 1.86265e-09 | 2.6077e-08 | 1 | 30 | 0 | 0 | JointSLA |

# Operating Envelope

| load_multiplier | category | delta_sla | ci_lower | ci_upper | p_holm |
| --- | --- | --- | --- | --- | --- |
| 0.5 | SLA-aware-favored | 0.1284 | 0.1204 | 0.1364 | 2.608e-08 |
| 0.75 | SLA-aware-favored | 0.1142 | 0.1022 | 0.1254 | 2.608e-08 |
| 1 | SLA-aware-favored | 0.1005 | 0.08846 | 0.1118 | 2.608e-08 |
| 1.25 | SLA-aware-favored | 0.08075 | 0.06916 | 0.09263 | 3.353e-08 |
| 1.5 | SLA-aware-favored | 0.06364 | 0.04667 | 0.08027 | 4.003e-06 |
| 1.75 | SLA-aware-favored | 0.02435 | 0.009056 | 0.03954 | 0.03045 |
| 2 | approximately competitive / statistically unresolved | -0.01568 | -0.03328 | 0.002581 | 0.2883 |

Unresolved points are approximately competitive only as a descriptive label; failed rejection does not prove equivalence. Primary SLA label may differ from p95/p99; inspect all four paired rows.

# Negative Results

No statistically supported SLA-breach crossover was observed on the predefined 0.50×–2.00× grid. Every seed and loss retained in `negative_seed_cases.csv`; no tuning, deleting unfavorable points or moving deadlines. Original DIRECT aggregate disadvantage remains valid.

# Threats to Validity

Seven finite load points, one GPU profile set, synthetic nodes/network/concurrency and workload. Controller global timing/cold priors approximate class physics. Extra traffic adapter preserves conditional intensity/cluster law, not identical realized tier fractions or perfect across-load nesting. Shared tapes induce dependence across loads; Holm does not require independence. Unlimited queues, short horizon, slot-quantized cold times, observational burst diagnostics and conditional censoring can limit deployment transfer. Instrumentation timing varies with host load; observational work excluded from the inherited snapshot timers but included in total simulation wall time.

# Safe Paper Claims

No statistically supported SLA-breach crossover was observed on the predefined 0.50×–2.00× grid. This study characterizes a frozen controller’s operating envelope and performance-resource trade-off under hardware-grounded model profiles, with paired seeds and preserved negative results. Metric-specific crossover is essential: the JointSLA mean latency and p95/p99 advantage at 1.75×–2× is supported, while its aggregate breach advantage at 2× is not. Gold remains significantly worse under JointSLA at every tested load; Bronze becomes better at 1.75×–2×. No class-specific JointSLA breach advantage is supported. JointSLA uses fewer replicas/VRAM at all seven loads, but fewer actions at only five loads; its action count exceeds SLA-aware at 1.75×–2×. Mechanism attribution is addressed separately by the factorial diagnostic experiment.

# Claims We Cannot Make

Universal superiority, a crossover beyond the tested grid, formal equivalence at unresolved loads, a real 6G deployment, true optimal frontier, carrier-grade validation, or isolated causal explanation from pressure trends alone. No algorithm improvements were made. Statistical support for p99 does not imply support for breach or p95.
