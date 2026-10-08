# Frozen evidence and presentation lineage

All paths are relative to the repository. CSVs remain authoritative over approximate values in the request. The dashboard reads original artifacts; display copies may be filtered, pivoted or converted in units. It never regenerates scientific statistics or requests.

## Shared transformations / units

`summary_statistics.csv` has `policy, metric, n, mean, standard_deviation, ci95_lower, ci95_upper` plus optional `scale/load_multiplier/tier/model_class`. Cards, bars and lines directly use `mean` and existing bounds; no seed-level CI recomputation. Fractional breach rates multiply by 100 for percent; fractional deltas multiply by 100 for **percentage points**. `_pct` source columns already contain percentages and are never multiplied. Latency and controller `_ms` remain milliseconds. `average_vram_residency_gib` stays GiB. Hardware `_bytes` divide by 2^30 for display; original bytes are retained in export. Synthetic `vram_gb_seconds` is a nominal source GB·s integral, not silently relabeled GiB. Seed distributions retain source individual-run metrics; no pooled percentiles are inferred. Missing metrics show “Not available in frozen results”.

Paired schemas are different: original `policy_A/policy_B, absolute_difference, difference_ci95_lower/upper` is **B minus A**; hardware/pressure `delta_joint_minus_sla` is v1 minus SLA-aware; held-out `delta_v2_minus_comparator` is v2 minus comparator. Existing `p_value_holm, rank_biserial_correlation, wins, ties, losses` are displayed intact, with source direction fields where available. No claim of significance is derived from chart means. An absent CI is unavailable, not a standard deviation error bar.

## Panel inventory

