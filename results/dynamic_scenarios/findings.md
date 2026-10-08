# Findings from the three scenarios

30 paired seeds and 100 slots; 150 total runs including a fresh baseline and both capacity variants. All weights and workload parameters were fixed before the measured run.

The <15% all-offered SLA failure target was not achieved by any case or any seed. The best mean was the seven-node case: 34.88% vs 57.19% at five nodes. Equal-slot mean latency fell from 273.25 ms to 83.54 ms; replica-seconds rose from 270.64 to 364.67.

Predictive prewarming did not improve the mean failure rate: 57.36% vs 57.19%. It accepted only 1.67 prewarm actions per run on average. Mean cold-start count was 29.20 vs 28.70; starts overlapping bursts were 2.73 vs 2.90. First-request cold penalties totaled 143.33 vs 140.50 ms per run. These small descriptive differences do not establish statistical significance.

The admission case rejected 5.13% of all traffic (16.85% of Bronze traffic). All-offered failure was 53.77%; conditional admitted breaches were 51.30%. Gold/Silver combined breaches were 57.19% vs 59.00%. Gold and Silver drop rates were zero.

| Admission-control tier | All-offered failure, % | Admitted breach, % | Drop rate, % |
|---|---:|---:|---:|
| Gold | 61.32 | 61.32 | 0.00 |
| Silver | 52.69 | 52.69 | 0.00 |
| Bronze | 44.60 | 34.24 | 16.85 |

In this model, service queue delay dominates node resource queue delay: the baseline means were 274.28 and 0.68 ms, respectively. Mean VRAM residency was 94.41% at five nodes and 90.45% at seven. This is consistent with limited space for replicas and a serial per-replica pipeline, including network waiting, constraining prewarming and latency reduction. It is a diagnosis from the model, not an isolated causal ablation of each mechanism.

The implemented scope retains the original limit of three replicas per service, two actions per slot, cold starts, deadlines and compound arrival batches. Achieving <15% will require a subsequent controlled experiment on remaining bottlenecks; these results do not establish a general edge-system limit. No SLA targets, traffic rates or drop denominators were relaxed to claim success.

All means, sample SDs, paired differences and per-seed measurements are retained in summary.csv, paired_differences.csv and runs.csv. The source protocol and complete request/admission evidence support independent verification.
