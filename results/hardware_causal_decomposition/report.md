# Motivation

Diagnose the preserved DIRECT reversal without modifying either controller. Exploratory full 2³ factorial, seeds 1–10 paired within and across D0–D7; every regime identical traffic/deadlines/network/resources except selected E/V/C intervention. Δ=Joint−SLA. Report means ± sample SD and paired descriptive differences; no confirmatory significance claim at N=10. Shapley allocation symmetrically divides anchored interaction contrasts across constituent factors and sums exactly to the observed D7−D0 reversal. Factorial averaged marginals and all pair/triple interactions retained. Not strict external causality.

# Frozen Reference Configurations

D0 uses original MEDIUM synthetic config and uniform workers; D7 matches frozen hardware DIRECT on class execution, memory and readiness. Full sweep 1× seeds1/2/3 reproduced frozen traces. D7 decomposition seeds1–10 also checked against the frozen endpoint; D0 checked against original synthetic results. Controllers and estimator formulas unchanged.

# Decomposition Design

Exploratory full 2³ factorial, seeds 1–10 paired within and across D0–D7; every regime identical traffic/deadlines/network/resources except selected E/V/C intervention. Δ=Joint−SLA. Report means ± sample SD and paired descriptive differences; no confirmatory significance claim at N=10. Shapley allocation symmetrically divides anchored interaction contrasts across constituent factors and sums exactly to the observed D7−D0 reversal. Factorial averaged marginals and all pair/triple interactions retained. Not strict external causality. The execution/cold component includes hardware values in the unchanged global estimator interface and per-class worker physics. Cannot separate estimator mismatch from physical workload effect without another separately designed experiment.

# D0-D7 Definitions

| regime | execution | vram | cold |
| --- | --- | --- | --- |
| D0 | 0 | 0 | 0 |
| D1 | 1 | 0 | 0 |
| D2 | 0 | 1 | 0 |
| D3 | 0 | 0 | 1 |
| D4 | 1 | 1 | 0 |
| D5 | 1 | 0 | 1 |
| D6 | 0 | 1 | 1 |
| D7 | 1 | 1 | 1 |

E=real preprocess+upload / inference / postprocess. V=real peak allocated VRAM. C=real class cold readiness rounded upward to slots. Cold first-request 5ms penalty and 100ms/10ms migration model remain synthetic everywhere. Initial services/tapes stay unchanged.

# Execution-Time Effect

| metric | factor | mean_factorial_marginal | marginal_std | shapley_reversal_contribution | shapley_std | n |
| --- | --- | --- | --- | --- | --- | --- |
| action_budget_exhausted_fraction | execution | -0.3152 | 0.0872 | -0.3097 | 0.08642 | 10 |
| average_active_replicas_per_service | execution | -0.2028 | 0.02942 | -0.1958 | 0.0301 | 10 |
| average_cpu_utilization | execution | -0.0005867 | 0.0004108 | -0.000548 | 0.000414 | 10 |
| average_gpu_utilization | execution | 0.0004576 | 0.002921 | 0.0007355 | 0.003174 | 10 |
| average_queue_length | execution | 25.77 | 36.87 | 22.88 | 36.45 | 10 |
| average_replicas | execution | -8.86 | 1.257 | -8.597 | 1.274 | 10 |
| average_vram_residency_gib | execution | -10.95 | 5.587 | -10.7 | 5.741 | 10 |
| cold_starts | execution | -37.3 | 7.871 | -36.45 | 7.885 | 10 |
| mean_queue_delay_ms | execution | 22.87 | 40.99 | 20.08 | 41.24 | 10 |
| mean_request_latency_ms | execution | 22.27 | 41.28 | 19.48 | 41.43 | 10 |
| migrations | execution | -2.275 | 1.685 | -2.683 | 2.04 | 10 |
| p95_latency_ms | execution | 137.3 | 241.7 | 119.9 | 246.3 | 10 |
| p95_queue_delay_ms | execution | 138.7 | 240.8 | 121.4 | 245.5 | 10 |
| p99_latency_ms | execution | 121.7 | 479.9 | 117.8 | 481.8 | 10 |
| peak_pool_vram_gib | execution | -2.988 | 1.714 | -2.828 | 1.785 | 10 |
| peak_queue_length | execution | 41.08 | 57.24 | 31.98 | 53.49 | 10 |
| peak_replicas | execution | -7.225 | 2.19 | -7.1 | 2.127 | 10 |
| queue_changed_choice_fraction | execution | -0.1004 | 0.01622 | -0.09868 | 0.01652 | 10 |
| scale_ins | execution | -21.5 | 7.7 | -20.82 | 7.469 | 10 |
| scale_outs | execution | -37.3 | 7.871 | -36.45 | 7.885 | 10 |
| sla_breach_rate | execution | 0.01942 | 0.0244 | 0.01578 | 0.02203 | 10 |
| total_actions | execution | -61.08 | 14.91 | -59.95 | 14.64 | 10 |

