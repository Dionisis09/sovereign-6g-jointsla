# Goal

Reduce implementation overhead without changing any algorithmic decision, floating-point formula, physical event, workload, configuration or statistical method. Only H4 is reassessed.

# Frozen Research Baseline

The verified SMALL (5/20), MEDIUM (10/40), LARGE (20/80) JointSLA implementations and all three existing result trees remain byte-identical. H1/H2/H3/H5 retain their verified conclusions. Two actions per 100-ms slot, max three replicas, causal state and CPU→GPU→CPU pipeline are unchanged.
SHA-256 verification protects 4,265 pre-existing files. The optimized adapter has a fixed implementation fingerprint in optimization_protocol.json.

# Original Bottleneck

Historical 30-seed full controller means were 2.517, 6.933, 26.836 ms. About 83% of historical LARGE control time was snapshot construction. Fresh repeated timings below are the appropriate before/after comparison; historical measurements were taken at a different time.
The legacy snapshot repeatedly scans all stores for each service and sorts the same queues, and nominal() repeats immutable service/topology arithmetic and dynamic node observation for every service–node pair.

# Profiling Method

Before optimization, cProfile ran unchanged seed 1 at each scale. It is repeated after optimization. profile_before/after.csv report exclusive function times, calls, per-call means and percentage of selected controller/state/routing functions. Cumulative time includes called NumPy, copy, sorting and dictionary operations. Percentages are an attribution denominator, not a sum of nested full-loop percentages.
The complete pstats files retain builtins and all call edges. No cProfile or tracemalloc is active during the performance benchmark. Each benchmark implementation/scale warms up once, then performs seven fresh seed-1 replays, alternating execution order. Each provides 700 live controller invocations with actual accepted/rejected action application. Existing high-resolution timers isolate snapshot and policy/application; all disk output, constructor, workload generation and plotting are excluded.

# Legacy Controller Profile

SMALL:

| function | calls | total_time_ms | cumulative_time_ms | percent_controller_time |
|---|---|---|---|---|
| simulator.py:126:nominal | 21752 | 159.7937 | 368.3914 | 35.6892 |
| simulator.py:164:dispatch | 6417 | 55.9311 | 459.5689 | 12.4919 |
| router.py:22:estimate | 45805 | 40.0467 | 44.4931 | 8.9442 |
| simulator.py:143:candidates | 8417 | 35.0824 | 280.5212 | 7.8355 |
| simulator.py:25:items | 13911 | 22.3064 | 40.2053 | 4.9820 |

MEDIUM:

| function | calls | total_time_ms | cumulative_time_ms | percent_controller_time |
|---|---|---|---|---|
| simulator.py:126:nominal | 59529 | 403.4298 | 936.8908 | 40.5286 |
| simulator.py:164:dispatch | 11290 | 97.8865 | 769.0823 | 9.8337 |
| router.py:22:estimate | 88600 | 73.5084 | 81.6993 | 7.3847 |
| simulator.py:143:candidates | 15290 | 68.4403 | 475.0716 | 6.8755 |
| simulator.py:25:items | 28114 | 68.2918 | 121.5194 | 6.8606 |

LARGE:

| function | calls | total_time_ms | cumulative_time_ms | percent_controller_time |
|---|---|---|---|---|
| simulator.py:126:nominal | 207492 | 1369.0419 | 3147.2326 | 48.5919 |
| simulator.py:25:items | 55720 | 238.2601 | 318.8434 | 8.4567 |
| simulator.py:164:dispatch | 25639 | 221.1139 | 1874.7678 | 7.8481 |
| simulator.py:143:candidates | 33639 | 205.0822 | 1179.4527 | 7.2791 |
| router.py:22:estimate | 188339 | 160.2717 | 177.5711 | 5.6886 |

# Optimizations Applied

