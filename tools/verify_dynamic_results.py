"""Verify exported dynamic evidence without running the simulator again.

Run from the repository root: python -m tools.verify_dynamic_results
"""
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from catalyst.reused import digest, write_json


def verify(output):
    output = Path(output)
    runs = pd.read_csv(output / "runs.csv")
    slots = pd.read_csv(output / "slot_trajectories.csv")
    nodes = pd.read_csv(output / "node_trajectories.csv")
    summary_path = output / "original_summary.csv"
    if not summary_path.exists():
        summary_path = output / "summary.csv"
    summary = pd.read_csv(summary_path, index_col="policy")
    protocol = json.loads((output / "protocol.json").read_text())
    config = json.loads((output / "config.json").read_text())
    assert digest(config) == protocol["config_hash"]
    for path, fingerprint in protocol["source_hashes"].items():
        assert digest(Path(path.replace("\\", "/")).read_text(encoding="utf-8")) == fingerprint, path
    reference_rows, inputs = [], {}
    for seed, group in runs.groupby("seed"):
        with gzip.open(output / "inputs" / f"seed_{seed:03d}.json.gz", "rt", encoding="utf-8") as stream:
            value = json.load(stream)
        assert group.workload_hash.nunique() == 1 and digest(value) == group.workload_hash.iloc[0]
        assert group.policy.nunique() == 4 and group.requests.nunique() == 1
        assert group.requests.iloc[0] == len(value["requests"])
        inputs[seed] = value
        reference_rows.extend(dict(seed=seed, **row) for row in value["requests"])
    reference = pd.DataFrame(reference_rows)
    aggregates, seen = {}, {}
    requests_checked = 0
    components = ["service_queue_ms", "node_queue_ms", "compute_ms", "network_ms", "lifecycle_penalty_ms"]
    for chunk in pd.read_csv(output / "request_outcomes.csv.gz", chunksize=30_000):
        merged = chunk.merge(reference, on=["seed", "request_id"], suffixes=("", "_input"), validate="many_to_one")
        assert len(merged) == len(chunk)
        for column in ("service_id", "arrival_slot", "arrival_s"):
            assert np.allclose(merged[column], merged[f"{column}_input"], atol=1e-12, rtol=0)
        for seed, subset in merged.groupby("seed"):
            value = inputs[seed]
            deadline = subset.service_id.map({s["service_id"]: s["deadline_ms"] for s in value["services"]})
            assert np.allclose(subset.deadline_ms, deadline)
            valid = subset.loc[~subset.unplaced]
            actual = (valid.completion_s - valid.arrival_s) * 1000
            compute = valid.work_factor * sum(config[c] for c in ("preprocess_ms", "inference_ms", "postprocess_ms"))
            matrix = np.array(value["scenario"]["network_latency_ms"])
            ingress = valid.service_id.map({s["service_id"]: s["ingress"] for s in value["services"]}).to_numpy(dtype=int)
            target = valid.node.to_numpy(dtype=int)
            bandwidth = np.array([n["bandwidth_capacity_mbps"] for n in value["scenario"]["nodes"]])
            network = matrix[ingress, target] + 1000 * valid.payload_mbit / bandwidth[target]
            assert np.allclose(actual, valid.latency_ms, atol=1e-6, rtol=0)
            assert np.allclose(actual, valid[components].sum(axis=1), atol=1e-6, rtol=0)
            assert np.allclose(compute, valid.compute_ms, atol=1e-6, rtol=0)
            assert np.allclose(network, valid.network_ms, atol=1e-6, rtol=0)
            assert np.array_equal(valid.breach, valid.latency_ms > valid.deadline_ms)
        for key, group in merged.groupby(["seed", "policy"]):
            ids = set(group.request_id)
            old_ids = seen.setdefault(key, set())
            assert len(ids) == len(group) and not old_ids.intersection(ids)
            old_ids.update(ids)
            current = aggregates.setdefault(key, dict(requests=0, breaches=0, latency_sum=0., completions=0))
            current["requests"] += len(group)
            current["breaches"] += int(group.breach.sum())
            current["latency_sum"] += float(group.latency_ms.sum())
            current["completions"] += int(group.latency_ms.count())
        requests_checked += len(chunk)
    for row in runs.itertuples():
        totals = aggregates[row.seed, row.policy]
        assert totals["requests"] == row.requests and totals["completions"] == row.completed_requests
        assert len(seen[row.seed, row.policy]) == row.requests
        assert np.isclose(totals["latency_sum"] / totals["completions"], row.average_latency_ms)
        assert np.isclose(100 * totals["breaches"] / totals["requests"], row.sla_breach_pct)
        trajectory = slots.loc[(slots.seed == row.seed) & (slots.policy == row.policy)]
        assert len(trajectory) == config["slots"] and trajectory.requests.sum() == row.requests
        assert np.isclose(trajectory.latency_ms.mean(), row.time_average_slot_latency_ms)
        assert np.isclose(100 * trajectory.breaches.sum() / trajectory.requests.sum(), row.sla_breach_pct)
        assert np.isclose(trajectory.cumulative_sla_breach_pct.iloc[-1], row.sla_breach_pct)
    metrics = [c for c in runs if c not in ("seed", "policy", "workload_hash")]
    for policy, group in runs.groupby("policy"):
        for metric in metrics:
            for name, expected in (("mean", group[metric].mean()), ("std", group[metric].std()), ("count", group[metric].count())):
                assert np.isclose(summary.loc[policy, f"{metric}_{name}"], expected, atol=1e-8), (policy, metric, name)
    for resource in ("cpu", "gpu", "bandwidth"):
        assert nodes[f"{resource}_utilization"].between(-1e-8, 1 + 1e-8).all()
    events = pd.read_csv(output / "reservation_events.csv")
    for (seed, policy), group in events.groupby(["seed", "policy"], sort=False):
        value = inputs[seed]
        capacities = np.array([[n["cpu_capacity"], n["gpu_capacity"], n["bandwidth_capacity_mbps"]] for n in value["scenario"]["nodes"]])
        reserved = np.zeros_like(capacities)
        for event in group.itertuples():
            s = value["services"][event.service_id]
            reserved[event.node] += event.sign * np.array([s["cpu_cores"], s["gpu_vram_gb"], s["bandwidth_mbps"]])
            assert np.all(reserved >= -1e-8) and np.all(reserved <= capacities + 1e-8)
            assert np.allclose(reserved[event.node], [event.cpu_reserved, event.gpu_vram_reserved, event.bandwidth_reserved])
    report = dict(runs=len(runs), requests_checked=requests_checked, slot_rows=len(slots), node_rows=len(nodes),
                  input_hashes_verified=True, source_hashes_verified=True, request_components_verified=True,
                  latency_and_sla_reconstructed=True, summary_mean_std_count_reconstructed=True,
                  reservation_ledger_verified=True, physical_utilization_bounded=True)
    write_json(output / "export_verification.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/dynamic"))
    verify(parser.parse_args().output)