The E toggle substitutes hardware stage times and the fixed population mean controller stage prior. Shorter inference does not guarantee less total queueing when policy-induced replica counts change.

# VRAM Effect

| metric | factor | mean_factorial_marginal | marginal_std | shapley_reversal_contribution | shapley_std | n |
| --- | --- | --- | --- | --- | --- | --- |
| action_budget_exhausted_fraction | vram | -0.03125 | 0.05139 | -0.02567 | 0.05211 | 10 |
| average_active_replicas_per_service | vram | -0.2859 | 0.09169 | -0.2789 | 0.08975 | 10 |
| average_cpu_utilization | vram | -0.0001277 | 0.0005754 | -8.897e-05 | 0.0005838 | 10 |
| average_gpu_utilization | vram | -0.003825 | 0.003414 | -0.003547 | 0.003627 | 10 |
| average_queue_length | vram | 32.63 | 25.72 | 29.75 | 24.99 | 10 |
| average_replicas | vram | -11.67 | 3.751 | -11.41 | 3.678 | 10 |
| average_vram_residency_gib | vram | 14.96 | 9.793 | 15.21 | 9.687 | 10 |
| cold_starts | vram | -8.35 | 4.953 | -7.5 | 4.865 | 10 |
| mean_queue_delay_ms | vram | 28.14 | 30.07 | 25.34 | 29.85 | 10 |
| mean_request_latency_ms | vram | 27.79 | 30.52 | 25 | 30.28 | 10 |
| migrations | vram | 2.575 | 1.472 | 2.167 | 1.199 | 10 |
| p95_latency_ms | vram | 112.9 | 177.1 | 95.47 | 175.1 | 10 |
| p95_queue_delay_ms | vram | 113.7 | 175.3 | 96.4 | 173.2 | 10 |
| p99_latency_ms | vram | 25.69 | 388.4 | 21.77 | 393.7 | 10 |
| peak_pool_vram_gib | vram | 1.989 | 2.144 | 2.15 | 2.182 | 10 |
| peak_queue_length | vram | 93.92 | 36.83 | 84.83 | 43.92 | 10 |
| peak_replicas | vram | -7.825 | 3.186 | -7.7 | 3.093 | 10 |
| queue_changed_choice_fraction | vram | 0.01946 | 0.02456 | 0.0212 | 0.024 | 10 |
| scale_ins | vram | 4.6 | 6.009 | 5.283 | 5.904 | 10 |
| scale_outs | vram | -8.35 | 4.953 | -7.5 | 4.865 | 10 |
| sla_breach_rate | vram | 0.07941 | 0.01893 | 0.07577 | 0.02021 | 10 |
| total_actions | vram | -1.175 | 10.67 | -0.05 | 10.34 | 10 |

Only reservation footprint changes. Actual concurrency remains finite and unchanged; VRAM alone is not throughput.

# Cold-Start Effect

