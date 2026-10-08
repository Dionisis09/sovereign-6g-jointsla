# Claim boundaries

## Supported, within the corresponding frozen regime

- Synthetic advantage: `results/joint_routing_30seeds/paired_tests.csv` and report.
- Scalability within SMALL 5/20, MEDIUM 10/40, LARGE 20/80: `results/scalability_30seeds/paired_tests.csv`.
- Hardware-grounded aggregate-SLA reversal: `results/hardware_grounded/paired_tests.csv` and report.
- High-pressure v1 mean/p95/p99 latency improvement: `results/hardware_pressure_sweep/paired_tests.csv`.
- VRAM / warm-capacity / cold-start interaction evidence: `results/hardware_causal_decomposition/{factor_effects,interaction_effects,burst_summary}.csv`. Exploratory 10-seed analysis, not unique causal identification.
- v2 Gold improvement **relative to v1**, with residual performance/resource/recovery costs: `results/jointsla_v2_heldout/paired_tests.csv`.
- The performance–resource–recovery trade-off and a tested operating envelope.
- Implementation speedup with frozen outcome equivalence: `results/controller_optimization/full_30seed_equivalence.csv` and before/after measurements.

## Not supported

Universal JointSLA superiority; global optimality; statistically proven aggregate-SLA crossover; production readiness; real 6G deployment; full SOVEREIGN implementation; TMF-921 implementation; hardware-independent generalization; global Pareto optimality; an independently demonstrated physical causal effect for each Shapley attribution; a claim that v2 fixes all QoS or outperforms SLA-aware for all tiers.

At 2× the pressure-series mean SLA difference changes sign; lack of support for a crossover stays explicit. Gold is a persistent v1 weakness. MJO wins LARGE p99. v2 loses v1's high-pressure latency advantage. Distinct seed cohorts and regimes are never merged into one scientific estimate.

The coupled system is an experimental subject. Coupling placement/scaling/routing alone is not asserted as a new algorithmic contribution. Architectural mapping is conceptual and does not establish implementation of intents, sovereignty, availability or geographic constraints.
# Live replay scope

Live Experiments executes the unchanged simulator on archived held-out inputs. Matching outputs demonstrate repeatability for selected seeds, not universal policy superiority or new statistical significance. Runtime varies with host load. All live artifacts remain separate from frozen research results.

