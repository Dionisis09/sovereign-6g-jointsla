"""Scenario adapters keep the existing simulator and SLA-aware function intact."""
from dataclasses import replace
import math
import numpy as np
from placement_experiment.data_generation import EdgeServer, Scenario, Config as StaticConfig
from placement_experiment.algorithms import greedy_placement
from .simulator import Simulator
from .policies import POLICIES, sla_aware
from .metrics import calculate_metrics, validate_run


def extend_capacity(workload, additional_nodes):
    """Append nodes without perturbing services, request tape or original topology.

    Fresh seeded streams are independent of the original generator. Six-node
    topology is a prefix of seven-node topology; ingress remains at original nodes.
    Initial greedy placement is recomputed over the expanded capacity pool.
    """
    nodes = list(workload.scenario.nodes)
    original_count = len(nodes)
    total = original_count + additional_nodes
    network = np.zeros((total, total))
    network[:original_count, :original_count] = workload.scenario.network_latency_ms
    for node_id in range(original_count, total):
        rng = np.random.default_rng(np.random.SeedSequence([workload.seed, 6201, node_id]))
        nodes.append(EdgeServer(node_id, float(rng.uniform(9, 12)), float(rng.uniform(20, 30)),
                                float(rng.uniform(280, 420))))
        for peer in range(node_id):
            link_rng = np.random.default_rng(np.random.SeedSequence([workload.seed, 6202, node_id, peer]))
            network[node_id, peer] = network[peer, node_id] = link_rng.uniform(4, 25)
    network.setflags(write=False)
    scenario = Scenario(workload.seed, tuple(nodes), workload.scenario.applications, network)
    initial = greedy_placement(StaticConfig(node_count=total, application_count=len(workload.services)), scenario, workload.seed)
    units = tuple(2 if n.gpu_capacity < 25 else 3 for n in nodes)
    return replace(workload, scenario=scenario, initial=initial, gpu_units=units)


def traffic_hash_payload(workload):
    """Topology-independent identity used to enforce paired demand across cases."""
    value = workload.to_dict()
    return {key: value[key] for key in ("seed", "services", "requests", "traffic")}


class ScenarioSimulator(Simulator):
    """Instrument offered/admitted arrivals; optionally reject new Bronze requests."""
    def __init__(self, config, workload, settings, controller=None, admission=False):
        self.settings = settings
        self.controller = controller or sla_aware
        self.admission = admission
        self.arrival_history = np.zeros((config.slots, len(workload.services)))
        self.admission_events = []
        super().__init__(config, workload, "__scenario_controller__")

    def snapshot(self):
        result = super().snapshot()
        # Previous complete slots only; future rows remain private to the engine.
        result["arrival_history"] = self.arrival_history[:self.slot].copy()
        return result

    def admission_state(self, sid):
        service = self.services[sid]
        ready = sum(r.service_id == sid and r.ready and not r.retiring and r.pending_target is None
                    for r in self.replicas.values())
        compute_ms = self.config.preprocess_ms + self.config.inference_ms + self.config.postprocess_ms
        budget = max(1, ready) * max(1, math.ceil(service.deadline_ms / compute_ms))
        return len(self.queues[sid].items), budget, ready

    def source(self):
        for request in self.workload.requests:
            yield self.env.timeout(max(0., request.arrival_s - self.env.now))
            sid = request.service_id
            self.observed_arrivals[sid] += 1
            self.arrival_history[request.arrival_slot, sid] += 1
            service = self.services[sid]
            depth, budget, ready = self.admission_state(sid)
            drop = (self.admission and service.tier == "Bronze"
                    and depth / budget > self.settings.admission_threshold)
            self.admission_events.append(dict(request_id=request.request_id, time_s=self.env.now,
                                               service_id=sid, tier=service.tier, queue_depth=depth,
                                               queue_budget=budget, ready_replicas=ready, dropped=bool(drop)))
            unplaced = self.workload.initial[sid] is None
            if drop or unplaced:
                self.outcomes.append(dict(request_id=request.request_id, service_id=sid, tier=service.tier,
                                          arrival_slot=request.arrival_slot, arrival_s=request.arrival_s,
                                          completion_s=None, node=None, replica_id=None, deadline_ms=service.deadline_ms,
                                          latency_ms=None, service_queue_ms=None, node_queue_ms=None,
                                          compute_ms=None, network_ms=None, lifecycle_penalty_ms=None,
                                          breach=True, unplaced=unplaced, dropped=bool(drop),
                                          drop_reason="bronze_queue_threshold" if drop else ""))
                self._finish_if_done()
            else:
                yield self.queues[sid].put(request)

    def run(self):
        key = self.policy
        if key in POLICIES:
            raise RuntimeError("scenario controller already active")
        POLICIES[key] = self.controller
        try:
            result = super().run()
        finally:
            del POLICIES[key]
        for row in result["outcomes"]:
            row.setdefault("dropped", False)
            row.setdefault("drop_reason", "")
        result["admission"] = self.admission_events
        return result


