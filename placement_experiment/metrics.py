"""Evaluate every method on final resource totals, not optimistic insertion costs."""
import numpy as np
from .data_generation import estimate_latency


def calculate_metrics(config, scenario, assignments):
    """Return run metrics plus auditable per-application latency outcomes.

    Average latency is traffic-weighted among placed apps. SLA violation rate
    includes unplaced offered traffic; placed_sla_violation_rate is conditional
    on placement. CPU/GPU utilization measures reserved capacity, not busy time.
    """
    expected = {a.application_id for a in scenario.applications}
    if set(assignments) != expected:
        raise ValueError("one assignment or explicit None required per application")
    lookup = {n.node_id: i for i, n in enumerate(scenario.nodes)}
    usage = np.zeros((len(scenario.nodes), 3))
    for app in scenario.applications:
        node = assignments[app.application_id]
        if node is not None:
            if node not in lookup:
                raise ValueError("unknown node")
            usage[lookup[node]] += app.demand
    if np.any(usage > scenario.capacities + 1e-9):
        raise ValueError("infeasible placement exceeds CPU/GPU/bandwidth capacity")
    outcomes = []
    total_load = sum(a.traffic_load_rps for a in scenario.applications)
    placed_load = failure_load = placed_failure_load = weighted_latency = 0.
    unplaced = 0
    for app in scenario.applications:
        node = assignments[app.application_id]
        latency = None
        if node is None:
            unplaced += 1
            failure_load += app.traffic_load_rps
        else:
            latency = estimate_latency(config, scenario, app, lookup[node], usage[lookup[node]])
            placed_load += app.traffic_load_rps
            weighted_latency += latency * app.traffic_load_rps
            if latency > app.latency_requirement_ms:
                placed_failure_load += app.traffic_load_rps
                failure_load += app.traffic_load_rps
        outcomes.append(dict(application_id=app.application_id, node_id=node, latency_ms=latency,
                             latency_requirement_ms=app.latency_requirement_ms, traffic_load_rps=app.traffic_load_rps,
                             sla_violated=node is None or latency > app.latency_requirement_ms))
    metrics = dict(average_latency_ms=weighted_latency / placed_load if placed_load else None,
                   sla_violation_rate=failure_load / total_load if total_load else None,
                   placed_sla_violation_rate=placed_failure_load / placed_load if placed_load else None,
                   unplaced_applications=unplaced)
    for i, node in enumerate(scenario.nodes):
        for resource, utilization in zip(("cpu", "gpu", "bandwidth"), usage[i] / node.capacity):
            metrics[f"{resource}_utilization_node_{node.node_id}"] = float(utilization)
    return metrics, outcomes

