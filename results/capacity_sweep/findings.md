# Capacity experiment findings

The 90 new runs use 30 paired seeds at each of 8, 9 and 10 nodes. The unchanged
SLA-aware heuristic receives identical traffic at all six tested capacities.
There is no admission control and no dropped traffic.

| Nodes | SLA failure (%), mean ± SD | Time-averaged latency (ms), mean ± SD |
|---|---:|---:|
| 5 | 57.19 ± 7.72 | 273.25 ± 167.31 |
| 6 | 44.49 ± 8.09 | 131.66 ± 64.58 |
| 7 | 34.88 ± 8.51 | 83.54 ± 27.74 |
| 8 | 27.97 ± 6.87 | 62.06 ± 13.56 |
| 9 | 23.19 ± 4.63 | 52.65 ± 7.75 |
| 10 | 21.08 ± 4.13 | 48.35 ± 4.69 |

The mean paired SLA reductions for 7→8, 8→9 and 9→10 nodes are
6.91 ± 5.06, 4.79 ± 4.11 and 2.11 ± 2.43 percentage points. Those changes
improve 28/30, 26/30 and 24/30 seeds, respectively; adding a node does not
guarantee improvement for every seed under the fixed greedy heuristic.

A continuous two-segment fit selects a knee at 7 nodes. Its slope changes
from −11.69 to −4.52 percentage points per node, a 61.4% decrease in slope
magnitude. Of 1,000 paired bootstrap samples, 685 select 7, 314 select 8,
and one has no qualifying knee. The measured region of diminishing returns
is therefore approximately **7–8 nodes**. This is a descriptive fit on the
tested capacities, not a physical inflection, significance test or cost optimum.

No capacity achieves a mean failure rate below 15%. At 9 nodes one seed
meets the target; at 10 nodes two seeds meet it. The 10-node mean is 21.08%.
The lower latency and failure rate continue to improve beyond the knee, but
with smaller marginal gains.

The latency column weights nonempty arrival slots equally within each seed;
the request-weighted alternative is also exported. SD describes seed
variation. GPU curves use capacity-weighted pool utilization; they do not
imply every individual node has the same headroom.

All 76 tests pass. Independent export verification reconstructed 528,408
new request outcomes and checked paired inputs, node capacities, summaries
and marginal gains. See `export_verification.json`, `knee_analysis.json`,
`marginal_gains.csv` and `target_evaluation.json` for the audit data.