def validate_scenario_run(config, workload, settings, result, admission):
    """Use the original independent component/ledger checks on admitted requests."""
    rows = sorted(result["outcomes"], key=lambda r: r["request_id"])
    assert [r["request_id"] for r in rows] == list(range(len(workload.requests)))
    admitted_requests, admitted_rows = [], []
    for request, row, event in zip(workload.requests, rows, result["admission"]):
        assert event["request_id"] == request.request_id and abs(event["time_s"] - request.arrival_s) < 1e-12
        assert row["arrival_s"] == request.arrival_s and row["service_id"] == request.service_id
        assert event["service_id"] == request.service_id
        service = workload.services[request.service_id]
        budget = max(1, event["ready_replicas"]) * max(1, math.ceil(service.deadline_ms /
                         (config.preprocess_ms + config.inference_ms + config.postprocess_ms)))
        assert event["queue_budget"] == budget
        expected = admission and service.tier == "Bronze" and event["queue_depth"] / budget > settings.admission_threshold
        assert row["dropped"] == event["dropped"] == expected
        if row["dropped"]:
            assert row["breach"] and row["latency_ms"] is None and row["completion_s"] is None
            assert row["drop_reason"] == "bronze_queue_threshold"
            continue
        new_id = len(admitted_requests)
        admitted_requests.append(replace(request, request_id=new_id))
        admitted_rows.append({**row, "request_id": new_id})
    check = validate_run(config, replace(workload, requests=tuple(admitted_requests)), {**result, "outcomes": admitted_rows})
    return {**check, "offered_requests_validated": len(rows), "drops_validated": len(rows)-len(admitted_rows)}


def scenario_metrics(config, workload, result, controller=None):
    """Offer-based failures include drops; conditional admitted breaches are separate."""
    import pandas as pd
    metrics, slots, nodes, outcomes = calculate_metrics(config, workload, result)
    completed = outcomes.loc[~outcomes.dropped & ~outcomes.unplaced]
    metrics.update(dropped_requests=int(outcomes.dropped.sum()), drop_pct=float(outcomes.dropped.mean()*100),
                   admitted_sla_breach_pct=float(completed.breach.mean()*100))
    for tier in ("Gold", "Silver", "Bronze"):
        offered = outcomes.loc[outcomes.tier == tier]
        admitted = offered.loc[~offered.dropped & ~offered.unplaced]
        metrics[f"{tier.lower()}_drop_pct"] = float(offered.dropped.mean()*100)
        metrics[f"{tier.lower()}_admitted_sla_breach_pct"] = float(admitted.breach.mean()*100)
    protected = outcomes.loc[outcomes.tier.isin(["Gold", "Silver"])]
    metrics["gold_silver_sla_breach_pct"] = float(protected.breach.mean()*100)
    cohort = outcomes.groupby("arrival_slot").agg(dropped_requests=("dropped", "sum"),
                                                  admitted_requests=("latency_ms", "count"))
    admitted_breaches = completed.groupby("arrival_slot").breach.sum()
    slots["dropped_requests"] = slots.slot.map(cohort.dropped_requests).fillna(0).astype(int)
    slots["admitted_requests"] = slots.slot.map(cohort.admitted_requests).fillna(0).astype(int)
    slots["admitted_breaches"] = slots.slot.map(admitted_breaches).fillna(0).astype(int)
    slots["drop_pct"] = 100 * slots.dropped_requests / slots.requests.replace(0, np.nan)
    slots["cumulative_drop_pct"] = 100 * slots.dropped_requests.cumsum() / slots.requests.cumsum().replace(0, np.nan)
    slots["cumulative_admitted_sla_breach_pct"] = 100 * slots.admitted_breaches.cumsum() / slots.admitted_requests.cumsum().replace(0, np.nan)
    cold = [r for r in result["lifecycle"] if r["kind"] == "cold_start"]
    metrics["cold_start_count"] = len(cold)
    metrics["cold_start_penalty_total_ms"] = float(outcomes.loc[outcomes.lifecycle_penalty_ms == config.cold_penalty_ms, "lifecycle_penalty_ms"].sum())
    action_services = {r["replica_id"]: r["service_id"] for r in result["actions"] if r["kind"] == "scale_up"}
    burst = {(r["service_id"], r["slot"]): r["burst"] for r in workload.traffic}
    overlap = 0
    for event in cold:
        sid = action_services[event["replica_id"]]
        first = int(math.floor(event["start_s"] / config.slot_seconds + 1e-8))
        last = int(math.ceil(event["ready_s"] / config.slot_seconds - 1e-8))
        overlap += any(burst.get((sid, slot), False) for slot in range(first, last))
    metrics["cold_starts_overlapping_bursts"] = overlap
    proposals = controller.prewarm_proposals if controller is not None else []
    accepted = {(a["slot"], a["service_id"], a["target_node"]) for a in result["actions"] if a["kind"] == "scale_up"}
    metrics["prewarm_actions"] = sum((r["slot"], r["service_id"], r["target"]) in accepted for r in proposals)
    return metrics, slots, nodes, outcomes
