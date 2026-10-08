"""Analyze existing capacity/admission/prewarming data without rerunning them."""
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from catalyst.reused import write_json
from .statistics import bootstrap_mean_ci, summarize


def supplemental_raw(frame):
    out = frame[["seed", "scenario", "node_count"]].copy()
    mapping = dict(sla_breach_rate=("sla_breach_pct", .01),
                   mean_request_latency_ms=("average_latency_ms", 1),
                   mean_slot_latency_ms=("time_average_slot_latency_ms", 1),
                   drop_rate=("drop_pct", .01), Gold_breach_rate=("gold_sla_breach_pct", .01),
                   Silver_breach_rate=("silver_sla_breach_pct", .01), Bronze_breach_rate=("bronze_sla_breach_pct", .01),
                   Gold_drop_rate=("gold_drop_pct", .01), Silver_drop_rate=("silver_drop_pct", .01),
                   Bronze_drop_rate=("bronze_drop_pct", .01),
                   admitted_breach_rate=("admitted_sla_breach_pct", .01),
                   Gold_Silver_breach_rate=("gold_silver_sla_breach_pct", .01),
                   replica_seconds=("replica_seconds", 1), cold_starts=("cold_start_count", 1),
                   cold_penalty_total_ms=("cold_start_penalty_total_ms", 1),
                   cold_starts_overlapping_bursts=("cold_starts_overlapping_bursts", 1),
                   prewarm_actions=("prewarm_actions", 1), migrations=("migrations", 1),
                   scale_outs=("scale_up_actions", 1), scale_ins=("scale_down_actions", 1),
                   mean_vram_reserved_fraction=("mean_gpu_vram_reserved_pct", .01))
    for dest, (source, factor) in mapping.items():
        out[dest] = frame[source]*factor
    return out


def analyze_existing(output, history, capacity):
    """Existing full export verifiers establish validity before statistical reuse."""
    from tools.verify_dynamic_scenarios import verify as verify_scenarios
    from tools.verify_capacity_sweep import verify as verify_capacity
    receipt = dict(capacity_available=False, scenarios_available=False, source_files={})
    if (capacity/"combined_runs.csv").exists():
        verify_capacity(capacity)
        raw = supplemental_raw(pd.read_csv(capacity/"combined_runs.csv"))
        if set(raw.node_count) != set(range(5, 11)) or raw.duplicated(["seed", "node_count"]).any():
            raise ValueError("invalid capacity grid")
        for _, group in raw.groupby("node_count"):
            assert group.seed.sort_values().tolist() == list(range(30))
        records = []
        for nodes, group in raw.groupby("node_count"):
            row = dict(nodes=int(nodes), n=len(group), first_seed=int(group.seed.min()), last_seed=int(group.seed.max()))
            for metric, label in (("sla_breach_rate", "breach_rate"), ("mean_request_latency_ms", "latency_ms"), ("mean_slot_latency_ms", "slot_latency_ms")):
                lo, hi = bootstrap_mean_ci(group.sort_values("seed")[metric], key=f"capacity:{nodes}:{metric}")
                row.update({f"mean_{label}": float(group[metric].mean()), f"{label}_ci95_lower": lo, f"{label}_ci95_upper": hi})
            records.append(row)
        raw.to_csv(output/"capacity_raw_results.csv", index=False)
        pd.DataFrame(records).to_csv(output/"capacity_summary.csv", index=False)
        receipt["capacity_available"] = True
    if (history/"runs.csv").exists():
        verify_scenarios(history)
        raw = supplemental_raw(pd.read_csv(history/"runs.csv"))
        for _, group in raw.groupby("scenario"):
            assert group.seed.sort_values().tolist() == list(range(30))
        raw.to_csv(output/"scenario_raw_results.csv", index=False)
        summarize(raw, ("scenario",), exclude=("node_count",)).to_csv(output/"scenario_summary_statistics.csv", index=False)
        paired = []
        for scenario in ("predictive", "admission"):
            for metric in ("sla_breach_rate", "mean_request_latency_ms", "drop_rate", "Gold_Silver_breach_rate", "replica_seconds", "cold_starts"):
                p = raw.pivot(index="seed", columns="scenario", values=metric).sort_index()
                d = p.baseline-p[scenario]
                lo, hi = bootstrap_mean_ci(d, key=f"supplementary:{scenario}:{metric}")
                paired.append(dict(scenario=scenario, metric=metric, n=len(d), baseline_mean=float(p.baseline.mean()),
                                   scenario_mean=float(p[scenario].mean()), baseline_minus_scenario=float(d.mean()),
                                   difference_ci95_lower=lo, difference_ci95_upper=hi,
                                   positive_difference="lower scenario value", analysis="exploratory; not a main-policy test"))
        pd.DataFrame(paired).to_csv(output/"supplementary_paired_summary.csv", index=False)
        receipt["scenarios_available"] = True
    for path in (capacity/"combined_runs.csv", capacity/"protocol.json", history/"runs.csv", history/"protocol.json"):
        if path.exists():
            receipt["source_files"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt["seed_scope"] = "Supplemental seeds 0–29; main seeds 1–30; 29 shared seeds, not independent replication. No supplemental simulations rerun."
    if not receipt["capacity_available"]:
        receipt["capacity_limitation"] = "No verified 30-seed capacity data: existing results preserved; a new run is required for CI."
    write_json(output/"supplementary_provenance.json", receipt)
    return receipt