| View / panel | Authoritative sources and relevant columns | Transformation / direct or derived | Units and caveats |
|---|---|---|---|
| Overview held-out cards/charts | `results/jointsla_v2_heldout/summary_statistics.csv`: load_multiplier, policy, metric, mean, n, ci95_lower/upper | Direct 1× rows for SLA and Gold | %, frozen seed-mean CIs, seeds 31–60; v2 Gold claim is relative to v1 |
| Overview story / contribution / 60-second explanation | Reports in joint_routing, scalability, hardware_grounded, hardware_pressure_sweep, hardware_causal_decomposition, jointsla_v2_heldout | Narrative synthesis of scoped findings | No new numeric estimate or novelty claim |
| System / lifecycle diagrams | `docs/SOVEREIGN_INTENT_MAPPING.md`, existing system source described there | Explanatory diagrams, not execution | Sliders use visibly labeled illustrative ms; no experiment source or claim |
| Synthetic QoS/resources/selected metric | `results/joint_routing_30seeds/summary_statistics.csv`; SLA, mean/p95/p99, replicas, vram_gb_seconds, cold_starts, total_actions | Direct policy rows, display labels only | 30 original paired seeds; synthetic nominal resource units |
| Earlier baseline | `results/paper_30seeds/summary_statistics.csv`, same schema | Direct separate earlier comparison | Not merged with other regimes |
| Synthetic seed explorer / distributions | `results/joint_routing_30seeds/raw_policy_results.csv`: seed, policy, metrics, traffic_hash, workload_hash | Direct run aggregates, filtered inspected seed; distribution all selected seeds | No request-level rows loaded; p95/p99 remain within-run percentiles |
| Synthetic paired statistics | `results/joint_routing_30seeds/paired_tests.csv`; selected metric and policies | Direct inferential results, B minus A | Mixed comparison families retained; do not confuse sign with v1-minus-baseline |
| Scalability lines / comparative tabs | `results/scalability_30seeds/{summary_statistics,raw_results,paired_tests}.csv`: scale, policy and shared metrics | Direct means/CIs vs ordered SMALL/MEDIUM/LARGE, raw seed distributions | 5/20, 10/40, 20/80 only; no extrapolation |
| Controller timing / budget | `results/controller_optimization/controller_performance_before_after.csv`: legacy/optimized full_controller_mean/median/p95_ms | Melt existing columns into comparison bars | ms; 10 ms reference only for mean, not p95 |
| Controller / snapshot speedup | Same file: speedup_full_controller, speedup_snapshot | Direct frozen ratios, no re-benchmark | ×; implementation-only performance result |
| Controller equivalence | `results/controller_optimization/full_30seed_equivalence.csv`: pass, hash equality flags, requests_verified | Direct audit rows | Historical validation, not new simulation |
| Strong comparator metrics, tiers, cost scatter | `results/strong_baseline_30seeds/{summary_statistics,raw_results,paired_tests}.csv`: scale, policy, Gold/Silver/Bronze_breach_rate, controller_cpu_ms_per_request and QoS | Direct values; summary pivot for descriptive scatter | %, ms, ms/request. MJO is optimization-inspired; not exact reproduction |
| Hardware identity | `results/hardware_grounded/profiling/hardware_info.json`: cpu_model, devices.name, total_vram_bytes, background_load_caveat | Direct names; bytes / 2^30 | GiB physical VRAM, one laptop; no lab isolation claim |
| Hardware pipeline measurements | `model_profile_summary.csv`: model, batch_size, stage, phase, mean/median/p95/p99 | Direct selected models/statistic; distinct CPU pre/upload/GPU/CPU post stages | ms; batch 1; measurement percentiles are not seed CIs |
| Hardware cold readiness | `cold_start_summary.csv`: stage=cold_start_total, selected measured statistic | Direct measured totals, no sum of percentiles | ms; local readiness context only |
| Hardware memory | `vram_summary.csv`: model_residency_bytes and allocated/reserved/peak fields | Presentation-only GiB columns alongside unchanged byte source | GiB; residency versus peak reserved/allocated remain distinct |
| Hardware reversal | `results/hardware_grounded/{summary_statistics,raw_results,paired_tests}.csv`: DIRECT/MEDIUM plus shared metrics | Direct 30-seed means/CIs; separate resource and QoS panels | 1× hardware-derived costs, simulated serving environment |
| Pressure load curves / cards | `results/hardware_pressure_sweep/summary_statistics.csv`: load_multiplier, policy, selected QoS/resource/mean_queue_delay_ms | All-load direct series; selected load direct cards | 0.50–2.00×; load selection does not invent intermediate runs |
| Pressure paired differences | `paired_tests.csv`: delta_joint_minus_sla, delta_ci95_lower/upper, p_value_holm, supported_direction | Direct v1−SLA-aware deltas and CIs; all-load curve, selected-load statistical rows | pp for rate; ms for latency; no supported aggregate SLA crossover |
| Pressure paired seed inspection | `paired_seed_differences.csv`: seed, metric, delta_joint_minus_sla and outcome | Direct selected-load rows | Same delta direction, no re-testing |
| Tier behavior | `results/hardware_pressure_sweep/tier_summary_statistics.csv`: tier, load, policy, metric, mean, CIs | Direct selected tier across frozen loads | Rates %, run latency ms; aggregate effects do not apply uniformly |
| Model-class behavior | `model_class_summary_statistics.csv`: LIGHT/MEDIUM/HEAVY and same summary schema | Direct selected class | No subgroup alone establishes cause |
| D0–D7 settings | `results/hardware_causal_decomposition/regime_definitions.json`: real_execution, real_vram, real_cold | Direct factor settings | Exploratory seeds 1–10 |
| D0–D7 delta bars | `paired_differences.csv`: regime, metric=sla_breach_rate, delta_joint_minus_sla, wins/ties/losses | Direct delta ×100 | pp; this artifact does not supply inferential CIs |
| Factor attribution | `factor_effects.csv`: factor, shapley_reversal_contribution; `interaction_effects.csv` | Direct frozen attribution ×100 | pp; includes interactions, not independent physical effects |
| Burst distributions and censoring | Pressure/Mechanism `burst_summary.csv`; held-out `burst_seed_summary.csv`: preburst_active_replicas, queue_growth, recovery_window_breach_rate, mean_recovery_after_burst_slots, mean_first_scaleout_delay_slots, scaleout_count where present, censored fractions | Direct selected-scope seed distributions; no fabricated event counts | replicas/service, requests, %, slots. Conditional observed timings; missing/censored events not zero; windows may overlap |
| v2 design and freeze | `results/jointsla_v2_heldout/freeze_manifest.json`: timestamp, statement, parameters, source_hashes, protected_history | Direct frozen fields; design explanation from report | One mitigation; no future information, no new candidate |
| Development panels | `results/jointsla_v2_development/{summary_statistics,raw_results,paired_tests}.csv` | Direct separate seed 101–105 series | 5 seeds; not held-out evidence |
| v2 held-out QoS/resources/Gold | `results/jointsla_v2_heldout/{summary_statistics,raw_results,paired_tests}.csv` | Direct 1×/2× data, existing CIs and tests | 30 seeds 31–60. Gold improvement relative to v1 does not imply universal baseline superiority |
| Performance/resource points | Held-out or pressure summary: replicas, Gold/SLA rates, p95, VRAM, actions | Pivot frozen means, scatter at selected existing load | Observed points only, not global Pareto frontier |
| SOVEREIGN / intent | `docs/SOVEREIGN_INTENT_MAPPING.md`; `docs/figures/sov6g_intent_jointsla_architecture.mmd`; supplied proposal printed pp.25,28–29 reviewed in prior turn | Conceptual mapping and implementation boundaries | No full integration, TMF-921, real 6G or implemented sovereignty claim |
| Timeline / research story | Original reports in all named frozen directories | Stage ordering and scoped narrative | Sequence only; no invented dates or numerical trends |
| Reproducibility | `results/jointsla_v2_heldout/validation.json`: exported_request_outcomes_verified, no_lost_or_duplicate_requests; held-out report test record | Direct source counts; read-only startup schema/key/seed/hash checks are separate | Frozen 244-test record is historical, not dashboard test count |
| Original figures / reports | Selected dataset `figures/*.png` and `report.md` | Original assets, no plot alteration | Each caption is the original relative path; displayed on demand |
| Learning Mode | Definitions aligned with frozen analysis and source units | Explanatory only | Not new data or an inferential procedure |

