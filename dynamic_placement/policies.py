"""Deterministic controllers consuming past-only telemetry snapshots.

The engine, rather than the policy, enforces every capacity and lifecycle rule.
To add an optimizer/RL agent, register a function (config, snapshot) -> list[Action].
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Action:
    kind: str
    service_id: int
    target: int | None = None
    replica_id: int | None = None
    risk: float = 0.


def static_allocation(config, snapshot):
    """Fixed common initial mean-load placement; no scaling or migration."""
    return []


def _eligible(config, snap, service):
    return snap["slot"] - snap["last_action"][service] >= config.cooldown_slots


def _fits(snap, service, target):
    return bool(np.all(snap["reserved"][target] + service.reservation <= snap["capacities"][target] + 1e-9))


def _removal(config, snap, service):
    replicas = snap["replicas"][service.service_id]
    if len(replicas) <= 1 or snap["queue_lengths"][service.service_id] or not _eligible(config, snap, service.service_id):
        return None
    candidates = [r for r in replicas if r["ready"] and not r["busy"]
                  and max(snap["utilization"][r["node"]]) < config.low_threshold]
    if candidates:
        r = max(candidates, key=lambda r: r["id"])
        return Action("scale_down", service.service_id, replica_id=r["id"])
    return None


def reactive_scaling(config, snap):
    """Previous-slot >80% CPU/GPU triggers local scale-out; both <20% scale-in."""
    actions = []
    for service in snap["services"]:
        sid, replicas = service.service_id, snap["replicas"][service.service_id]
        if not _eligible(config, snap, sid):
            continue
        nodes = sorted({r["node"] for r in replicas if r["ready"]},
                       key=lambda n: (-max(snap["utilization"][n]), n))
        if len(replicas) < config.max_replicas:
            target = next((n for n in nodes if max(snap["utilization"][n]) > config.high_threshold
                           and _fits(snap, service, n)), None)
            if target is not None:
                actions.append(Action("scale_up", sid, target))
                continue
        remove = _removal(config, snap, service)
        if remove:
            actions.append(remove)
    return actions[:config.action_budget]


def periodic_replacement(config, snap):
    """At fixed intervals move replicas from >80% to <50% busy hosts."""
    if snap["slot"] == 0 or snap["slot"] % config.rebalance_period:
        return []
    candidates = []
    for service in snap["services"]:
        if not _eligible(config, snap, service.service_id):
            continue
        for r in snap["replicas"][service.service_id]:
            source = max(snap["utilization"][r["node"]])
            if not r["ready"] or source <= config.high_threshold:
                continue
            targets = [n for n in range(len(snap["capacities"])) if n != r["node"]
                       and max(snap["utilization"][n]) < .5 and _fits(snap, service, n)]
            if targets:
                target = min(targets, key=lambda n: (max(snap["utilization"][n]), n))
                candidates.append((-source, service.service_id, r["id"], target))
    candidates.sort()
    used, actions = set(), []
    for _, sid, rid, target in candidates:
        if sid not in used:
            actions.append(Action("migrate", sid, target, rid))
            used.add(sid)
    return actions[:config.action_budget]


def risk_score(config, snap, service):
    """SVRS = tier weight * (predicted delay/deadline + queued work/deadline).

    Predicted delay uses recent completions or the known empty-system path;
    oldest waiting age protects queues with no recent completion feedback.
    No future arrival rates or scheduled bursts are exposed to this function.
    """
    sid = service.service_id
    count = max(1, sum(r["ready"] for r in snap["replicas"][sid]))
    compute_ms = config.preprocess_ms + config.inference_ms + config.postprocess_ms
    predicted = max(snap["latency_ms"][sid], snap["oldest_wait_ms"][sid] + compute_ms)
    queue_work = snap["queue_lengths"][sid] * compute_ms / count
    return service.priority * (predicted + queue_work) / service.deadline_ms


def sla_aware(config, snap):
    """Prioritize observed SLA risk, then score feasible scale/migration actions.

    Joint score: predicted delay/deadline + .35 CPU/GPU pressure + .25 lifecycle
    overhead/deadline. Delay projects EWMA arrival work and service backlog.
    For a migration, the score includes full downtime, whereas scale-out adds
    a replica while the existing replicas keep serving during its cold start.
    A migration must improve the source score; scale-out requires risk pressure.
    """
    ranked = sorted(snap["services"], key=lambda s: (-risk_score(config, snap, s),
                                                     -s.priority, -snap["rates"][s.service_id], s.service_id))
    actions = []
    compute_s = (config.preprocess_ms + config.inference_ms + config.postprocess_ms) / 1000
    for service in ranked:
        sid, replicas = service.service_id, snap["replicas"][service.service_id]
        if not _eligible(config, snap, sid) or not replicas:
            continue
        risk = risk_score(config, snap, service)
        active = max(1, sum(r["ready"] for r in replicas))
        demand = snap["rates"][sid] * compute_s / active
        if risk / service.priority < config.risk_threshold and demand < config.high_threshold:
            remove = _removal(config, snap, service)
            if remove:
                actions.append(remove)
            continue
        choices = []
        for target in range(len(snap["capacities"])):
            if not _fits(snap, service, target):
                continue
            pressure = float(max(snap["utilization"][target]))
            reserved = (snap["reserved"][target] + service.reservation) / snap["capacities"][target]
            for kind in ("scale_up", "migrate"):
                if kind == "scale_up" and len(replicas) >= config.max_replicas:
                    continue
                r = max((r for r in replicas if r["ready"] and r["node"] != target),
                        key=lambda r: (max(snap["utilization"][r["node"]]), -r["id"]), default=None)
                if kind == "migrate" and r is None:
                    continue
                count = active + (kind == "scale_up")
                overhead_ms = ((config.cold_start_slots if kind == "scale_up" else config.migration_down_slots)
                               * config.slot_seconds * 1000
                               + (config.cold_penalty_ms if kind == "scale_up" else config.migration_penalty_ms))
                net = snap["network_ms"][service.ingress, target] + service.payload_mbit / snap["capacities"][target, 2] * 1000
                backlog_ms = snap["queue_lengths"][sid] * compute_s * 1000 / count
                rho = min(.98, max(pressure, snap["rates"][sid] * compute_s / count))
                delay_ms = net + compute_s * 1000 / (1 - rho) + backlog_ms
                score = (delay_ms / service.deadline_ms + config.headroom_weight * (pressure + float(reserved[:2].mean())) / 2
                         + config.overhead_weight * overhead_ms / service.deadline_ms)
                if kind == "migrate":
                    source_pressure = max(snap["utilization"][r["node"]])
                    source_rho = min(.98, max(source_pressure, demand))
                    source_score = ((snap["network_ms"][service.ingress, r["node"]]
                                     + compute_s * 1000 / (1 - source_rho) + backlog_ms) / service.deadline_ms
                                    + config.headroom_weight * source_pressure)
                    if score >= source_score or source_pressure <= config.high_threshold:
                        continue
                choices.append((score, kind != "scale_up", target, kind, r["id"] if r else None))
        if choices:
            _, _, target, kind, rid = min(choices)
            actions.append(Action(kind, sid, target, rid if kind == "migrate" else None, risk))
    return actions[:config.action_budget]


POLICIES = dict(static=static_allocation, reactive=reactive_scaling,
                periodic=periodic_replacement, sla_aware=sla_aware)
