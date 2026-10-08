# Supervisor demonstration · 9 minutes

Enable Presentation Mode. Leave Learning Mode off initially; enable it if a definition needs explanation. Navigation always remains available.

| Time | Click | Say / inspect |
|---|---|---|
| 0:00–1:00 | Overview; expand “Explain the paper in 60 seconds” if useful | The subject is coupled edge-AI orchestration; the contribution is the operating envelope and trade-off, not universal algorithm superiority. |
| 1:00–2:00 | System & JointSLA; move the queue sliders | Requests have a CPU–GPU–CPU pipeline. Warm replicas serve immediately. Routing may choose farther replicas to avoid long queues. Slider values are illustrative only. |
| 2:00–3:00 | Synthetic Results; keep SLA-aware and JointSLA-v1 selected | Inspect SLA and latency, then statistical details. Scalability confirms benefits only at tested synthetic sizes. |
| 3:00–4:00 | Hardware Profiling, then Hardware-Grounded Reversal | Measured inference is short, but readiness is much longer. Fewer replicas and less memory do not necessarily produce fewer deadline misses. |
| 4:00–5:15 | Pressure Sweep; choose 2× | Tail latency improves strongly. The mean aggregate-SLA difference changes sign, but a crossover is not statistically supported. Inspect frozen paired CIs. |
| 5:15–6:15 | Mechanism Analysis, then Burst Recovery at 1× | Execution alone does not explain the reversal. VRAM and cold readiness interact with consolidation. Attribution includes interactions; conditional recovery delays must be read with censoring. |
| 6:15–7:30 | JointSLA-v2, then v2 Held-out Results at 1× and 2× | One candidate, frozen after development seeds 101–105. Independent seeds 31–60 show Gold improvement relative to v1, but the overall trade-off remains. |
| 7:30–8:15 | SOVEREIGN / Intent | Primary fit is Pillar 3 Distributed Inference Fabric, with DSO context from Pillar 2. Dashed upstream functions are conceptual, not implemented interfaces. |
| 8:15–9:00 | Research Story, then Data / Reproducibility | An operating envelope, not a universal advantage. Show outcome verification, frozen sources, pairing checks, and the deliberate negative results. |

Optional backup: Strong Baseline for MJO trade-offs; Controller Optimization for the unchanged-science speedup; observed operating points for descriptive performance/resource comparisons. No simulation is executed during the demo.
# Optional live demonstration

Open **Live Experiments**, select 1×, seed 31 and all three policies, then click **Run live paired experiment**. Show completion, the physical/accounting audit and the ten-metric match against frozen values. Inspect latency and GPU trajectories and download the metrics/manifest. Explain that a selected-seed replay demonstrates reproducibility; the held-out 30-seed tables support statistical conclusions.