| metric | factor | mean_factorial_marginal | marginal_std | shapley_reversal_contribution | shapley_std | n |
| --- | --- | --- | --- | --- | --- | --- |
| action_budget_exhausted_fraction | cold | -0.1303 | 0.04073 | -0.1247 | 0.03893 | 10 |
| average_active_replicas_per_service | cold | -0.06215 | 0.01024 | -0.05512 | 0.009161 | 10 |
| average_cpu_utilization | cold | 9.801e-05 | 0.0003299 | 0.0001367 | 0.0004122 | 10 |
| average_gpu_utilization | cold | 0.00021 | 0.002209 | 0.0004878 | 0.002732 | 10 |
| average_queue_length | cold | 14.63 | 10.85 | 11.74 | 9.323 | 10 |
| average_replicas | cold | -2.859 | 0.4324 | -2.595 | 0.4027 | 10 |
| average_vram_residency_gib | cold | -3.475 | 1.215 | -3.221 | 0.9634 | 10 |
| cold_starts | cold | -15.4 | 2.777 | -14.55 | 2.744 | 10 |
| mean_queue_delay_ms | cold | 11.77 | 10.77 | 8.976 | 10.68 | 10 |
| mean_request_latency_ms | cold | 12.41 | 11 | 9.617 | 10.81 | 10 |
| migrations | cold | 2.725 | 1.493 | 2.317 | 1.406 | 10 |
| p95_latency_ms | cold | 36.81 | 68.45 | 19.33 | 62.84 | 10 |
| p95_queue_delay_ms | cold | 36.01 | 67.21 | 18.66 | 61.4 | 10 |
| p99_latency_ms | cold | 94.53 | 192.8 | 90.61 | 189 | 10 |
| peak_pool_vram_gib | cold | -1.413 | 1.566 | -1.253 | 1.214 | 10 |
| peak_queue_length | cold | 65.78 | 27.38 | 56.68 | 30.47 | 10 |
| peak_replicas | cold | -1.925 | 0.8084 | -1.8 | 0.9189 | 10 |
| queue_changed_choice_fraction | cold | -0.02314 | 0.008056 | -0.0214 | 0.007109 | 10 |
| scale_ins | cold | -14.25 | 3.793 | -13.57 | 3.552 | 10 |
| scale_outs | cold | -15.4 | 2.777 | -14.55 | 2.744 | 10 |
| sla_breach_rate | cold | 0.05102 | 0.02213 | 0.04738 | 0.01938 | 10 |
| total_actions | cold | -26.93 | 6.677 | -25.8 | 6.212 | 10 |

Synthetic readiness 1 slot; measured classes 1/2/5 slots. Slow relative recovery is physically grounded but slot-quantized; extra first-request penalty unchanged. Each effect depends on other components.

# Combined Effects

| regime | metric | n | mean_sla_aware | mean_joint_sla | delta_joint_minus_sla | delta_std | wins | ties | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D0 | sla_breach_rate | 10 | 0.6064 | 0.5766 | -0.02983 | 0.02833 | 9 | 0 | 1 |
| D0 | mean_request_latency_ms | 10 | 312.9 | 273 | -39.96 | 78.92 | 8 | 0 | 2 |
| D0 | p95_latency_ms | 10 | 1278 | 1081 | -197.1 | 457.9 | 8 | 0 | 2 |
| D0 | p99_latency_ms | 10 | 2163 | 1903 | -260.6 | 946.6 | 8 | 0 | 2 |
| D1 | sla_breach_rate | 10 | 0.3458 | 0.2903 | -0.05548 | 0.02471 | 10 | 0 | 0 |
| D1 | mean_request_latency_ms | 10 | 108.9 | 78.84 | -30.02 | 13.23 | 10 | 0 | 0 |
| D1 | p95_latency_ms | 10 | 465.8 | 294.7 | -171 | 99.95 | 9 | 0 | 1 |
| D1 | p99_latency_ms | 10 | 829.8 | 514.4 | -315.4 | 200.3 | 9 | 0 | 1 |
| D2 | sla_breach_rate | 10 | 0.3978 | 0.3944 | -0.003342 | 0.03346 | 4 | 0 | 6 |
| D2 | mean_request_latency_ms | 10 | 127.9 | 97.1 | -30.84 | 22.58 | 10 | 0 | 0 |
| D2 | p95_latency_ms | 10 | 538.2 | 323.3 | -215 | 143.5 | 10 | 0 | 0 |
| D2 | p99_latency_ms | 10 | 976.9 | 573.5 | -403.5 | 244.8 | 10 | 0 | 0 |
| D3 | sla_breach_rate | 10 | 0.6176 | 0.5964 | -0.02121 | 0.02949 | 9 | 0 | 1 |
| D3 | mean_request_latency_ms | 10 | 321.9 | 275.5 | -46.47 | 64.87 | 9 | 0 | 1 |
| D3 | p95_latency_ms | 10 | 1322 | 1050 | -272.3 | 357.6 | 9 | 0 | 1 |
| D3 | p99_latency_ms | 10 | 2098 | 1908 | -189.9 | 799.1 | 8 | 0 | 2 |
| D4 | sla_breach_rate | 10 | 0.1334 | 0.1709 | 0.03752 | 0.02656 | 1 | 0 | 9 |
| D4 | mean_request_latency_ms | 10 | 43.45 | 43.01 | -0.4422 | 7.473 | 5 | 0 | 5 |
| D4 | p95_latency_ms | 10 | 154.3 | 148 | -6.37 | 37.71 | 5 | 0 | 5 |
| D4 | p99_latency_ms | 10 | 368.7 | 243.4 | -125.3 | 152.4 | 6 | 0 | 4 |
| D5 | sla_breach_rate | 10 | 0.3551 | 0.3537 | -0.001386 | 0.04162 | 5 | 0 | 5 |
| D5 | mean_request_latency_ms | 10 | 113.2 | 97.66 | -15.58 | 17.17 | 8 | 0 | 2 |
| D5 | p95_latency_ms | 10 | 472.1 | 370.7 | -101.4 | 95 | 9 | 0 | 1 |
| D5 | p99_latency_ms | 10 | 820.9 | 619.7 | -201.1 | 165 | 10 | 0 | 0 |
| D6 | sla_breach_rate | 10 | 0.4069 | 0.4733 | 0.06644 | 0.04253 | 0 | 0 | 10 |
| D6 | mean_request_latency_ms | 10 | 131.1 | 127.4 | -3.711 | 21.13 | 6 | 0 | 4 |
| D6 | p95_latency_ms | 10 | 542.6 | 436.4 | -106.2 | 145.8 | 9 | 0 | 1 |
| D6 | p99_latency_ms | 10 | 1009 | 703.6 | -305.2 | 191 | 10 | 0 | 0 |
| D7 | sla_breach_rate | 10 | 0.1517 | 0.2608 | 0.1091 | 0.02358 | 0 | 0 | 10 |
| D7 | mean_request_latency_ms | 10 | 48.54 | 62.68 | 14.14 | 7.034 | 0 | 0 | 10 |
| D7 | p95_latency_ms | 10 | 190 | 227.6 | 37.59 | 52.27 | 2 | 0 | 8 |
| D7 | p99_latency_ms | 10 | 417.5 | 387.1 | -30.36 | 105.4 | 6 | 0 | 4 |

