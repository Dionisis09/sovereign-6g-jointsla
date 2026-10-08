from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from catalyst.reused import digest
from placement_experiment.algorithms import ALGORITHMS, sla_weighted_placement
from placement_experiment.data_generation import Application, Config, EdgeServer, Scenario, generate_scenario, estimate_latency
from placement_experiment.metrics import calculate_metrics


def fixture_scenario():
    return Scenario(0, (EdgeServer(0, 10., 10., 1000.), EdgeServer(1, 10., 10., 1000.)),
                    (Application(0, 0, 2., 2., 200., 25., 10.),
                     Application(1, 1, 2., 2., 200., 30., 20.)),
                    np.array([[0., 10.], [10., 0.]]))


def test_seeded_inputs_and_required_scenario():
    config = Config()
    first, second = generate_scenario(config, 7), generate_scenario(config, 7)
    assert first.to_dict() == second.to_dict()
    assert first.to_dict() != generate_scenario(config, 8).to_dict()
    assert len(first.nodes) == 5 and len(first.applications) == 20
    assert first.network_latency_ms.shape == (5, 5)
    assert np.array_equal(first.network_latency_ms, first.network_latency_ms.T)
    assert not first.network_latency_ms.flags.writeable
    assert np.all(np.diag(first.network_latency_ms) == 0)


@pytest.mark.parametrize("method", list(ALGORITHMS))
def test_determinism_input_immutability_and_all_capacities(method):
    config = Config()
    algorithm = ALGORITHMS[method]
    for seed in range(30):
        scenario = generate_scenario(config, seed)
        original = digest(scenario.to_dict())
        allocation = algorithm(config, scenario, seed)
        assert allocation == algorithm(config, scenario, seed)
        assert digest(scenario.to_dict()) == original
        metrics, outcomes = calculate_metrics(config, scenario, allocation)
        assert len(outcomes) == 20
        assert 0 <= metrics["sla_violation_rate"] <= 1
        assert all(0 <= value <= 1 + 1e-9 for key, value in metrics.items() if "utilization" in key)


@pytest.mark.parametrize("demand", [(11., 1., 1.), (1., 11., 1.), (1., 1., 1001.)])
def test_each_capacity_can_independently_reject(demand):
    scenario = Scenario(0, (EdgeServer(0, 10., 10., 1000.),),
                        (Application(0, 0, *demand, 50., 10.),), np.zeros((1, 1)))
    for algorithm in ALGORITHMS.values():
        assert algorithm(Config(), scenario, 0) == {0: None}
    with pytest.raises(ValueError, match="infeasible"):
        calculate_metrics(Config(), scenario, {0: 0})


def test_final_latency_and_weighted_denominators():
    config, scenario = Config(), fixture_scenario()
    metrics, outcomes = calculate_metrics(config, scenario, {0: 0, 1: 0})
    assert outcomes[0]["latency_ms"] == pytest.approx(22.08)
    assert outcomes[1]["latency_ms"] == pytest.approx(32.08)
    assert metrics["average_latency_ms"] == pytest.approx((10*22.08 + 20*32.08)/30)
    assert metrics["sla_violation_rate"] == pytest.approx(2/3)
    assert metrics["placed_sla_violation_rate"] == pytest.approx(2/3)
    assert metrics["cpu_utilization_node_0"] == pytest.approx(.4)
    # Even without a served latency violation, refused traffic still counts as failure.
    rejected, _ = calculate_metrics(config, scenario, {0: 0, 1: None})
    assert rejected["sla_violation_rate"] == pytest.approx(2/3)
    assert rejected["placed_sla_violation_rate"] == 0.
    assert rejected["unplaced_applications"] == 1


def test_no_placement_preserves_missing_latency():
    metrics, _ = calculate_metrics(Config(), fixture_scenario(), {0: None, 1: None})
    assert metrics["average_latency_ms"] is None
    assert metrics["placed_sla_violation_rate"] is None
    assert metrics["sla_violation_rate"] == 1.


def test_unknown_or_missing_assignments_rejected():
    with pytest.raises(ValueError, match="one assignment"):
        calculate_metrics(Config(), fixture_scenario(), {0: 0})
    with pytest.raises(ValueError, match="unknown node"):
        calculate_metrics(Config(), fixture_scenario(), {0: 0, 1: 99})


@pytest.mark.parametrize("sla,load", [(5., 10.), (100., 100.)])
def test_heuristic_prioritizes_stricter_sla_and_higher_load(sla, load):
    scenario = Scenario(0, (EdgeServer(0, 10., 10., 1000.),),
                        (Application(0, 0, 10., 10., 1000., 100., 10.),
                         Application(1, 0, 10., 10., 1000., sla, load)), np.zeros((1, 1)))
    assert sla_weighted_placement(Config(), scenario, 0) == {1: 0, 0: None}
    assert sla_weighted_placement(Config(), scenario, 99) == {1: 0, 0: None}


def test_deterministic_tie_break_and_latency_monotonicity():
    scenario = fixture_scenario()
    app = scenario.applications[0]
    assert estimate_latency(Config(), scenario, app, 0, app.demand * 2) > estimate_latency(Config(), scenario, app, 0, app.demand)
    assert estimate_latency(Config(), scenario, app, 1, app.demand) > estimate_latency(Config(), scenario, app, 0, app.demand)
    tied = replace(scenario, applications=(app,), network_latency_ms=np.zeros((2, 2)))
    assert sla_weighted_placement(Config(), tied, 0)[0] == 0


@pytest.mark.parametrize("options", [dict(trials=29), dict(first_seed=-1), dict(node_count=0),
                                    dict(cpu_capacity=(20., 10.)), dict(sla_risk_weight=float("nan"))])
def test_invalid_configuration(options):
    with pytest.raises(ValueError):
        Config(**options)


def test_runner_csv_summary_matches_paired_trials(tmp_path, monkeypatch):
    from placement_experiment import runner
    monkeypatch.setattr(runner, "create_plots", lambda *args: None)
    frame, summary = runner.run_experiment(Config(), tmp_path)
    saved = pd.read_csv(tmp_path / "results.csv")
    assert len(saved) == 30 * 4
    assert (saved.groupby("seed").scenario_hash.nunique() == 1).all()
    assert len(pd.read_csv(tmp_path / "application_outcomes.csv")) == 30 * 4 * 20
    for algorithm, group in frame.groupby("algorithm"):
        for column in ["average_latency_ms", "sla_violation_rate", "cpu_utilization_node_0", "runtime_ms"]:
            assert summary.loc[algorithm, f"{column}_mean"] == pytest.approx(group[column].mean())
            assert summary.loc[algorithm, f"{column}_std"] == pytest.approx(group[column].std(ddof=1))
    assert len(json.loads((tmp_path / "scenarios.json").read_text())) == 30