## Missing / differences / scope

Synthetic summaries do not supply `average_vram_residency_gib`; resource tabs explicitly use `vram_gb_seconds` with nominal source units. Available hardware/pressure/held-out averages remain GiB. Frozen burst files do not universally include scaleout_count; the unavailable message appears for those series instead of replacing it with cold_starts. There is no supplied model-class scalar causal explanation. No request-level default view is built. Source selection can inspect small validation/audit artifacts without reading millions of outcomes.

The original approximate values are cross-checks, not constants. Different datasets use different seed cohorts, deadlines/settings and scopes; D0 is the 10-seed decomposition baseline rather than the original 30-seed synthetic estimate. Their differences must not be presented as a report/data conflict. Frozen CI methods/resamples and test family details remain available in source inspection.

## Lazy trajectory panels

Pressure Sweep, Burst Recovery and v2 Held-out Results can explicitly load small per-run `runs/load_X.XX/seed_NNN/POLICY/{slot_trajectories,node_trajectories}.csv.gz`. These are frozen 100-slot / node-slot trajectories, not request outcomes. Fields: slot, latency_ms, cumulative_sla_breach_pct, waiting_requests, burst_service_fraction; node, cpu_utilization, gpu_utilization, gpu_vram_reserved_fraction. Slot latency and cumulative SLA use the frozen arrival-cohort definitions, with later completions where recorded. Already-percent SLA columns stay unchanged; burst/resource fractions ×100. Node pivots contain one node/slot value; no CI is invented for a selected run. GPU compute and VRAM reservation are separate views. Exports retain the selected seed/load/policy population.

## Verified denominator correction

The user-provided tooltip example described completed-request SLA breach percentages. The authoritative `paper_evaluation/accounting.py:request_metrics` defines `sla_breach_rate` over **all offered requests**, with drops/unplaced counted as failures and latency quantiles over completed requests. The dashboard follows that source definition. This distinction is documented rather than silently adopting the prompt example.
# Live execution provenance

Live Experiments reads held-out archived input tapes/configs and the freeze manifest in `results/jointsla_v2_heldout`. It runs the existing policy engines and writes only to unique `dashboard/.cache/live_runs` directories. The live manifest records source hashes, seeds, policies, request accounting and per-run frozen comparisons. Live plots use these newly generated trajectories; no confidence intervals or paper aggregates are recomputed.