Original and fully calibrated endpoint gaps are compared on the same ten seeds, not cross-population seed averages.

# Queue Pressure

| regime | hardware_gpu_pressure | hardware_cpu_pressure | initial_vram_pressure |
| --- | --- | --- | --- |
| D0 | 0.4614 | 0.1001 | 0.74 |
| D1 | 0.2627 | 0.03557 | 0.74 |
| D2 | 0.4614 | 0.1001 | 0.02269 |
| D3 | 0.4614 | 0.1001 | 0.74 |
| D4 | 0.2627 | 0.03557 | 0.02269 |
| D5 | 0.2627 | 0.03557 | 0.74 |
| D6 | 0.4614 | 0.1001 | 0.02269 |
| D7 | 0.2627 | 0.03557 | 0.02269 |

| regime | policy | mean_queue_delay_ms | average_queue_length | average_replicas | average_active_replicas_per_service | scale_outs | scale_ins | cold_starts | action_budget_exhausted_fraction | queue_changed_choice_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D0 | joint_sla | 248.8 | 256.2 | 51.78 | 1.281 | 39.3 | 26.2 | 39.3 | 0.201 | 0.1275 |
| D0 | sla_aware | 287.5 | 302.1 | 53.44 | 1.322 | 41.5 | 28.2 | 41.5 | 0.207 | 0 |
| D1 | joint_sla | 63.79 | 73.31 | 45.97 | 1.135 | 55.9 | 52.9 | 55.9 | 0.361 | 0.0566 |
| D1 | sla_aware | 91.13 | 104.3 | 52.5 | 1.292 | 71.1 | 58 | 71.1 | 0.452 | 0 |
| D2 | joint_sla | 76.29 | 87.73 | 63.34 | 1.556 | 82.7 | 56.4 | 82.7 | 0.592 | 0.1864 |
| D2 | sla_aware | 104.6 | 119.4 | 70.92 | 1.747 | 70.2 | 37.3 | 70.2 | 0.425 | 0 |
| D3 | joint_sla | 251.1 | 262.6 | 50.68 | 1.247 | 34.6 | 21.7 | 34.6 | 0.146 | 0.1107 |
| D3 | sla_aware | 296.3 | 311.8 | 53.57 | 1.316 | 41.2 | 27.7 | 41.2 | 0.199 | 0 |
| D4 | joint_sla | 31.45 | 36.59 | 46.26 | 1.141 | 60.5 | 58.9 | 60.5 | 0.473 | 0.04765 |
| D4 | sla_aware | 28.98 | 33.43 | 67.61 | 1.658 | 99.9 | 69.6 | 99.9 | 0.759 | 0 |
| D5 | joint_sla | 81.94 | 94.46 | 44.46 | 1.093 | 36.5 | 34.3 | 36.5 | 0.188 | 0.03816 |
| D5 | sla_aware | 95.38 | 109.7 | 52.88 | 1.284 | 70.9 | 57.6 | 70.9 | 0.452 | 0 |
| D6 | joint_sla | 105.7 | 121.7 | 58.03 | 1.409 | 67.7 | 43.3 | 67.7 | 0.489 | 0.1481 |
| D6 | sla_aware | 107.6 | 122.6 | 71.02 | 1.732 | 71.9 | 38.6 | 71.9 | 0.443 | 0 |
| D7 | joint_sla | 49.51 | 57.45 | 44.09 | 1.083 | 38.3 | 37.4 | 38.3 | 0.278 | 0.02865 |
| D7 | sla_aware | 33.83 | 39.01 | 68.35 | 1.653 | 99 | 68.5 | 99 | 0.744 | 0 |

