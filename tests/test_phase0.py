from dataclasses import replace
from pathlib import Path
import gzip
import json
import inspect
import numpy as np
import pytest
from pydantic import ValidationError
from catalyst.contracts import Intent, ServiceState, compile_contract
from catalyst.scenario import load_config, matrix, workload, Scenario, Event
from catalyst.engine import Engine
from catalyst.policies import Action, Snapshot, TargetView, decide, local_violations, project
from catalyst.reused import digest, quantile, write_json, write_gzip


@pytest.fixture
def config():
    return load_config()


def snap(inference=35., network=38., fraction=0., workers=1, time=10.):
    return Snapshot(time, (TargetView(workers, 0, inference, network),
                           TargetView(1, 0, 14.4, network + 4)),
                    0, fraction, 30., 0., True, time - 3, time - 3, False, False, False)


def test_contract_boundaries_and_union(config):
    contract = compile_contract(config.intent)
    assert not contract.violations(ServiceState(80., .85, .99, .1))
    assert len(contract.violations(ServiceState(81., .84, .98, .11))) == 4
    tape = workload(config, next(matrix(config)), 0)
    engine = Engine(config, next(matrix(config)), tape, "B1")
    engine.samples = [dict(violations=list(contract.violations(ServiceState(81., .84, .98, .11))))]
    assert engine.summary()["total_service_contract_breach_seconds"] == config.tick_s


@pytest.mark.parametrize("field,value", [("end_to_end_latency_ms", -1), ("minimum_model_quality", 1.1),
                                          ("service_availability", 0), ("max_update_disruption_s", float("nan"))])
def test_intent_rejects_invalid(config, field, value):
    with pytest.raises(ValidationError):
        Intent.model_validate({**config.intent.model_dump(), field: value})


def test_unknown_clauses_rejected(config):
    with pytest.raises(ValidationError):
        Intent.model_validate({**config.intent.model_dump(), "made_up": True})


def test_composition_distinguishes_strong_local(config):
    snapshot = snap()
    assert not local_violations(config, snapshot, Action.START_OR_CONTINUE_ROLLOUT)
    assert decide(config, snapshot, "B1")[0] == Action.START_OR_CONTINUE_ROLLOUT
    action, _, rejected, _ = decide(config, snapshot, "CATALYST")
    assert action == Action.SCALE_OUT
    assert rejected[0]["reasons"] == ["END_TO_END_LATENCY"]
    assert decide(config, snapshot, "A1") == decide(config, snapshot, "B1")
    assert decide(config, snapshot, "A2")[0] == Action.START_OR_CONTINUE_ROLLOUT


def test_quality_latency_tradeoff_and_unsafe_switch(config):
    unsafe = config.model_copy(update={"v2_service_ms": 8., "v2_quality": .8})
    snapshot = snap(inference=14.4, network=20.)
    assert "LOCAL_MODEL_QUALITY" in local_violations(unsafe, snapshot, Action.START_OR_CONTINUE_ROLLOUT)
    assert decide(unsafe, snapshot, "B1")[0] != Action.START_OR_CONTINUE_ROLLOUT
    assert decide(unsafe, snapshot, "CATALYST")[0] != Action.START_OR_CONTINUE_ROLLOUT


def test_reroute_to_overloaded_target(config):
    snapshot = replace(snap(), targets=(TargetView(2, 5, 100., 20.), TargetView(1, 12, 150., 24.)),
                       arrival_rate_rps=100.)
    reasons = local_violations(config, snapshot, Action.REROUTE)
    assert "LOCAL_DESTINATION_CAPACITY" in reasons
    assert decide(config, snapshot, "CATALYST")[0] != Action.REROUTE


def test_rollback_after_predicted_breach(config):
    snapshot = snap(inference=40., network=40., fraction=.5, workers=2, time=13.)
    action, _, rejected, prediction = decide(config, snapshot, "CATALYST")
    assert action == Action.ROLLBACK
    assert rejected[0]["source"] == "contract"
    assert not compile_contract(config.intent).violations(prediction)


def test_disruption_and_availability_guard(config):
    disruptive = config.model_copy(update={"rollout_disruption_s": .2})
    assert {"LOCAL_AVAILABILITY", "LOCAL_UPDATE_DISRUPTION"} <= set(
        local_violations(disruptive, snap(14.4, 20.), Action.START_OR_CONTINUE_ROLLOUT))


def test_capacity_and_network_events_share_engine(config):
    scenario = Scenario(family="S3", level=1, events=(Event(time_s=14., load_multiplier=1.2,
                        network_extra_delay_ms=10., capacity_reduction=.2, rollout_enabled=False),))
    assert scenario.state_at(13.)["capacity_reduction"] == 0.
    assert scenario.state_at(14.)["capacity_reduction"] == .2
    engine = Engine(config, scenario, workload(config, scenario, 0), "B1").run()
    assert engine.decisions[13]["snapshot"]["rollout_enabled"] is False
    assert len(engine.outcomes) == len(engine.tape.requests)


