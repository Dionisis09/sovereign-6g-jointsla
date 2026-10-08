"""Derive request-level metrics without changing legacy metric definitions."""
import numpy as np
import pandas as pd

POLICIES = ("static", "reactive", "periodic", "sla_aware")
LABELS = dict(static="Static", reactive="Reactive", periodic="Periodic", sla_aware="SLA-aware")
PRIMARY = ("sla_breach_rate", "mean_request_latency_ms", "p95_latency_ms", "p99_latency_ms")
TIERS = ("Gold", "Silver", "Bronze")


def request_metrics(outcomes):
    """All-offered failure rates; linear quantiles of completed request delays.

    Drop and unplaced flags are mutually exclusive in the existing experiment.
    Requests without completion have no invented latency. Fractions use [0,1].
    """
    f = pd.DataFrame(outcomes)
    if f.empty:
        raise ValueError("no offered requests; latency/rates cannot be estimated")
    if f.request_id.duplicated().any():
        raise ValueError("duplicate request outcome")
    completed = f.latency_ms.notna()
    dropped = f.get("dropped", pd.Series(False, index=f.index)).astype(bool)
    unplaced = f.get("unplaced", pd.Series(False, index=f.index)).astype(bool)
    if (dropped & unplaced).any() or not (completed | dropped | unplaced).all():
        raise ValueError("unaccounted or multiply classified request")
    if ((dropped | unplaced) & (~f.breach.astype(bool) | completed)).any():
        raise ValueError("drops/unplaced must be failures without completed latency")
    latency = f.loc[completed, "latency_ms"].to_numpy(dtype=float)
    if not len(latency) or not np.isfinite(latency).all() or (latency < -1e-7).any():
        raise ValueError("no finite completed latency sample")
    quantiles = np.quantile(latency, [.5, .95, .99], method="linear")
    m = dict(total_requests=len(f), completed_requests=int(completed.sum()),
             dropped_requests=int(dropped.sum()), unplaced_requests=int(unplaced.sum()),
             sla_breaches=int(f.breach.sum()), sla_breach_rate=float(f.breach.mean()),
             drop_rate=float(dropped.mean()), mean_latency_ms=float(latency.mean()),
             mean_request_latency_ms=float(latency.mean()), median_latency_ms=float(quantiles[0]),
             p95_latency_ms=float(quantiles[1]), p99_latency_ms=float(quantiles[2]),
             mean_slot_latency_ms=float(f.groupby("arrival_slot").latency_ms.mean().mean()))
    for tier in TIERS:
        subset = f.loc[f.tier == tier]
        m[f"{tier}_requests"] = len(subset)
        m[f"{tier}_breaches"] = int(subset.breach.sum())
        m[f"{tier}_breach_rate"] = float(subset.breach.mean()) if len(subset) else np.nan
        m[f"{tier}_drop_rate"] = float(dropped.loc[subset.index].mean()) if len(subset) else np.nan
    return m


def augment_metrics(config, workload, result, legacy, outcomes, slots, nodes):
    """Keep all legacy fields; add counts, quantiles and explicit unit aliases.

    Average replicas is the exact allocated-replica integral / arrival horizon,
    including cold/retiring replicas. Peak replicas is the maximum allocated
    count observed at slot ends, including the initial warm allocation.
    Utilization averages give equal weight to each node-slot; weighted pool
    utilization is exported separately for heterogeneous capacities.
    """
    m = dict(legacy, **request_metrics(outcomes))
    m.update(migrations=legacy["migrations"], scale_outs=legacy["scale_up_actions"],
             scale_ins=legacy["scale_down_actions"],
             cold_starts=sum(r["kind"] == "cold_start" for r in result["lifecycle"]),
             average_replicas=legacy["replica_seconds"]/(config.slots*config.slot_seconds),
             peak_replicas=max(int(slots.replicas.max()), sum(n is not None for n in workload.initial.values())),
             average_cpu_utilization=float(nodes.cpu_utilization.mean()),
             average_gpu_utilization=float(nodes.gpu_utilization.mean()),
             average_bandwidth_utilization=float(nodes.bandwidth_utilization.mean()))
    for resource, capacities in (("cpu", [n.cpu_capacity for n in workload.scenario.nodes]),
                                  ("gpu", workload.gpu_units)):
        weighted = nodes[f"{resource}_utilization"] * nodes.node.map(dict(enumerate(capacities)))
        m[f"pool_{resource}_utilization"] = float(weighted.sum()/(sum(capacities)*config.slots))
    horizon = config.slots*config.slot_seconds
    m["completed_after_horizon"] = int((outcomes.completion_s > horizon).sum())
    assert np.isclose(m["average_latency_ms"], m["mean_request_latency_ms"])
    assert np.isclose(m["time_average_slot_latency_ms"], m["mean_slot_latency_ms"])
    assert np.isclose(m["sla_breach_pct"], 100*m["sla_breach_rate"])
    return m


def validate_pairing(raw, seeds, policies=POLICIES):
    """Reject duplicate, missing or mismatched seed-policy observations."""
    required = {(s, p) for s in seeds for p in policies}
    if raw.duplicated(["seed", "policy"]).any() or set(zip(raw.seed, raw.policy)) != required:
        raise ValueError("incorrect seed-policy pairing")
    for seed, group in raw.groupby("seed"):
        for col in ("traffic_hash", "workload_hash", "total_requests"):
            if group[col].nunique(dropna=False) != 1:
                raise ValueError(f"mismatched {col} for seed {seed}")