Offered ratios use per-class physical times. `queue_changed_choice_fraction` is a retrospective candidate-choice diagnostic, not a causal no-queue ablation. Lower value does not establish lower benefit of queue-aware routing. Action-budget exhaustion is a descriptive frequency, not proof that a larger budget would fix SLA.

# Replica Dynamics

| regime | metric | n | mean_sla_aware | mean_joint_sla | delta_joint_minus_sla | delta_std | wins | ties | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D0 | average_replicas | 10 | 53.44 | 51.78 | -1.662 | 1.254 | 9 | 0 | 1 |
| D0 | average_vram_residency_gib | 10 | 240.2 | 235.4 | -4.866 | 4.628 | 10 | 0 | 0 |
| D0 | cold_starts | 10 | 41.5 | 39.3 | -2.2 | 6.795 | 6 | 0 | 4 |
| D0 | scale_outs | 10 | 41.5 | 39.3 | -2.2 | 6.795 | 6 | 0 | 4 |
| D0 | scale_ins | 10 | 28.2 | 26.2 | -2 | 6.96 | 6 | 1 | 3 |
| D0 | total_actions | 10 | 69.8 | 65.5 | -4.3 | 13.58 | 6 | 0 | 4 |
| D1 | average_replicas | 10 | 52.5 | 45.97 | -6.528 | 3.902 | 10 | 0 | 0 |
| D1 | average_vram_residency_gib | 10 | 236.2 | 212.7 | -23.54 | 15.49 | 10 | 0 | 0 |
| D1 | cold_starts | 10 | 71.1 | 55.9 | -15.2 | 6.143 | 10 | 0 | 0 |
| D1 | scale_outs | 10 | 71.1 | 55.9 | -15.2 | 6.143 | 10 | 0 | 0 |
| D1 | scale_ins | 10 | 58 | 52.9 | -5.1 | 8.875 | 6 | 0 | 4 |
| D1 | total_actions | 10 | 129.2 | 108.8 | -20.4 | 13.38 | 10 | 0 | 0 |
| D2 | average_replicas | 10 | 70.92 | 63.34 | -7.582 | 3.008 | 10 | 0 | 0 |
| D2 | average_vram_residency_gib | 10 | 10.1 | 9.04 | -1.056 | 0.6891 | 10 | 0 | 0 |
| D2 | cold_starts | 10 | 70.2 | 82.7 | 12.5 | 6.621 | 1 | 0 | 9 |
| D2 | scale_outs | 10 | 70.2 | 82.7 | 12.5 | 6.621 | 1 | 0 | 9 |
| D2 | scale_ins | 10 | 37.3 | 56.4 | 19.1 | 2.998 | 0 | 0 | 10 |
| D2 | total_actions | 10 | 108.1 | 141.1 | 33 | 10.27 | 0 | 0 | 10 |
| D3 | average_replicas | 10 | 53.57 | 50.68 | -2.883 | 1.825 | 10 | 0 | 0 |
| D3 | average_vram_residency_gib | 10 | 240.5 | 230.7 | -9.714 | 5.795 | 10 | 0 | 0 |
| D3 | cold_starts | 10 | 41.2 | 34.6 | -6.6 | 5.103 | 10 | 0 | 0 |
| D3 | scale_outs | 10 | 41.2 | 34.6 | -6.6 | 5.103 | 10 | 0 | 0 |
| D3 | scale_ins | 10 | 27.7 | 21.7 | -6 | 5.793 | 8 | 1 | 1 |
| D3 | total_actions | 10 | 69.5 | 57.8 | -11.7 | 11.7 | 9 | 0 | 1 |
| D4 | average_replicas | 10 | 67.61 | 46.26 | -21.35 | 2.915 | 10 | 0 | 0 |
| D4 | average_vram_residency_gib | 10 | 9.603 | 6.605 | -2.998 | 0.4454 | 10 | 0 | 0 |
| D4 | cold_starts | 10 | 99.9 | 60.5 | -39.4 | 9.891 | 10 | 0 | 0 |
| D4 | scale_outs | 10 | 99.9 | 60.5 | -39.4 | 9.891 | 10 | 0 | 0 |
| D4 | scale_ins | 10 | 69.6 | 58.9 | -10.7 | 9.9 | 8 | 0 | 2 |
| D4 | total_actions | 10 | 169.8 | 119.4 | -50.4 | 19.03 | 10 | 0 | 0 |
| D5 | average_replicas | 10 | 52.88 | 44.46 | -8.419 | 4.024 | 10 | 0 | 0 |
| D5 | average_vram_residency_gib | 10 | 237.1 | 205.8 | -31.2 | 15.13 | 10 | 0 | 0 |
| D5 | cold_starts | 10 | 70.9 | 36.5 | -34.4 | 10.95 | 10 | 0 | 0 |
| D5 | scale_outs | 10 | 70.9 | 36.5 | -34.4 | 10.95 | 10 | 0 | 0 |
| D5 | scale_ins | 10 | 57.6 | 34.3 | -23.3 | 9.405 | 10 | 0 | 0 |
| D5 | total_actions | 10 | 128.7 | 71.5 | -57.2 | 19.61 | 10 | 0 | 0 |
| D6 | average_replicas | 10 | 71.02 | 58.03 | -12.99 | 3.756 | 10 | 0 | 0 |
| D6 | average_vram_residency_gib | 10 | 10.29 | 8.421 | -1.866 | 0.7127 | 10 | 0 | 0 |
| D6 | cold_starts | 10 | 71.9 | 67.7 | -4.2 | 8.443 | 8 | 0 | 2 |
| D6 | scale_outs | 10 | 71.9 | 67.7 | -4.2 | 8.443 | 8 | 0 | 2 |
| D6 | scale_ins | 10 | 38.6 | 43.3 | 4.7 | 7.009 | 2 | 1 | 7 |
| D6 | total_actions | 10 | 114.2 | 123.4 | 9.2 | 13.86 | 3 | 1 | 6 |
| D7 | average_replicas | 10 | 68.35 | 44.09 | -24.26 | 2.523 | 10 | 0 | 0 |
| D7 | average_vram_residency_gib | 10 | 9.945 | 6.369 | -3.576 | 0.4737 | 10 | 0 | 0 |
| D7 | cold_starts | 10 | 99 | 38.3 | -60.7 | 9.476 | 10 | 0 | 0 |
| D7 | scale_outs | 10 | 99 | 38.3 | -60.7 | 9.476 | 10 | 0 | 0 |
| D7 | scale_ins | 10 | 68.5 | 37.4 | -31.1 | 8.962 | 10 | 0 | 0 |
| D7 | total_actions | 10 | 168.8 | 78.7 | -90.1 | 18.93 | 10 | 0 | 0 |

