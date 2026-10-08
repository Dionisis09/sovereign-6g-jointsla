# Placement experiment results

30 paired seeds × four methods = 120 runs. 5 servers and 20 applications per seed.

Values are mean ± sample standard deviation across seeds. SLA failures include unplaced offered traffic; mean latency is weighted by placed traffic only.

| Algorithm | Latency, ms | SLA failure, % | Unplaced apps | Runtime, ms |
|---|---:|---:|---:|---:|
| random | 40.517 ± 2.953 | 39.597 ± 12.620 | 0.367 ± 0.718 | 0.399 ± 0.065 |
| greedy | 39.894 ± 2.162 | 36.953 ± 12.712 | 0.433 ± 1.104 | 0.748 ± 0.103 |
| shortest_latency | 31.287 ± 1.682 | 16.515 ± 10.075 | 0.300 ± 0.702 | 0.477 ± 0.253 |
| sla_weighted | 31.296 ± 1.473 | 10.631 ± 7.560 | 0.300 ± 0.702 | 0.822 ± 0.108 |

| Algorithm | Edge | CPU utilization, % | GPU utilization, % |
|---|---|---:|---:|
| random | 0 | 54.43 ± 10.26 | 69.24 ± 17.90 |
| random | 1 | 53.23 ± 16.43 | 69.48 ± 17.57 |
| random | 2 | 51.27 ± 13.29 | 70.24 ± 19.21 |
| random | 3 | 49.10 ± 11.91 | 68.32 ± 16.87 |
| random | 4 | 58.78 ± 14.12 | 78.37 ± 16.43 |
| greedy | 0 | 52.12 ± 7.24 | 69.32 ± 12.84 |
| greedy | 1 | 54.89 ± 9.47 | 71.65 ± 15.28 |
| greedy | 2 | 50.77 ± 9.02 | 73.28 ± 16.04 |
| greedy | 3 | 52.58 ± 9.86 | 73.69 ± 11.32 |
| greedy | 4 | 55.07 ± 10.28 | 70.24 ± 14.05 |
| shortest_latency | 0 | 54.61 ± 13.73 | 69.12 ± 16.03 |
| shortest_latency | 1 | 55.25 ± 17.45 | 72.35 ± 17.16 |
| shortest_latency | 2 | 52.54 ± 13.07 | 71.01 ± 19.23 |
| shortest_latency | 3 | 51.07 ± 11.57 | 70.77 ± 17.93 |
| shortest_latency | 4 | 53.86 ± 12.28 | 73.41 ± 15.56 |
| sla_weighted | 0 | 53.71 ± 11.74 | 68.14 ± 15.42 |
| sla_weighted | 1 | 53.36 ± 11.07 | 69.64 ± 14.91 |
| sla_weighted | 2 | 54.56 ± 13.29 | 74.85 ± 14.41 |
| sla_weighted | 3 | 49.91 ± 10.50 | 71.13 ± 15.80 |
| sla_weighted | 4 | 54.82 ± 9.42 | 74.30 ± 14.80 |

All placements pass independent CPU/GPU/bandwidth capacity validation. Baseline definitions and the fixed heuristic are in the README. This is a stipulated static latency model, not a measured telco system or a queueing simulation. SD bars show scenario variability, not confidence intervals or significance. The seed fixes inputs and decisions; wall-clock runtime is not deterministic.

Inspect `results.csv`, `summary.csv`, `application_outcomes.csv`, and `scenarios.json` for full trial-level and application-level evidence. Heuristic weights were fixed before the experiment and were not tuned against these results.
