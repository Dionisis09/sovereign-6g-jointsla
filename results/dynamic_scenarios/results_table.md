# Dynamic scenario comparison

30 paired seeds, 100 slots. Capacity is one scenario with 6- and 7-node variants.

Mean ± sample SD across seeds. Offered failures include drops. Latency uses completed requests, averaged equally over nonempty arrival slots.

| Scenario | Latency, ms | Offered failure, % | Admitted breaches, % | Drops, % | Gold/Silver breaches, % | Replica seconds |
|---|---:|---:|---:|---:|---:|---:|
| baseline (5 nodes) | 273.25 ± 167.31 | 57.19 ± 7.72 | 57.19 ± 7.72 | 0.00 ± 0.00 | 59.00 ± 8.58 | 270.64 ± 17.66 |
| predictive (5 nodes) | 279.36 ± 169.21 | 57.36 ± 7.82 | 57.36 ± 7.82 | 0.00 ± 0.00 | 59.12 ± 8.57 | 270.85 ± 17.66 |
| capacity_6 (6 nodes) | 131.66 ± 64.58 | 44.49 ± 8.09 | 44.49 ± 8.09 | 0.00 ± 0.00 | 46.92 ± 7.98 | 320.28 ± 21.10 |
| capacity_7 (7 nodes) | 83.54 ± 27.74 | 34.88 ± 8.51 | 34.88 ± 8.51 | 0.00 ± 0.00 | 38.87 ± 9.22 | 364.67 ± 22.22 |
| admission (5 nodes) | 166.14 ± 84.37 | 53.77 ± 7.45 | 51.30 ± 7.58 | 5.13 ± 2.55 | 57.19 ± 9.72 | 270.18 ± 18.60 |

The <15% target applies to all-offered failure, including rejected traffic. Conditional admitted breaches are reported separately and cannot establish success by omitting drops. Gold/Silver have zero administrative drops. All workloads and weights were fixed before the measured run.

Cold-start counts, first-request penalties, starts overlapping observed bursts, scale/migration counts, per-tier failures/drops, GPU/CPU metrics and runtimes are included in summary.csv and runs.csv. Forecasts have no future trace access; the first burst has no learned phase. A compound Poisson process is unpredictable at the request level; forecasting targets the periodic rate envelope.