Do not infer aggressive scale-in solely from lower replica counts: fewer scale-outs, readiness and retiring lifetime can all produce consolidation. Three representative D7 seeds selected by sorted paired ΔSLA, explicitly labeled best/lower-median/worst. Ready and allocated replicas distinguished.

# Burst Recovery

| regime | policy | bursts | preburst_active_replicas | queue_growth | mean_first_scaleout_delay_slots | scaleout_censored_fraction | mean_cold_delay_ms | mean_recovery_after_burst_slots | recovery_censored_fraction | recovery_window_requests | recovery_window_breaches | recovery_window_breach_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D0 | joint_sla | 120 | 1.247 | 13.18 | 13.35 | 0.8333 | 100 | 3.511 | 0.1125 | 6727 | 5122 | 0.7546 |
| D0 | sla_aware | 120 | 1.333 | 13.74 | 16.13 | 0.8633 | 100 | 3.884 | 0.1367 | 6875 | 5376 | 0.7769 |
| D1 | joint_sla | 120 | 1.067 | 8.375 | 7.331 | 0.6992 | 100 | 1.325 | 0.0125 | 5760 | 2436 | 0.4178 |
| D1 | sla_aware | 120 | 1.288 | 9.162 | 12.86 | 0.7133 | 100 | 1.995 | 0.02833 | 6004 | 2978 | 0.4921 |
| D2 | joint_sla | 120 | 1.44 | 10.1 | 7.4 | 0.6108 | 100 | 1.87 | 0.005833 | 5887 | 3376 | 0.569 |
| D2 | sla_aware | 120 | 1.798 | 9.718 | 16.72 | 0.7658 | 100 | 2.301 | 0.035 | 6099 | 3478 | 0.565 |
| D3 | joint_sla | 120 | 1.222 | 13.64 | 10.42 | 0.8242 | 207.5 | 3.809 | 0.1058 | 6733 | 5230 | 0.7709 |
| D3 | sla_aware | 120 | 1.319 | 13.81 | 16.37 | 0.8658 | 216 | 3.735 | 0.1483 | 6885 | 5424 | 0.7835 |
| D4 | joint_sla | 120 | 1.055 | 6.589 | 5.226 | 0.6642 | 100 | 0.44 | 0 | 5486 | 1351 | 0.2451 |
| D4 | sla_aware | 120 | 1.648 | 5.214 | 9.694 | 0.6467 | 100 | 0.5742 | 0 | 5534 | 1052 | 0.1887 |
| D5 | joint_sla | 120 | 1.038 | 9.897 | 5.745 | 0.7725 | 209.3 | 1.691 | 0.015 | 5877 | 3006 | 0.5043 |
| D5 | sla_aware | 120 | 1.283 | 9.325 | 12.7 | 0.72 | 219.6 | 2.049 | 0.035 | 6053 | 3053 | 0.4989 |
| D6 | joint_sla | 120 | 1.309 | 12.08 | 6.426 | 0.6475 | 214.7 | 2.499 | 0.008333 | 6057 | 4017 | 0.6607 |
| D6 | sla_aware | 120 | 1.785 | 9.794 | 16.04 | 0.7625 | 211.2 | 2.393 | 0.0275 | 6104 | 3521 | 0.5706 |
| D7 | joint_sla | 120 | 1.027 | 8.308 | 4.709 | 0.765 | 207.2 | 0.9133 | 0 | 5615 | 2136 | 0.3782 |
| D7 | sla_aware | 120 | 1.675 | 5.482 | 10.4 | 0.6625 | 215.7 | 0.6992 | 0 | 5570 | 1182 | 0.2101 |

