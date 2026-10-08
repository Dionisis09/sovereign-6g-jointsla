"""Mechanism tests: queuing, finite resources, migration/cold starts and pairing."""
from dataclasses import replace
import numpy as np
import pytest
import simpy
from dynamic_placement.config import Config
from dynamic_placement.workload import Workload, Request, generate_workload
from dynamic_placement.simulator import BusyIntegral, Simulator
from dynamic_placement.metrics import calculate_metrics, validate_run
from dynamic_placement.policies import Action, POLICIES, periodic_replacement, reactive_scaling, risk_score
from catalyst.reused import digest


@pytest.fixture
def tiny():
    config = Config(slots=8)
    original = generate_workload(config, 3)
    service = original.services[0]
    initial = {s.service_id: None for s in original.services}
    initial[0] = 0
    requests = tuple(Request(i, 0, .01, 0, 1., service.payload_mbit) for i in range(12))
    traffic = tuple(dict(service_id=s.service_id, slot=slot, burst=False, expected_rate_rps=s.base_rate_rps,
                         arrivals=12 if s.service_id == 0 and slot == 0 else 0)
                    for s in original.services for slot in range(config.slots))
    return config, replace(original, initial=initial, requests=requests, traffic=traffic)


def test_input_replay_and_compound_clusters():
    config = Config()
    a, b = generate_workload(config, 0), generate_workload(config, 0)
    assert digest(a.to_dict()) == digest(b.to_dict())
    assert digest(a.to_dict()) != digest(generate_workload(config, 1).to_dict())
    assert any(a.requests[i].arrival_s == a.requests[i+1].arrival_s for i in range(len(a.requests)-1))
    burst = [r for r in a.traffic if r["service_id"] == 0 and r["burst"]]
    starts = [r["slot"] for i, r in enumerate(burst) if i == 0 or r["slot"] > burst[i-1]["slot"]+1]
    assert len(starts) == 3 and np.diff(starts).tolist() == [30, 30]


def test_queue_growth_component_sum_and_drain(tiny):
    c, w = tiny
    c = replace(c, slots=1)
    w = replace(w, traffic=tuple(row for row in w.traffic if row["slot"] == 0))
    result = Simulator(c, w, "static").run()
    checks = validate_run(c, w, result)
    assert checks["requests_validated"] == 12
    assert result["diagnostics"]["drain_seconds"] > 0
    assert max(row["service_queue_ms"] for row in result["outcomes"]) > 100
    metrics, slots, _, _ = calculate_metrics(c, w, result)
    assert metrics["requests"] == 12 and slots.requests.sum() == 12
    assert metrics["time_average_slot_latency_ms"] == pytest.approx(slots.latency_ms.mean())
    assert metrics["sla_breach_pct"] == pytest.approx(100 * sum(r["breach"] for r in result["outcomes"]) / 12)


def test_busy_integral_across_boundaries():
    env = simpy.Environment()
    integral = BusyIntegral(env)
    integral.change(2)
    env.run(until=.3)
    assert integral.value() == pytest.approx(.6)
    integral.change(-1)
    env.run(until=.5)
    assert integral.value() == pytest.approx(.8)


def test_common_inputs_and_deterministic_results(tiny):
    c, w = tiny
    c = replace(c, action_budget=1)
    first = Simulator(c, w, "sla_aware").run()
    second = Simulator(c, w, "sla_aware").run()
    assert digest(first["outcomes"]) == digest(second["outcomes"])
    assert first["actions"] == second["actions"]
    for policy in POLICIES:
        result = Simulator(c, w, policy).run()
        validate_run(c, w, result)
        assert {r["request_id"] for r in result["outcomes"]} == set(range(12))


def test_cold_start_delays_new_replica(tiny):
    c, w = tiny
    engine = Simulator(c, w, "static")
    assert engine.apply(Action("scale_up", 0, 1))
    replica = engine.replicas[20] if 20 in engine.replicas else engine.replicas[1]
    assert not replica.ready
    engine.env.run(until=.099)
    assert not replica.ready
    engine.env.run(until=.101)
    assert replica.ready
    assert engine.lifecycle_events[0]["ready_s"] == pytest.approx(.1)


def test_migration_preserves_requests_and_applies_downtime_and_penalty(tiny, monkeypatch):
    c, w = tiny
    def migrate_once(config, snapshot):
        if snapshot["slot"] == 1:
            return [Action("migrate", 0, 1, 0)]
        return []
    monkeypatch.setitem(POLICIES, "forced_migration", migrate_once)
    engine = Simulator(c, w, "forced_migration")
    result = engine.run()
    validate_run(c, w, result)
    assert len(result["outcomes"]) == 12
    assert len(result["actions"]) == 1
    lifecycle = result["lifecycle"][0]
    assert lifecycle["kind"] == "migration_downtime"
    assert lifecycle["ready_s"] - lifecycle["start_s"] == pytest.approx(.1)
    migrated = [r for r in result["outcomes"] if r["node"] == 1]
    assert migrated and migrated[0]["lifecycle_penalty_ms"] == 10
    assert any(r["node"] == 0 for r in result["outcomes"])
    # Migration holds both reservations until the in-flight source request finishes.
    reserve = [r for r in result["reservations"] if r["node"] == 1 and r["sign"] == 1][0]
    release = [r for r in result["reservations"] if r["node"] == 0 and r["sign"] == -1][0]
    assert reserve["time_s"] <= release["time_s"]


def test_engine_rejects_infeasible_and_last_replica_removal(tiny):
    c, w = tiny
    engine = Simulator(c, w, "static")
    assert not engine.apply(Action("scale_down", 0, replica_id=0))
    engine.reserved[1] = engine.capacities[1]
    assert not engine.apply(Action("scale_up", 0, 1))
    assert not engine.apply(Action("migrate", 0, 1, 0))
    assert engine.replicas[0].node == 0


def test_local_threshold_and_periodic_target_selection(tiny):
    c, w = tiny
    engine = Simulator(c, w, "static")
    snap = engine.snapshot()
    snap["slot"] = 10
    snap["utilization"][0] = [.1, .9]
    reactive = reactive_scaling(c, snap)
    assert reactive[0].kind == "scale_up" and reactive[0].target == 0
    periodic = periodic_replacement(c, snap)
    assert periodic[0].kind == "migrate" and periodic[0].target != 0
    snap["slot"] = 11
    assert not periodic_replacement(c, snap)
    snap["utilization"][0] = [.1, .79]
    assert not reactive_scaling(c, snap)


def test_svrs_responds_to_queue_age_and_tier(tiny):
    c, w = tiny
    snap = Simulator(c, w, "static").snapshot()
    service = w.services[0]
    initial = risk_score(c, snap, service)
    snap["queue_lengths"][0] = 3
    snap["oldest_wait_ms"][0] = 100
    assert risk_score(c, snap, service) > initial
    assert risk_score(c, snap, replace(service, priority=3)) == 3 * risk_score(c, snap, replace(service, priority=1))
    assert not {"requests", "traffic", "burst", "future_arrivals"}.intersection(snap)


@pytest.mark.parametrize("kwargs", [dict(trials=29), dict(slot_seconds=0), dict(batch_mean=.5),
                                  dict(low_threshold=.9), dict(noise_sigma=float("nan")), dict(slots=1.5)])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)
