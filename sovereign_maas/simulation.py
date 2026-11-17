"""Deterministic queue toy model; all observations and outcomes are simulated."""

from datetime import UTC, datetime
from random import Random

from .domain import ActionKind, CandidateAction, ServiceBundle, TelemetrySnapshot, TopologyNode, Verification


def make_snapshot(seed: int) -> TelemetrySnapshot:
    rng = Random(seed)
    queue = rng.randint(3, 5)
    rate = float(rng.randint(52, 54))
    nodes = (
        TopologyNode(id="edge-a", region="eu-gr", network_ms=10, replica_capacity=4),
        TopologyNode(id="cloud-a", region="eu-de", network_ms=80, replica_capacity=2),
    )
    return TelemetrySnapshot(
        seed=seed,
        observed_at=datetime.now(UTC),
        queue_depth=queue,
        arrival_rps=rate,
        cycle_ms=20,
        observed_p95_ms=latency(queue, 1, nodes[0].network_ms, 20),
        nodes=nodes,
    )


def latency(queue: float, replicas: int, network_ms: float, cycle_ms: float) -> float:
    return round(network_ms + cycle_ms * (1 + queue / replicas), 3)


def projected_queue(snapshot: TelemetrySnapshot, seconds: float, replicas: int) -> float:
    capacity_rps = replicas * 1000 / snapshot.cycle_ms
    return max(0.0, snapshot.queue_depth + (snapshot.arrival_rps - capacity_rps) * seconds)


def final_queue(snapshot: TelemetrySnapshot, kind: ActionKind, target_replicas: int) -> float:
    if kind == ActionKind.NOOP:
        return projected_queue(snapshot, 5.0, snapshot.replicas)
    ttr_s = 1.0 if kind == ActionKind.SCALE_OUT else 2.0
    before_ready = projected_queue(snapshot, ttr_s, snapshot.replicas)
    capacity_after_rps = target_replicas * 1000 / snapshot.cycle_ms
    return max(0.0, before_ready + snapshot.arrival_rps - capacity_after_rps)


def ttv_low_rule(bundle: ServiceBundle, snapshot: TelemetrySnapshot) -> float:
    """Conservative linear rule; not an empirical quantile or calibrated estimate."""
    if snapshot.observed_p95_ms >= bundle.intent.latency_p95_ms:
        return 0.0
    growth_ms_s = snapshot.cycle_ms * max(0.0, snapshot.arrival_rps - 1000 / snapshot.cycle_ms)
    if growth_ms_s == 0:
        return 1_000_000_000.0  # finite sentinel for no rule-predicted breach
    return round(max(0.0, (bundle.intent.latency_p95_ms - snapshot.observed_p95_ms) / growth_ms_s - 0.5), 3)


def candidate_post_latency(snapshot: TelemetrySnapshot, kind: ActionKind, target_replicas: int) -> float:
    node = snapshot.nodes[1] if kind == ActionKind.MIGRATE else snapshot.nodes[0]
    return latency(
        final_queue(snapshot, kind, target_replicas),
        target_replicas,
        node.network_ms,
        snapshot.cycle_ms,
    )


def execute(bundle: ServiceBundle, snapshot: TelemetrySnapshot, action: CandidateAction) -> Verification:
    """Replay the simulated after-state with no external side effects."""
    kind = action.kind
    node = next(n for n in snapshot.nodes if n.id == action.target_node)
    actual = latency(
        final_queue(snapshot, kind, action.target_replicas),
        action.target_replicas,
        node.network_ms,
        snapshot.cycle_ms,
    )
    return Verification(
        measured_p95_ms=actual,
        slo_met=actual <= bundle.intent.latency_p95_ms,
        final_replicas=action.target_replicas,
        final_node=node.id,
    )
