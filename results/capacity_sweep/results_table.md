# Capacity sweep: 5–10 nodes

30 paired seeds per capacity, unchanged SLA-aware policy. Values are mean ± sample SD.

| Nodes | SLA failure, % | Time-avg latency, ms | Replica seconds |
|---|---:|---:|---:|
| 5 | 57.19 ± 7.72 | 273.25 ± 167.31 | 270.64 ± 17.66 |
| 6 | 44.49 ± 8.09 | 131.66 ± 64.58 | 320.28 ± 21.10 |
| 7 | 34.88 ± 8.51 | 83.54 ± 27.74 | 364.67 ± 22.22 |
| 8 | 27.97 ± 6.87 | 62.06 ± 13.56 | 394.01 ± 20.06 |
| 9 | 23.19 ± 4.63 | 52.65 ± 7.75 | 416.76 ± 15.25 |
| 10 | 21.08 ± 4.13 | 48.35 ± 4.69 | 426.07 ± 19.08 |

Empirical hinge-fit knee: 7. Pre-knee slope: -11.694 percentage points/node; post-knee slope: -4.516.

This is a fitted diminishing-return candidate over six tested capacities. It is not a physical inflection or a guaranteed optimum. The original 5–7-node runs are reused with verified paired traffic. See knee_analysis.json for bootstrap stability, marginal_gains.csv for paired increments, and target_evaluation.json for the <15% goal. No requests are dropped.