Preburst replicas, queue growth, first scale-out latency, cold readiness, recovery latency and recovery-window SLA exported per burst. Conditional recovery means require censoring fractions beside them; no failed recovery removed.

# Dominant Contributors

{
  "caveat": "Component interventions include frozen global controller estimator inputs as well as worker physics; attribution within this simulator is not proof of an isolated real-world causal mechanism.",
  "dominant_sla_factor_by_absolute_shapley": "vram",
  "exact_factorial_decomposition": true,
  "exploratory_n": 10,
  "extension_reason": "Full paired factorial isolates E/V/C combinations; existing DIRECT 30-seed endpoint plus full pressure sweep supply confirmatory endpoint evidence. No additional 30-seed factor run selected from outcomes; factorial magnitudes remain exploratory.",
  "extension_to_30_seeds": false,
  "shapley_identity_verified": true
}

| metric | factor | mean_factorial_marginal | marginal_std | shapley_reversal_contribution | shapley_std | n |
| --- | --- | --- | --- | --- | --- | --- |
| sla_breach_rate | execution | 0.01942 | 0.0244 | 0.01578 | 0.02203 | 10 |
| sla_breach_rate | vram | 0.07941 | 0.01893 | 0.07577 | 0.02021 | 10 |
| sla_breach_rate | cold | 0.05102 | 0.02213 | 0.04738 | 0.01938 | 10 |

Dominant means largest absolute symmetric contribution to the change in controller SLA gap, not universally dominant physical cause.

# Interaction Effects

