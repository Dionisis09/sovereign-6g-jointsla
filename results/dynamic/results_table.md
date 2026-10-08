# Dynamic placement results

30 paired seeds × 100 slots × four policies.

Mean ± sample SD across seeds. Time-averaged latency gives each nonempty arrival slot equal weight; request-averaged latency gives each completed request equal weight. Both include late completions. SLA includes every offered request; admission failures have no finite latency.

| Policy | Time-avg latency, ms | Request-avg latency, ms | SLA breaches, % | Actions | Migrations | Replica seconds | Decision time, ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| static | 804.691 ± 320.182 | 846.236 ± 325.610 | 72.241 ± 5.576 | 0.000 ± 0.000 | 0.000 ± 0.000 | 200.000 ± 0.000 | 0.001 ± 0.000 |
| reactive | 786.545 ± 306.688 | 828.797 ± 313.389 | 71.375 ± 5.698 | 4.033 ± 3.943 | 0.000 ± 0.000 | 208.027 ± 7.170 | 0.045 ± 0.006 |
| periodic | 805.256 ± 309.811 | 846.649 ± 315.215 | 72.538 ± 5.529 | 1.167 ± 1.913 | 1.167 ± 1.913 | 200.000 ± 0.000 | 0.004 ± 0.001 |
| sla_aware | 273.247 ± 167.312 | 299.234 ± 171.971 | 57.195 ± 7.718 | 50.433 ± 21.260 | 0.100 ± 0.403 | 270.643 ± 17.658 | 0.283 ± 0.022 |

The three baseline definitions and proposed risk score are fixed in the package README. Actual CPU/GPU/link busy utilization is capacity bounded. Offered-load ratios above one measure nominal incoming demand pressure, not physical overbooking. Both are exported per node and slot.

Scale-out uses additional replicas and VRAM under the same node budgets. Replica seconds and VRAM GB-seconds disclose this cost. The periodic policy only migrates; it does not add capacity. A node threshold can miss a service queue bottleneck when that service is waiting on its serial pipeline. These synthetic results are not a reproduction of published DRL performance percentages.

Full metrics (including per-tier breaches, CPU/GPU profiles, queue delays, offered overload, scale-up/down counts and runtime) are in `summary.csv`; per-seed evidence is in `runs.csv`.
