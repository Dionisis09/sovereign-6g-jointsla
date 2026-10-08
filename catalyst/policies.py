"""Controllers receive a public snapshot, never the simulator or workload tape."""
from dataclasses import dataclass, replace
from enum import StrEnum
from .contracts import ServiceState, compile_contract
from .scenario import Config


class Action(StrEnum):
    NOOP = "NOOP"
    SCALE_OUT = "SCALE_OUT"
    REROUTE = "REROUTE"
    START_OR_CONTINUE_ROLLOUT = "START_OR_CONTINUE_ROLLOUT"
    ROLLBACK = "ROLLBACK"


PRIMARY = ("B0", "B1", "CATALYST")
ABLATIONS = ("A1", "A2")


@dataclass(frozen=True)
class TargetView:
    workers: int
    queued: int
    inference_p99_ms: float
    network_p99_ms: float


@dataclass(frozen=True)
class Snapshot:
    time_s: float
    targets: tuple[TargetView, TargetView]
    active: int
    fraction_v2: float
    arrival_rate_rps: float
    capacity_reduction: float
    rollout_enabled: bool
    last_rollout_s: float
    last_reroute_s: float
    overhead_active: bool
    observed_breach: bool
    pressure: bool


def project(config: Config, snapshot: Snapshot, action: Action) -> ServiceState:
    active = 1 - snapshot.active if action == Action.REROUTE else snapshot.active
    target = snapshot.targets[active]
    fraction = snapshot.fraction_v2
    if action == Action.START_OR_CONTINUE_ROLLOUT:
        fraction = min(1., fraction + .25)
    if action == Action.ROLLBACK:
        fraction = 0.
    workers = target.workers + int(action == Action.SCALE_OUT)
    overhead = config.rollout_overhead_ms if (
        action == Action.START_OR_CONTINUE_ROLLOUT or snapshot.overhead_active) else 0.
    demand = ((1 - fraction) * config.v1_service_ms + fraction * config.v2_service_ms)
    demand = demand / (1 - snapshot.capacity_reduction) + overhead
    old_demand = ((1 - snapshot.fraction_v2) * config.v1_service_ms +
                  snapshot.fraction_v2 * config.v2_service_ms) / (1 - snapshot.capacity_reduction)
    projected_inference = max(1.2 * demand,
                              target.inference_p99_ms * demand / old_demand * target.workers / workers,
                              (target.queued / workers + 1.2) * demand)
    quality = config.v1_quality if fraction == 0 else (
        config.v2_quality if fraction == 1 else min(config.v1_quality, config.v2_quality))
    disruption = config.rollout_disruption_s if action == Action.START_OR_CONTINUE_ROLLOUT else 0.
    latency = target.network_p99_ms + config.gateway_ms + projected_inference
    availability = max(0., 1 - disruption / config.metric_window_s)
    if latency > config.request_timeout_ms:
        availability = 0.
    return ServiceState(latency, quality, availability, disruption)


def local_violations(config, snapshot, action):
    state = project(config, snapshot, action)
    active = 1 - snapshot.active if action == Action.REROUTE else snapshot.active
    network = snapshot.targets[active].network_p99_ms
    inference = state.latency_ms - network - config.gateway_ms
    failures = []
    if inference > config.local_inference_limit_ms:
        failures.append("LOCAL_INFERENCE_LATENCY")
    if network > config.local_network_limit_ms:
        failures.append("LOCAL_NETWORK_LATENCY")
    if state.quality < config.intent.minimum_model_quality:
        failures.append("LOCAL_MODEL_QUALITY")
    if state.disruption_s > config.intent.max_update_disruption_s:
        failures.append("LOCAL_UPDATE_DISRUPTION")
    # Availability protection here is local; no network+inference composition.
    if 1 - state.disruption_s / config.metric_window_s < config.intent.service_availability:
        failures.append("LOCAL_AVAILABILITY")
    if action == Action.SCALE_OUT and snapshot.targets[active].workers >= 2:
        failures.append("LOCAL_CAPACITY_LIMIT")
    if action == Action.START_OR_CONTINUE_ROLLOUT:
        fraction = min(1., snapshot.fraction_v2 + .25)
        demand = ((1 - fraction) * config.v1_service_ms + fraction * config.v2_service_ms)
        utilization = snapshot.arrival_rate_rps * demand / (1000 * snapshot.targets[active].workers * (1 - snapshot.capacity_reduction))
        if utilization > config.scale_high_utilization:
            failures.append("LOCAL_ROLLOUT_CAPACITY")
    if snapshot.targets[active].workers < 1:
        failures.append("LOCAL_UNAVAILABLE")
    if action == Action.REROUTE:
        demand = ((1 - snapshot.fraction_v2) * config.v1_service_ms +
                  snapshot.fraction_v2 * config.v2_service_ms) / (1 - snapshot.capacity_reduction)
        if snapshot.arrival_rate_rps * demand / (1000 * snapshot.targets[active].workers) > config.scale_high_utilization:
            failures.append("LOCAL_DESTINATION_CAPACITY")
    return tuple(failures)


def candidates(config, snapshot, reactive=False):
    target = snapshot.targets[snapshot.active]
    demand = ((1 - snapshot.fraction_v2) * config.v1_service_ms +
              snapshot.fraction_v2 * config.v2_service_ms) / (1 - snapshot.capacity_reduction)
    utilization = snapshot.arrival_rate_rps * demand / (1000 * target.workers)
    pressure = snapshot.pressure
    if utilization > config.scale_high_utilization or target.inference_p99_ms > config.local_inference_limit_ms:
        pressure = True
    elif utilization < config.scale_low_utilization and target.inference_p99_ms < .8 * config.local_inference_limit_ms:
        pressure = False
    options = []
    if pressure and target.workers < 2:
        options.append(Action.SCALE_OUT)
    if pressure and target.workers == 2 and snapshot.time_s - snapshot.last_reroute_s >= config.rollout_stage_hold_s:
        options.append(Action.REROUTE)
    if reactive and snapshot.fraction_v2 > 0:
        options.append(Action.ROLLBACK)
    if (snapshot.rollout_enabled and snapshot.fraction_v2 < 1 and
        snapshot.time_s >= config.rollout_start_s and
        snapshot.time_s - snapshot.last_rollout_s >= config.rollout_stage_hold_s):
        options.append(Action.START_OR_CONTINUE_ROLLOUT)
        if target.workers < 2:
            options.append(Action.SCALE_OUT)
        if snapshot.fraction_v2 > 0:
            options.append(Action.ROLLBACK)
    options.append(Action.NOOP)
    return tuple(dict.fromkeys(options)), pressure


def decide(config: Config, snapshot: Snapshot, policy: str, reactive=False,
           force_action: Action | None = None):
    if policy not in PRIMARY + ABLATIONS:
        raise ValueError(f"unknown policy {policy}")
    options, pressure = candidates(config, snapshot, reactive)
    rejected = []
    contract = compile_contract(config.intent)
    if force_action is not None:
        return force_action, pressure, [], project(config, snapshot, force_action)
    for action in options:
        prediction = project(config, snapshot, action)
        if action == Action.NOOP:
            return action, pressure, rejected, prediction
        local = local_violations(config, snapshot, action) if policy != "B0" else ()
        cross = contract.violations(prediction) if policy == "CATALYST" and not local else ()
        if local or cross:
            rejected.append(dict(action=action.value, source="local" if local else "contract",
                                 reasons=list(local or cross), prediction=prediction))
        else:
            return action, pressure, rejected, prediction
    raise AssertionError("NOOP must always remain available")