| metric | term | mean_contrast | contrast_std | n |
| --- | --- | --- | --- | --- |
| p95_latency_ms | execution | 26.02 | 474.6 | 10 |
| p95_latency_ms | vram | -17.92 | 404.9 | 10 |
| p95_latency_ms | execution×vram | 182.6 | 427.6 | 10 |
| p95_latency_ms | cold | -75.23 | 187.1 | 10 |
| p95_latency_ms | execution×cold | 144.9 | 252.5 | 10 |
| p95_latency_ms | vram×cold | 184 | 230.5 | 10 |
| p95_latency_ms | execution×vram×cold | -209.8 | 304.5 | 10 |
| sla_breach_rate | execution | -0.02565 | 0.04181 | 10 |
| sla_breach_rate | vram | 0.02649 | 0.04223 | 10 |
| sla_breach_rate | execution×vram | 0.06651 | 0.05329 | 10 |
| sla_breach_rate | cold | 0.008624 | 0.03059 | 10 |
| sla_breach_rate | execution×cold | 0.04547 | 0.06326 | 10 |
| sla_breach_rate | vram×cold | 0.06116 | 0.05461 | 10 |
| sla_breach_rate | execution×vram×cold | -0.04367 | 0.09351 | 10 |

Non-additivity means one-factor-at-a-time descriptions cannot explain the total endpoint reversal without interactions. All contrasts have paired seed SD; no claim of independently significant interaction at N=10.

# What Explains the DIRECT Reversal?

Across the same ten seeds, the Joint−SLA breach gap moves from -2.983pp (D0) to 10.910pp (D7): a 13.893pp reversal. Symmetric Shapley contributions: memory 7.577pp, cold 4.738pp, execution 1.578pp. These include allocated interaction effects; they are not isolated one-factor effects. Anchored single-factor contrasts sum to 0.946pp; combined interactions account for the remaining 12.947pp.

Mechanistic checks A–G: (A) E alone reduces mean queue delay substantially for both policies (see D0→D1), yet improves the relative JointSLA SLA gap; short execution alone does not explain the reversal. (B) queue-changed routing choices decrease with E, but this is a diagnostic, not proof that queue-aware routing loses value. (C) low DIRECT replica count is associated with fewer scale-outs and a smaller standing ready pool; JointSLA does not trigger more scale-ins than SLA-aware in D7, so 'more aggressive scale-in' is not established by action counts. (D) preburst ready replicas are larger under SLA-aware and observed burst queues smaller at DIRECT. (E) class readiness is 100/200/500ms versus roughly 5.5–7.6ms isolated pipelines; C compounds E/V effects. (F) observed first postburst scale-out is faster for JointSLA conditional on a scale-out occurring; it occurs less often and starts with fewer ready replicas. This does not support a blanket 'late reaction' claim. (G) budget exhaustion is lower under JointSLA at DIRECT; no budget intervention was run, so scarcity is not established as the primary cause. Global estimator mismatch, consolidation and slow recovery remain interacting mechanism explanations rather than isolated proven mediators.

A dedicated scaling/routing/budget intervention would be needed to prove that any individual algorithmic mechanism caused the loss.

# Threats to Validity

Ten seeds, synthetic continuum, single GPU isolated model profiles, model class and SLA correlations from fixed IDs, global estimator/class physics mismatch, short horizon, memory workspace assumptions and slot quantization. Full factorial isolates defined simulator interventions but not real-world exogenous hardware effects. Mechanism time series are observational mediators; an action-budget causal ablation was deliberately not run. No 30-seed factor validation added after inspecting which factor looked favorable.

# Safe Interpretation

A. No statistically supported aggregate SLA-breach crossover; 2× has a favorable mean sign but CI crosses zero. Supported direction changes do occur for mean/p95/p99. B. Observed sign changes: SLA 1.75×→2×; mean1.50×→1.75×; p95 1.00×→1.25×; p99 0.50×→0.75×. Support brackets are broader and reported in `metric_crossovers.json`; no exact continuous threshold is established. C. Memory has the largest symmetric SLA-gap contribution, with large execution/memory/cold interactions. D. Frame contribution as pressure-dependent operating-envelope characterization and performance-resource trade-off. E. This strengthens a transparent mechanism/operating-envelope research case while weakening universal-superiority or SLA-robustness claims; it does not guarantee a B-level venue acceptance. F. A new model-aware/consolidation-aware version is scientifically motivated as a separate preregistered hypothesis, validated on held-out seeds rather than tuned to these results. No algorithm changes were made here. All factor evidence remains exploratory at N=10; no 30-seed factor extension claimed.