1. Precompute immutable service–node network latency, resource fraction, execution metadata and static feasibility with the exact legacy scalar expressions and reduction order.
2. Maintain insertion-ordered per-service live-replica indexes on add and original worker completion. Entries reference original objects, so busy, readiness, node and migration state remain live.
3. Maintain per-service historical store IDs, retaining retired stores exactly as the original aggregate queue does. Queue ordering remains sorted by (arrival_s, request_id).
4. Collect aggregate waiting work once within each synchronous snapshot; reuse it for queue lengths, oldest age and all waiting ages.
5. Cache dynamic node resource/feasibility extraction only inside the same snapshot, clearing it in finally. Per-request nominal observation outside snapshots always reads current state.
Every candidate is retained. Score functions, routing dispatch, virtual deployment quality (including deepcopy), joint_actions, action application and physical pipeline are inherited unchanged. The worker wrapper introduces no event or yield beyond yield-from the original generator.

# Semantic Equivalence Validation

All nine golden seeds pass exact canonical trace hashes and direct object equality: actions, routing (including candidate score inputs and order), request destinations/completions/latencies/SLA flags, all 200 state snapshots and resource/lifecycle traces. Only measured timing fields are excluded.
Full replay: 90 optimized runs plus 90 fresh unchanged legacy reference runs. 1,225,366 request outcomes and 1,277,566 routing assignments pass exact comparison with frozen audit frames, read with round-trip float parsing. All 24 exported research metrics also equal fresh unchanged legacy calculations exactly. No epsilon/tolerance is used.
There are 293 scalar representations in historical summary CSVs whose default-parser read/write path changes the last binary bits. For each, the exact historical parser transformation is reproduced (not bounded by tolerance), raw audit frames are identical, and fresh legacy and optimized calculations are exactly identical. These are recorded in metric_representation_differences.csv; frozen summary files are untouched. For example p99 1089.8791033297935 is parsed as 1089.8791033297937 by the default reader. We do not claim those stored decimals equal recomputed values bit-for-bit.

# Performance Before vs After

| Scale | Legacy mean ms | Optimized mean ms | Legacy median ms | Optimized median ms | Legacy p95 ms | Optimized p95 ms | Speedup |
|---|---|---|---|---|---|---|---|
| SMALL | 2.6329 | 1.2336 | 2.4859 | 1.2473 | 3.5507 | 1.6874 | 2.1343 |
| MEDIUM | 7.5251 | 2.6924 | 6.8267 | 2.6616 | 10.6592 | 4.0233 | 2.7949 |
| LARGE | 29.8741 | 7.5046 | 29.9396 | 6.8885 | 39.1153 | 12.8410 | 3.9808 |

# Snapshot Construction Improvement

| Scale | Legacy ms | Optimized ms | Speedup | Reduction % |
|---|---|---|---|---|
| SMALL | 1.7501 | 0.2414 | 7.2508 | 86.2083 |
| MEDIUM | 5.5309 | 0.6199 | 8.9227 | 88.7926 |
| LARGE | 24.7124 | 2.4787 | 9.9699 | 89.9698 |

# Routing Overhead

The routing chooser/scorer is unchanged. Existing attempt timers include candidate construction, scoring and observational counterfactuals, excluding JSON audit formatting. Failed eligibility attempts and drain-time assignments are retained. Full controller below refers to one control invocation; per-request routing is additional CPU work and is measured separately, not hidden in that denominator.

| Scale | Legacy mean ms | Optimized mean ms | Legacy p95 ms | Optimized p95 ms |
|---|---|---|---|---|
| SMALL | 0.0335 | 0.0258 | 0.0572 | 0.0444 |
| MEDIUM | 0.0298 | 0.0212 | 0.0519 | 0.0356 |
| LARGE | 0.0393 | 0.0258 | 0.0617 | 0.0418 |

# Small / Medium / Large Results

SMALL: historical controller 2.5166 ms; optimized full-30-seed mean 0.9787 ms; mean per-seed controller p95 1.3497 ms. All 30 seeds have exact scientific equivalence.

MEDIUM: historical controller 6.9330 ms; optimized full-30-seed mean 2.1839 ms; mean per-seed controller p95 3.0551 ms. All 30 seeds have exact scientific equivalence.

LARGE: historical controller 26.8362 ms; optimized full-30-seed mean 5.7203 ms; mean per-seed controller p95 8.2829 ms. All 30 seeds have exact scientific equivalence.

