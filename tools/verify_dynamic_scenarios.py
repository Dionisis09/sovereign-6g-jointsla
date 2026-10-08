"""Independent reconstruction of the five paired scenario exports."""
import argparse
import gzip
import json
from pathlib import Path
import math
import numpy as np
import pandas as pd
from catalyst.reused import digest, write_json


def verify(output):
    output = Path(output)
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    config, settings = protocol["base_config"], protocol["scenarios"]
    for name, fingerprint in protocol["source_hashes"].items():
        assert digest(Path(name).read_text(encoding="utf-8")) == fingerprint, name
    runs = pd.read_csv(output / "runs.csv")
    slots = pd.read_csv(output / "slot_trajectories.csv")
    nodes = pd.read_csv(output / "node_trajectories.csv")
    summary = pd.read_csv(output / "summary.csv", index_col=["scenario", "policy", "node_count"])
    assert len(runs) == config["trials"] * 5
    assert runs.groupby("seed").scenario.nunique().eq(5).all()
    assert runs.groupby("seed").traffic_hash.nunique().eq(1).all()
    assert runs.groupby("seed").requests.nunique().eq(1).all()
    reference_rows, metadata, arrivals, burst_masks = [], {}, {}, {}
    for row in runs.itertuples():
        with gzip.open(output / "inputs" / f"seed_{row.seed:03d}_{row.scenario}.json.gz", "rt", encoding="utf-8") as stream:
            value = json.load(stream)
        assert digest(value) == row.workload_hash
        paired = {key: value[key] for key in ("seed", "services", "requests", "traffic")}
        assert digest(paired) == row.traffic_hash
        assert len(value["requests"]) == row.requests
        if row.scenario == "baseline":
            reference_rows.extend(dict(seed=row.seed, **r) for r in value["requests"])
            arrivals[row.seed] = pd.DataFrame(value["traffic"]).pivot(index="slot", columns="service_id", values="arrivals").to_numpy()
            burst_masks[row.seed] = pd.DataFrame(value["traffic"]).pivot(index="slot", columns="service_id", values="burst").to_numpy()
        metadata[row.seed, row.scenario] = {key: value[key] for key in ("scenario", "services", "gpu_units", "initial")}
    reference = pd.DataFrame(reference_rows)
    seen, totals, outcome_drops = {}, {}, set()
    component_names = ["service_queue_ms", "node_queue_ms", "compute_ms", "network_ms", "lifecycle_penalty_ms"]
    checked = 0
    for chunk in pd.read_csv(output / "request_outcomes.csv.gz", chunksize=40_000, dtype={"drop_reason": "string"}):
        merged = chunk.merge(reference, on=["seed", "request_id"], suffixes=("", "_input"), validate="many_to_one")
        assert len(merged) == len(chunk)
        for column in ("service_id", "arrival_slot", "arrival_s"):
            assert np.allclose(merged[column], merged[f"{column}_input"], atol=1e-12, rtol=0)
        for key, group in merged.groupby(["seed", "scenario"], sort=False):
            value = metadata[key]
            ids = set(group.request_id)
            previous = seen.setdefault(key, set())
            assert len(ids) == len(group) and not previous.intersection(ids)
            previous.update(ids)
            deadlines = group.service_id.map({s["service_id"]: s["deadline_ms"] for s in value["services"]})
            tiers = group.service_id.map({s["service_id"]: s["tier"] for s in value["services"]})
            assert np.allclose(group.deadline_ms, deadlines) and (group.tier == tiers).all()
            dropped = group.loc[group.dropped]
            assert key[1] == "admission" or not len(dropped)
            assert dropped.tier.eq("Bronze").all() and dropped.breach.all() and dropped.latency_ms.isna().all()
            assert dropped.drop_reason.eq("bronze_queue_threshold").all() and dropped.completion_s.isna().all()
            outcome_drops.update((key[0], key[1], int(i)) for i in dropped.request_id)
            valid = group.loc[~group.dropped & ~group.unplaced]
            actual = (valid.completion_s-valid.arrival_s)*1000
            compute = valid.work_factor * sum(config[c] for c in ("preprocess_ms", "inference_ms", "postprocess_ms"))
            matrix = np.array(value["scenario"]["network_latency_ms"])
            ingress = valid.service_id.map({s["service_id"]: s["ingress"] for s in value["services"]}).to_numpy(dtype=int)
            target = valid.node.to_numpy(dtype=int)
            bandwidth = np.array([n["bandwidth_capacity_mbps"] for n in value["scenario"]["nodes"]])
            network = matrix[ingress, target] + 1000*valid.payload_mbit/bandwidth[target]
            assert np.allclose(actual, valid.latency_ms, atol=1e-6, rtol=0)
            assert np.allclose(actual, valid[component_names].sum(axis=1), atol=1e-6, rtol=0)
            assert np.allclose(compute, valid.compute_ms, atol=1e-6, rtol=0)
            assert np.allclose(network, valid.network_ms, atol=1e-6, rtol=0)
            assert np.array_equal(valid.breach, valid.latency_ms > valid.deadline_ms)
            assert (valid[component_names] >= -1e-7).all().all()
            aggregate = totals.setdefault(key, dict(requests=0, completed=0, breaches=0, drops=0, latency=0., admitted_breaches=0, cold_penalty=0.,
                                tiers={tier: dict(requests=0, breaches=0, drops=0, completed=0, admitted_breaches=0) for tier in ("Gold", "Silver", "Bronze")}))
            aggregate["requests"] += len(group)
            aggregate["completed"] += len(valid)
            aggregate["breaches"] += int(group.breach.sum())
            aggregate["drops"] += int(group.dropped.sum())
            aggregate["latency"] += float(valid.latency_ms.sum())
            aggregate["admitted_breaches"] += int(valid.breach.sum())
            aggregate["cold_penalty"] += float(valid.loc[valid.lifecycle_penalty_ms == config["cold_penalty_ms"], "lifecycle_penalty_ms"].sum())
            for tier, tier_rows in group.groupby("tier"):
                target = aggregate["tiers"][tier]
                admitted = tier_rows.loc[~tier_rows.dropped & ~tier_rows.unplaced]
                for name, quantity in (("requests", len(tier_rows)), ("breaches", int(tier_rows.breach.sum())),
                                       ("drops", int(tier_rows.dropped.sum())), ("completed", len(admitted)),
                                       ("admitted_breaches", int(admitted.breach.sum()))):
                    target[name] += quantity
        checked += len(chunk)
    for row in runs.itertuples():
        aggregate = totals[row.seed, row.scenario]
        assert aggregate["requests"] == row.requests and aggregate["completed"] == row.completed_requests
        assert len(seen[row.seed, row.scenario]) == row.requests
        assert np.isclose(aggregate["latency"]/aggregate["completed"], row.average_latency_ms)
        assert np.isclose(aggregate["cold_penalty"], row.cold_start_penalty_total_ms)
        for name, numerator, denominator in (("sla_breach_pct", "breaches", "requests"), ("drop_pct", "drops", "requests"),
                                              ("admitted_sla_breach_pct", "admitted_breaches", "completed")):
            assert np.isclose(getattr(row, name), 100*aggregate[numerator]/aggregate[denominator])
        for tier, value in aggregate["tiers"].items():
            for suffix, numerator, denominator in (("sla_breach_pct", "breaches", "requests"), ("drop_pct", "drops", "requests"),
                                                   ("admitted_sla_breach_pct", "admitted_breaches", "completed")):
                assert np.isclose(getattr(row, f"{tier.lower()}_{suffix}"), 100*value[numerator]/value[denominator])
        protected = [aggregate["tiers"][tier] for tier in ("Gold", "Silver")]
        assert np.isclose(row.gold_silver_sla_breach_pct, 100*sum(t["breaches"] for t in protected)/sum(t["requests"] for t in protected))
        trajectory = slots.loc[(slots.seed == row.seed) & (slots.scenario == row.scenario)]
        assert len(trajectory) == config["slots"] and trajectory.requests.sum() == row.requests
        assert np.isclose(trajectory.latency_ms.mean(), row.time_average_slot_latency_ms)
        assert np.isclose(trajectory.cumulative_sla_breach_pct.iloc[-1], row.sla_breach_pct)
        assert np.isclose(trajectory.cumulative_drop_pct.iloc[-1], row.drop_pct)
        assert np.isclose(trajectory.cumulative_admitted_sla_breach_pct.iloc[-1], row.admitted_sla_breach_pct)
    event_drops, admission_count, seen_admissions = set(), 0, {}
    for chunk in pd.read_csv(output / "admission_events.csv.gz", chunksize=40_000):
        merged = chunk.merge(reference, on=["seed", "request_id"], suffixes=("", "_input"), validate="many_to_one")
        assert len(merged) == len(chunk)
        assert np.allclose(merged.time_s, merged.arrival_s, atol=1e-12, rtol=0)
        assert (merged.service_id == merged.service_id_input).all()
        for key, group in merged.groupby(["seed", "scenario"], sort=False):
            value = metadata[key]
            ids = set(group.request_id)
            previous = seen_admissions.setdefault(key, set())
            assert len(ids) == len(group) and not previous.intersection(ids)
            previous.update(ids)
            deadline = group.service_id.map({s["service_id"]: s["deadline_ms"] for s in value["services"]})
            tier = group.service_id.map({s["service_id"]: s["tier"] for s in value["services"]})
            compute = sum(config[c] for c in ("preprocess_ms", "inference_ms", "postprocess_ms"))
            budget = np.maximum(1, group.ready_replicas)*np.maximum(1, np.ceil(deadline/compute))
            assert np.array_equal(group.queue_budget, budget)
            expected = (key[1] == "admission") & tier.eq("Bronze") & (group.queue_depth/group.queue_budget > settings["admission_threshold"])
            assert np.array_equal(group.dropped, expected)
            event_drops.update((key[0], key[1], int(i)) for i in group.loc[group.dropped, "request_id"])
        admission_count += len(chunk)
    assert admission_count == checked and event_drops == outcome_drops
    assert seen_admissions == seen
    metrics = [c for c in runs if c not in ("seed", "scenario", "policy", "node_count", "workload_hash", "traffic_hash")]
    for key, group in runs.groupby(["scenario", "policy", "node_count"], sort=False):
        for metric in metrics:
            for stat, expected in (("mean", group[metric].mean()), ("std", group[metric].std()), ("count", group[metric].count())):
                assert np.isclose(summary.loc[key, f"{metric}_{stat}"], expected, atol=1e-8, equal_nan=True), (key, metric, stat)
    for resource in ("cpu", "gpu", "bandwidth"):
        assert nodes[f"{resource}_utilization"].between(-1e-8, 1+1e-8).all()
    ledger = pd.read_csv(output / "reservation_events.csv")
    for key, group in ledger.groupby(["seed", "scenario"], sort=False):
        value = metadata[key]
        capacities = np.array([[n["cpu_capacity"], n["gpu_capacity"], n["bandwidth_capacity_mbps"]] for n in value["scenario"]["nodes"]])
        reserved = np.zeros_like(capacities)
        for event in group.itertuples():
            service = value["services"][event.service_id]
            reserved[event.node] += event.sign*np.array([service["cpu_cores"], service["gpu_vram_gb"], service["bandwidth_mbps"]])
            assert np.all(reserved >= -1e-8) and np.all(reserved <= capacities+1e-8)
            assert np.allclose(reserved[event.node], [event.cpu_reserved, event.gpu_vram_reserved, event.bandwidth_reserved])
    forecasts = pd.read_csv(output / "forecast_trajectories.csv")
    for seed, group in forecasts.groupby("seed"):
        history = arrivals[seed]
        base = np.array([s["base_rate_rps"] for s in metadata[seed, "predictive"]["services"]])
        onset, last_detection, crossing = None, -10_000, False
        window = settings["moving_average_slots"]
        for event in group.itertuples():
            slot = event.slot
            ma = history[max(0, slot-window):slot].mean(axis=0)/config["slot_seconds"] if slot >= window else base
            assert np.isclose(event.aggregate_ma_rps, ma.sum())
            elevated = slot >= window and ma.sum() > base.sum()*settings["burst_detection_ratio"]
            assert event.detected == elevated
            if elevated and not crossing and slot-last_detection >= config["burst_period"]//2:
                onset, last_detection = max(0, slot-window//2), slot
            crossing = elevated
            predicted = onset+config["burst_period"] if onset is not None else None
            if predicted is not None:
                while predicted < slot:
                    predicted += config["burst_period"]
                assert event.predicted_burst_slot == predicted
            else:
                assert pd.isna(event.predicted_burst_slot)
    prewarms = pd.read_csv(output / "prewarm_proposals.csv")
    assert (prewarms.predicted_burst_slot-prewarms.slot).between(1, 2).all()
    actions = pd.read_csv(output / "actions.csv")
    lifecycle = pd.read_csv(output / "lifecycle_events.csv")
    for row in runs.itertuples():
        subset = actions.loc[(actions.seed == row.seed) & (actions.scenario == row.scenario)]
        assert len(subset) == row.total_actions
        assert (subset.kind == "scale_up").sum() == row.scale_up_actions
        assert (subset.kind == "scale_down").sum() == row.scale_down_actions
        assert (subset.kind == "migrate").sum() == row.migrations
        cold = lifecycle.loc[(lifecycle.seed == row.seed) & (lifecycle.scenario == row.scenario) & (lifecycle.kind == "cold_start")]
        assert len(cold) == row.cold_start_count
        owners = subset.loc[subset.kind == "scale_up"].set_index("replica_id").service_id.to_dict()
        overlap = 0
        for event in cold.itertuples():
            assert np.isclose(event.ready_s-event.start_s, config["cold_start_slots"]*config["slot_seconds"])
            start = int(math.floor(event.start_s/config["slot_seconds"]+1e-8))
            stop = int(math.ceil(event.ready_s/config["slot_seconds"]-1e-8))
            overlap += any(burst_masks[row.seed][slot, owners[event.replica_id]]
                           for slot in range(start, min(stop, config["slots"])))
        assert overlap == row.cold_starts_overlapping_bursts
        proposals = prewarms.loc[(prewarms.seed == row.seed) & (prewarms.scenario == row.scenario)]
        accepted = {(a.slot, a.service_id, a.target_node) for a in subset.loc[subset.kind == "scale_up"].itertuples()}
        assert sum((r.slot, r.service_id, r.target) in accepted for r in proposals.itertuples()) == row.prewarm_actions
    original = output.parent / "dynamic" / "runs.csv"
    baseline_matches = None
    if original.exists():
        historical = pd.read_csv(original).query("policy == 'sla_aware'").set_index("seed")
        fresh = runs.query("scenario == 'baseline'").set_index("seed")
        seeds = fresh.index.intersection(historical.index)
        comparable = [c for c in historical.select_dtypes(include="number") if "runtime" not in c and c in fresh]
        assert np.allclose(fresh.loc[seeds, comparable], historical.loc[seeds, comparable], atol=1e-8, rtol=1e-9)
        baseline_matches = len(seeds)
    report = dict(runs=len(runs), paired_seeds=config["trials"], request_outcomes_checked=checked,
                  admission_decisions_checked=admission_count, drops_checked=len(outcome_drops),
                  slot_rows=len(slots), node_rows=len(nodes), paired_traffic_verified=True,
                  request_components_and_tier_denominators_verified=True, summary_mean_std_count_verified=True,
                  admission_threshold_verified=True, causal_forecasts_verified=True,
                  prewarm_lead_verified=True, physical_capacity_and_reservations_verified=True, source_hashes_verified=True)
    report["historical_baseline_seeds_reproduced"] = baseline_matches
    report["cold_start_costs_verified"] = True
    write_json(output / "export_verification.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/dynamic_scenarios"))
    verify(parser.parse_args().output)
