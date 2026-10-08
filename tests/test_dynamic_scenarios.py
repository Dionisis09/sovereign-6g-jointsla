"""New mechanism checks preserve the original 61 tests and baseline behavior."""
from dataclasses import replace
import numpy as np
import pytest
from catalyst.reused import digest
from dynamic_placement.config import Config
from dynamic_placement.workload import generate_workload, Request
from dynamic_placement.simulator import Simulator
from dynamic_placement.policies import POLICIES
from dynamic_placement.predictive import ScenarioConfig, PredictivePrewarming
from dynamic_placement.scenario_model import (ScenarioSimulator, extend_capacity, traffic_hash_payload,
                                             scenario_metrics, validate_scenario_run)


def test_expanded_capacity_preserves_paired_traffic_and_prefix_topology():
    original = generate_workload(Config(slots=10), 2)
    six, seven = extend_capacity(original, 1), extend_capacity(original, 2)
    assert digest(traffic_hash_payload(original)) == digest(traffic_hash_payload(six)) == digest(traffic_hash_payload(seven))
    assert original.requests is six.requests is seven.requests
    assert six.scenario.nodes == seven.scenario.nodes[:6]
    assert np.array_equal(original.scenario.network_latency_ms, six.scenario.network_latency_ms[:5, :5])
    assert np.array_equal(six.scenario.network_latency_ms, seven.scenario.network_latency_ms[:6, :6])
    assert all(s.ingress < 5 for s in seven.services)


def test_scenario_adapter_exactly_preserves_baseline_and_registry():
    config = Config(slots=12)
    workload = generate_workload(config, 4)
    policies = dict(POLICIES)
    reference = Simulator(config, workload, "sla_aware").run()
    adapted = ScenarioSimulator(config, workload, ScenarioConfig()).run()
    clean = [{k: v for k, v in row.items() if k not in ("dropped", "drop_reason")} for row in adapted["outcomes"]]
    assert digest(reference["outcomes"]) == digest(clean)
    assert reference["actions"] == adapted["actions"]
    assert policies == POLICIES


def test_admission_drops_only_bronze_and_counts_offered_failure():
    config = Config(slots=5)
    workload = generate_workload(config, 3)
    requests = []
    for sid in (0, 1, 2):
        for _ in range(40):
            requests.append(Request(len(requests), sid, .01, 0, 1., workload.services[sid].payload_mbit))
    traffic = tuple(dict(service_id=s.service_id, slot=slot, burst=False, expected_rate_rps=s.base_rate_rps,
                         arrivals=40 if s.service_id < 3 and slot == 0 else 0)
                    for s in workload.services for slot in range(config.slots))
    workload = replace(workload, requests=tuple(requests), traffic=traffic)
    settings = ScenarioConfig()
    result = ScenarioSimulator(config, workload, settings, admission=True).run()
    checks = validate_scenario_run(config, workload, settings, result, True)
    metrics, _, _, frame = scenario_metrics(config, workload, result)
    dropped = frame.loc[frame.dropped]
    assert len(dropped) > 0 and dropped.tier.eq("Bronze").all()
    assert metrics["gold_drop_pct"] == metrics["silver_drop_pct"] == 0
    assert metrics["sla_breach_pct"] >= metrics["admitted_sla_breach_pct"]
    assert checks["offered_requests_validated"] == 120
    assert metrics["completed_requests"]+metrics["dropped_requests"] == 120


def test_admission_budget_changes_with_ready_replica_count_and_deadline():
    c, settings = Config(), ScenarioConfig()
    engine = ScenarioSimulator(c, generate_workload(c, 1), settings, admission=True)
    _, first_budget, first_count = engine.admission_state(2)
    node = next(n for n in range(5) if np.all(engine.reserved[n]+engine.services[2].reservation <= engine.capacities[n]))
    engine.add_replica(2, node, warm=True)
    _, second_budget, second_count = engine.admission_state(2)
    assert second_count == first_count+1
    assert second_budget == first_budget*2


def test_seed_15_event_timestamp_roundoff_is_accepted():
    config, settings = Config(slots=2), ScenarioConfig()
    workload = generate_workload(config, 15)
    result = ScenarioSimulator(config, workload, settings).run()
    # Representational roundoff is tolerated; meaningful timestamp corruption is not.
    result["admission"][0]["time_s"] += 1e-16
    validate_scenario_run(config, workload, settings, result, False)
    result["admission"][0]["time_s"] += .001
    with pytest.raises(AssertionError):
        validate_scenario_run(config, workload, settings, result, False)


def test_predictor_has_no_initial_oracle_and_prewarming_precedes_prediction():
    config, settings = Config(), ScenarioConfig()
    engine = ScenarioSimulator(config, generate_workload(config, 0), settings)
    predictor = PredictivePrewarming(settings)
    rates = np.array([s.base_rate_rps for s in engine.services])
    tape = np.tile(rates*config.slot_seconds, (100, 1))
    tape[20:30] *= 3
    for slot in range(51):
        snap = engine.snapshot()
        snap["slot"] = slot
        snap["arrival_history"] = tape[:slot].copy()
        predictor(config, snap)
    assert predictor.forecasts[0]["predicted_burst_slot"] is None
    assert all(row["predicted_burst_slot"] is None for row in predictor.forecasts[:20])
    assert predictor.prewarm_proposals
    assert all(1 <= row["predicted_burst_slot"]-row["slot"] <= 2 for row in predictor.prewarm_proposals)
    other_tape = tape.copy()
    other_tape[60:] *= 100
    a, b = PredictivePrewarming(settings), PredictivePrewarming(settings)
    for slot in range(51):
        snap = engine.snapshot()
        snap["slot"] = slot
        snap["arrival_history"] = tape[:slot].copy()
        original = a(config, snap)
        snap["arrival_history"] = other_tape[:slot].copy()
        assert b(config, snap) == original
    assert a.forecasts == b.forecasts


@pytest.mark.parametrize("settings", [dict(moving_average_slots=1), dict(prewarm_lead_slots=3),
                                      dict(burst_detection_ratio=1), dict(admission_threshold=1)])
def test_invalid_scenario_settings(settings):
    with pytest.raises(ValueError):
        ScenarioConfig(**settings)