# H4 Reassessment

**H4 = SUPPORTED**. Fixed mean <10-ms budget at every scale, original mean per-seed control p95 <=100 ms and routing p95 <=1 ms. Both repeated benchmark means and all-30-seed means must meet the budget; no threshold is changed after measurement.

| scale | full_30seed_controller_mean_ms | full_30seed_mean_controller_p95_ms | full_30seed_mean_routing_p95_ms | benchmark_controller_mean_ms | supported |
|---|---|---|---|---|---|
| SMALL | 0.9787 | 1.3497 | 0.0294 | 1.2336 | True |
| MEDIUM | 2.1839 | 3.0551 | 0.0295 | 2.6924 | True |
| LARGE | 5.7203 | 8.2829 | 0.0306 | 7.5046 | True |

# Remaining Bottlenecks

At LARGE, the repeated optimized snapshot mean is 2.4787 ms and unchanged policy plus application is 5.0259 ms. The policy/action path accounts for 67.0% of optimized control wall time. deployment_quality virtual scoring/deepcopy and feasibility loops now matter more than redundant state observation. This study leaves them unchanged.
Initialization now precomputes static metadata; its time is separately retained in benchmark_runs.csv and is not concealed as control time. Candidate bounds, global action budget and lifecycle restrictions remain unchanged. No theoretical asymptotic proof or universal performance claim follows from three sizes.

# Threats to Measurement Validity

- Single Windows/Python host, process scheduling and CPU-frequency variation. Alternating order/warm-up/repetition reduce but cannot remove host noise; these timings are not hardware-independent guarantees.
- Repeated benchmark uses seed 1; separate full replay spans all 30 seeds. P95 of 700 invocations differs from the mean of 30 per-seed p95s. Neither is a confidence interval.
- Full controller is snapshot plus policy/application at control slots. Per-request route cost and audited simulator runtime remain separate scopes. Timing never affects simulated latency.
- Ordered indexes and static tables have memory cost. Static caching relies on the model's immutable service, topology and configuration contract. Dynamic node cache is invocation-local, explicitly invalidated on normal/exception exit.
- Python tracemalloc measures the initial snapshot/constructor state only, separately from timing; process RSS is sampled and can retain allocator pages from previous runs. Neither is an isolated policy allocation proof.
- Frozen summary decimal-parser differences are disclosed; no scientific equality is inferred from approximate scalar matching.

| Scale | Legacy Python peak MB | Optimized Python peak MB | Legacy retained MB | Optimized retained MB |
|---|---|---|---|---|
| SMALL | 0.1617 | 0.1770 | 0.0706 | 0.1001 |
| MEDIUM | 0.4461 | 0.4879 | 0.1348 | 0.2365 |
| LARGE | 1.3672 | 1.5359 | 0.2639 | 0.6385 |

SMALL mean sampled replay process RSS: legacy 99.78 MiB, optimized 99.93 MiB.
MEDIUM mean sampled replay process RSS: legacy 142.47 MiB, optimized 142.94 MiB.
LARGE mean sampled replay process RSS: legacy 245.06 MiB, optimized 245.54 MiB.

# Safe Paper Claims

Implementation-level ordered state indexes, immutable metadata caching and invocation-local node observation reduced JointSLA control overhead below the predeclared 10-ms mean budget at all tested synthetic scales, without changing any orchestration, routing or request outcomes. Exact reference replay and frozen raw audit comparisons support semantic preservation.

This is implementation performance engineering, not new algorithmic novelty. Previously verified scientific conclusions and statistical results remain unchanged.

# Claims We Cannot Make

Production/carrier-grade feasibility, hardware-independent real-time guarantees, linear/asymptotic scalability, global optimality, improved algorithmic decisions, newly improved SLA/latency/resource results, or additional novelty of the slack term. Pure snapshot memory does not prove full-run peak Python memory. Historical stored summary decimals are not claimed bit-identical to fresh recalculation.

Reproduce: `python run_controller_optimization.py --all`. Stage flags: --profile, --validate-equivalence, --benchmark, --full-validation. All five figures have PNG 300 dpi, SVG and PDF exports.