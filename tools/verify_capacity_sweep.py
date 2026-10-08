"""Reconstruct the new request evidence and the paired 5–10-node capacity curve."""
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from catalyst.reused import digest, write_json


def verify(output):
    output = Path(output)
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    history = Path(protocol["historical_output"])
    assert digest((history / "runs.csv").read_text(encoding="utf-8")) == protocol["historical_runs_hash"]
    assert digest((history / "protocol.json").read_text(encoding="utf-8")) == protocol["historical_protocol_hash"]
    for path, fingerprint in protocol["source_hashes"].items():
        assert digest(Path(path).read_text(encoding="utf-8")) == fingerprint
    config = protocol["config"]
    runs = pd.read_csv(output / "runs.csv")
    combined = pd.read_csv(output / "combined_runs.csv")
    slots = pd.read_csv(output / "slot_trajectories.csv")
    nodes = pd.read_csv(output / "node_trajectories.csv")
    summary = pd.read_csv(output / "summary.csv", index_col=["scenario", "policy", "node_count"])
    assert len(runs) == config["trials"]*3 and len(combined) == config["trials"]*6
    assert combined.groupby("seed").traffic_hash.nunique().eq(1).all()
    assert combined.groupby("seed").requests.nunique().eq(1).all()
    assert set(combined.node_count) == set(range(5, 11))
    metadata, references = {}, []
    for seed, group in runs.groupby("seed", sort=False):
        with gzip.open(history / "inputs" / f"seed_{seed:03d}_capacity_7.json.gz", "rt", encoding="utf-8") as stream:
            prefix = json.load(stream)
        for row in group.itertuples():
            with gzip.open(output / "inputs" / f"seed_{seed:03d}_{row.scenario}.json.gz", "rt", encoding="utf-8") as stream:
                value = json.load(stream)
            assert digest(value) == row.workload_hash
            assert digest({k: value[k] for k in ("seed", "services", "requests", "traffic")}) == row.traffic_hash
            assert value["scenario"]["nodes"][:7] == prefix["scenario"]["nodes"]
            assert np.array_equal(np.array(value["scenario"]["network_latency_ms"])[:7, :7], prefix["scenario"]["network_latency_ms"])
            if row.node_count == 8:
                references.extend(dict(seed=seed, **r) for r in value["requests"])
            metadata[seed, row.scenario] = {k: value[k] for k in ("services", "scenario", "gpu_units")}
        for count in (8, 9):
            small, large = metadata[seed, f"capacity_{count}"], metadata[seed, "capacity_10"]
            assert small["scenario"]["nodes"] == large["scenario"]["nodes"][:count]
            assert np.array_equal(small["scenario"]["network_latency_ms"], np.array(large["scenario"]["network_latency_ms"])[:count, :count])
    reference = pd.DataFrame(references)
    seen, totals, checked = {}, {}, 0
    components = ["service_queue_ms", "node_queue_ms", "compute_ms", "network_ms", "lifecycle_penalty_ms"]
    for chunk in pd.read_csv(output / "request_outcomes.csv.gz", chunksize=40_000, dtype={"drop_reason": "string"}):
        assert not chunk.dropped.any() and not chunk.unplaced.any()
        merged = chunk.merge(reference, on=["seed", "request_id"], suffixes=("", "_input"), validate="many_to_one")
        assert len(merged) == len(chunk)
        for field in ("service_id", "arrival_slot", "arrival_s"):
            assert np.allclose(merged[field], merged[f"{field}_input"], atol=1e-12, rtol=0)
        for key, group in merged.groupby(["seed", "scenario"], sort=False):
            value = metadata[key]
            ids = set(group.request_id)
            old = seen.setdefault(key, set())
            assert len(ids) == len(group) and not old.intersection(ids)
            old.update(ids)
            actual = 1000*(group.completion_s-group.arrival_s)
            compute = group.work_factor*sum(config[f] for f in ("preprocess_ms", "inference_ms", "postprocess_ms"))
            ingress = group.service_id.map({s["service_id"]: s["ingress"] for s in value["services"]}).to_numpy(dtype=int)
            target = group.node.to_numpy(dtype=int)
            matrix = np.array(value["scenario"]["network_latency_ms"])
            bandwidth = np.array([n["bandwidth_capacity_mbps"] for n in value["scenario"]["nodes"]])
            network = matrix[ingress, target]+1000*group.payload_mbit/bandwidth[target]
            deadline = group.service_id.map({s["service_id"]: s["deadline_ms"] for s in value["services"]})
            tier = group.service_id.map({s["service_id"]: s["tier"] for s in value["services"]})
            assert np.allclose(group.deadline_ms, deadline) and (group.tier == tier).all()
            assert np.allclose(actual, group.latency_ms, atol=1e-6, rtol=0)
            assert np.allclose(actual, group[components].sum(axis=1), atol=1e-6, rtol=0)
            assert np.allclose(group.compute_ms, compute, atol=1e-6, rtol=0)
            assert np.allclose(group.network_ms, network, atol=1e-6, rtol=0)
            assert np.array_equal(group.breach, actual > deadline)
            accumulator = totals.setdefault(key, [0, 0, 0.])
            accumulator[0] += len(group)
            accumulator[1] += int(group.breach.sum())
            accumulator[2] += float(group.latency_ms.sum())
        checked += len(chunk)
    for row in runs.itertuples():
        count, breaches, latency = totals[row.seed, row.scenario]
        assert count == row.requests == len(seen[row.seed, row.scenario])
        assert np.isclose(latency/count, row.average_latency_ms)
        assert np.isclose(100*breaches/count, row.sla_breach_pct)
        trajectory = slots.loc[(slots.seed == row.seed) & (slots.scenario == row.scenario)]
        assert len(trajectory) == config["slots"] and trajectory.requests.sum() == count
        assert np.isclose(trajectory.latency_ms.mean(), row.time_average_slot_latency_ms)
        assert np.isclose(trajectory.cumulative_sla_breach_pct.iloc[-1], row.sla_breach_pct)
    keys = ("seed", "scenario", "policy", "node_count", "workload_hash", "traffic_hash")
    metrics = [c for c in combined if c not in keys]
    for key, group in combined.groupby(["scenario", "policy", "node_count"]):
        for metric in metrics:
            for statistic, expected in (("mean", group[metric].mean()), ("std", group[metric].std()), ("count", group[metric].count())):
                assert np.isclose(summary.loc[key, f"{metric}_{statistic}"], expected, atol=1e-8, equal_nan=True)
    gains = pd.read_csv(output / "marginal_gains.csv")
    for row in gains.itertuples():
        pivot = combined.pivot(index="seed", columns="node_count", values=row.metric)
        differences = pivot[row.from_nodes]-pivot[row.to_nodes]
        assert np.isclose(differences.mean(), row.mean_reduction) and np.isclose(differences.std(), row.paired_std)
        assert (differences > 0).sum() == row.seeds_improved
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
    knee = json.loads((output / "knee_analysis.json").read_text(encoding="utf-8"))
    x = np.arange(5, 11)
    y = combined.groupby("node_count").sla_breach_pct.mean().to_numpy()
    candidate = knee["fitted"]["candidate"]
    design = np.column_stack([np.ones(6), x, np.maximum(0, x-candidate)])
    beta = np.linalg.lstsq(design, y, rcond=None)[0]
    assert np.allclose(design@beta, knee["fitted"]["fitted_values"])
    assert sum(knee["bootstrap_knee_counts"].values()) == 1000
    report = dict(new_runs=len(runs), combined_capacity_runs=len(combined), requests_checked=checked,
                  slot_rows=len(slots), node_rows=len(nodes), identical_paired_traffic=True,
                  nested_topology_prefixes_verified=True, source_and_historical_hashes_verified=True,
                  request_latency_and_breaches_reconstructed=True, capacity_ledger_verified=True,
                  means_std_counts_verified=True, paired_marginal_gains_verified=True, hinge_fit_verified=True)
    write_json(output / "export_verification.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/capacity_sweep"))
    verify(parser.parse_args().output)
