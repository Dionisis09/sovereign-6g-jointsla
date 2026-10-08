"""Retrospective arrival-cohort metrics, including requests completed after T."""
import numpy as np
import pandas as pd


def calculate_metrics(config, workload, result):
    """Every offered request is in the SLA denominator, including admission failure.

    Latency is a request-weighted mean over completed requests, not a mean of
    per-slot means. Unplaced requests have no finite delay and are disclosed.
    Node utilization and offered-load pressure use only the observed T slots.
    """
    outcomes = pd.DataFrame(result["outcomes"])
    slots = pd.DataFrame(result["slots"])
    nodes = pd.DataFrame(result["nodes"])
    cohorts = outcomes.groupby("arrival_slot").agg(
        requests=("request_id", "size"), breaches=("breach", "sum"),
        completed_requests=("latency_ms", "count"), latency_ms=("latency_ms", "mean"),
        service_queue_ms=("service_queue_ms", "mean"), node_queue_ms=("node_queue_ms", "mean"))
    cohorts = cohorts.reindex(range(config.slots)).rename_axis("slot").reset_index()
    for column in ("requests", "breaches", "completed_requests"):
        cohorts[column] = cohorts[column].fillna(0).astype(int)
    cohorts["sla_breach_pct"] = 100 * cohorts.breaches / cohorts.requests.replace(0, np.nan)
    cohorts["cumulative_sla_breach_pct"] = 100 * cohorts.breaches.cumsum() / cohorts.requests.cumsum().replace(0, np.nan)
    slots = slots.merge(cohorts, on="slot", validate="one_to_one")
    traffic = pd.DataFrame(workload.traffic).groupby("slot").agg(
        burst_service_fraction=("burst", "mean"), expected_rate_rps=("expected_rate_rps", "sum"))
    slots = slots.merge(traffic, on="slot", validate="one_to_one")
    if not np.array_equal(slots.requests, slots.observed_arrivals):
        raise AssertionError("cohort and observed request counts differ")
    actions = pd.DataFrame(result["actions"])
    counts = actions.kind.value_counts() if len(actions) else {}
    metrics = dict(requests=len(outcomes), completed_requests=int(outcomes.latency_ms.count()),
                   unplaced_requests=int(outcomes.unplaced.sum()),
                   average_latency_ms=float(outcomes.latency_ms.mean()),
                   time_average_slot_latency_ms=float(slots.latency_ms.mean()),
                   latency_observed_slots=int(slots.latency_ms.count()),
                   average_service_queue_ms=float(outcomes.service_queue_ms.mean()),
                   average_node_queue_ms=float(outcomes.node_queue_ms.mean()),
                   sla_breach_pct=float(outcomes.breach.mean() * 100),
                   migrations=int(counts.get("migrate", 0)), scale_up_actions=int(counts.get("scale_up", 0)),
                   scale_down_actions=int(counts.get("scale_down", 0)), total_actions=len(actions),
                   decision_runtime_mean_ms=float(slots.decision_runtime_ms.mean()),
                   decision_runtime_std_ms=float(slots.decision_runtime_ms.std()), **result["diagnostics"])
    metrics["triggered_downtime_seconds"] = (metrics["scale_up_actions"] * config.cold_start_slots
                                              + metrics["migrations"] * config.migration_down_slots) * config.slot_seconds
    for resource in ("cpu", "gpu", "bandwidth"):
        metrics[f"{resource}_offered_overload_pct"] = float((nodes[f"{resource}_offered_ratio"] > 1).mean() * 100)
        metrics[f"{resource}_saturated_node_slot_pct"] = float((nodes[f"{resource}_utilization"] >= config.high_threshold).mean() * 100)
        for node in range(config.node_count):
            metrics[f"{resource}_utilization_node_{node}_pct"] = float(nodes.loc[nodes.node == node, f"{resource}_utilization"].mean() * 100)
    metrics["mean_gpu_vram_reserved_pct"] = float(nodes.gpu_vram_reserved_fraction.mean() * 100)
    for tier in ("Gold", "Silver", "Bronze"):
        subset = outcomes.loc[outcomes.tier == tier]
        metrics[f"{tier.lower()}_sla_breach_pct"] = float(subset.breach.mean() * 100)
    return metrics, slots, nodes, outcomes


def validate_run(config, workload, result):
    """Independently reconstruct request components, arrivals, and reservation ledger."""
    rows = sorted(result["outcomes"], key=lambda r: r["request_id"])
    if [r["request_id"] for r in rows] != list(range(len(workload.requests))):
        raise AssertionError("lost or duplicated request")
    for request, row in zip(workload.requests, rows):
        service = workload.services[request.service_id]
        assert row["service_id"] == request.service_id and row["arrival_slot"] == request.arrival_slot
        assert row["arrival_s"] == request.arrival_s and row["deadline_ms"] == service.deadline_ms
        if row["unplaced"]:
            assert workload.initial[request.service_id] is None and row["breach"]
            continue
        actual = 1000 * (row["completion_s"] - request.arrival_s)
        compute = (config.preprocess_ms + config.inference_ms + config.postprocess_ms) * request.work_factor
        node = workload.scenario.nodes[row["node"]]
        network = workload.scenario.network_latency_ms[service.ingress, row["node"]] + 1000 * request.payload_mbit / node.bandwidth_capacity_mbps
        components = sum(row[k] for k in ("service_queue_ms", "node_queue_ms", "compute_ms", "network_ms", "lifecycle_penalty_ms"))
        assert abs(actual - row["latency_ms"]) < 1e-6 and abs(actual - components) < 1e-6
        assert abs(compute - row["compute_ms"]) < 1e-6 and abs(network - row["network_ms"]) < 1e-6
        assert row["breach"] == (actual > service.deadline_ms)
        assert all(row[k] >= -1e-7 for k in ("service_queue_ms", "node_queue_ms", "compute_ms", "network_ms", "lifecycle_penalty_ms"))
    reservations = np.zeros_like(workload.scenario.capacities)
    for event in result["reservations"]:
        reservations[event["node"]] += event["sign"] * workload.services[event["service_id"]].reservation
        assert np.all(reservations >= -1e-8) and np.all(reservations <= workload.scenario.capacities + 1e-8)
        assert np.allclose(reservations[event["node"]], [event[k] for k in ("cpu_reserved", "gpu_vram_reserved", "bandwidth_reserved")])
    assert len(result["slots"]) == config.slots and len(result["nodes"]) == config.slots * config.node_count
    for row in result["nodes"]:
        assert all(-1e-8 <= row[f"{r}_utilization"] <= 1 + 1e-8 for r in ("cpu", "gpu", "bandwidth"))
    for row in result["lifecycle"]:
        duration = (config.cold_start_slots if row["kind"] == "cold_start" else config.migration_down_slots) * config.slot_seconds
        assert abs(row["ready_s"] - row["start_s"] - duration) < 1e-8
    assert sum(row["accepted_actions"] for row in result["slots"]) == len(result["actions"])
    return dict(requests_validated=len(rows), reservation_events_validated=len(result["reservations"]),
                node_slots_validated=len(result["nodes"]), latency_component_check=True, capacity_check=True)