def test_empty_and_overdue_windows(config):
    scenario = next(matrix(config))
    engine = Engine(config, scenario, workload(config, scenario, 0), "B1")
    engine.env.run(until=1.)
    assert not engine.observe()[0].availability < 1.
    engine.pending[999] = 0.
    assert engine.observe()[0].availability == 0.


def test_seed_replay_and_request_conservation(config):
    scenario = list(matrix(config))[-1]
    tape = workload(config, scenario, 7)
    assert tape == workload(config, scenario, 7)
    first = Engine(config, scenario, tape, "CATALYST").run()
    second = Engine(config, scenario, tape, "CATALYST").run()
    assert first.summary() == second.summary()
    assert first.decisions == second.decisions
    assert {r["request_id"] for r in first.outcomes} == {r.request_id for r in tape.requests}
    assert len(first.samples) == round(config.duration_s / config.tick_s)


def test_a1_is_b1_on_same_tape(config):
    scenario = list(matrix(config))[-1]
    tape = workload(config, scenario, 4)
    baseline = Engine(config, scenario, tape, "B1").run()
    ablation = Engine(config, scenario, tape, "A1").run()
    assert baseline.outcomes == ablation.outcomes
    assert baseline.decisions == ablation.decisions


def test_controller_has_no_future_access():
    import catalyst.policies as policies
    source = inspect.getsource(policies)
    for forbidden in (".tape", "state_at", "service_factor", "version_draw", "network_draw", ".env", "Engine"):
        assert forbidden not in source


def test_reused_quantile_against_numpy_and_strict_logging(tmp_path):
    values = np.random.default_rng(0).normal(size=31).tolist()
    for probability in (0., .5, .95, .99, 1.):
        assert quantile(values, probability) == pytest.approx(np.quantile(values, probability))
    assert quantile([], .99) is None
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
    path = tmp_path / "evidence.json.gz"
    write_gzip(path, {"x": values})
    before = path.read_bytes()
    write_gzip(path, {"x": values})
    assert before == path.read_bytes()
    assert json.loads(gzip.decompress(before))["x"] == values
    with pytest.raises(ValueError):
        write_json(tmp_path / "invalid.json", {"x": float("nan")})


def test_matrix_is_100_tapes(config):
    scenarios = list(matrix(config))
    assert len(scenarios) * len(config.seeds) == 100
    assert [s.family for s in scenarios].count("S0") == 1


def test_shadow_forcing_is_independent_replay(config):
    scenario = next(matrix(config))
    tape = workload(config, scenario, 1)
    normal = Engine(config, scenario, tape, "CATALYST").run()
    shadow = Engine(config, scenario, tape, "CATALYST", forced=(10., Action.ROLLBACK)).run(stop_at=12.)
    assert shadow.decisions[9]["action"] == "ROLLBACK"
    assert normal.decisions[9]["action"] != "ROLLBACK"
    assert Engine(config, scenario, tape, "CATALYST").run().summary() == normal.summary()


def test_negative_control_requires_decisive_equality(config):
    from catalyst.experiment import check_negative
    scenario = next(matrix(config))
    tape = workload(config, scenario, 0)
    rows = [{**Engine(config, scenario, tape, policy).run().summary(), "seed": 0}
            for policy in ("B0", "B1", "CATALYST")]
    assert check_negative(rows, config)["passed"]
    rows[-1]["outcomes_hash"] = "different"
    assert not check_negative(rows, config)["passed"]


@pytest.mark.parametrize("failure", [None, "false_blocks", "completion_delay", "ablation_same", "seven_seeds", "zero_baseline"])
def test_hard_rule_rejects_superficial_gains(config, failure):
    import pandas as pd
    from catalyst.experiment import comparisons
    rows = []
    for seed in range(10):
        for policy in ("B0", "B1", "CATALYST", "A1", "A2"):
            breach = 9. if policy == "CATALYST" else 10.
            if failure == "ablation_same" and policy == "A2":
                breach = 9.
            if failure == "seven_seeds" and policy == "CATALYST" and seed < 3:
                breach = 10.
            if failure == "zero_baseline":
                breach = 0.
            rows.append(dict(seed=seed, family="S3", level=2, policy=policy,
                             total_service_contract_breach_seconds=breach,
                             rollout_completed=True, rollout_completion_time_s=14. if failure == "completion_delay" and policy == "CATALYST" else 10.,
                             false_blocks=2 if failure == "false_blocks" and policy == "CATALYST" else 0,
                             audited_contract_blocks=10, censored_contract_blocks=0))
    result = comparisons(pd.DataFrame(rows), config)[0]
    assert result["qualifying"] == (failure is None)
    if failure == "zero_baseline":
        assert result["improvement_pct"] is None

