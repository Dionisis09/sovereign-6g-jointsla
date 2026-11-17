"""Sequential CPU policy semantics and frozen result checks."""

import json

import numpy as np
import pytest

from sovereign_maas.research_phase7_sequence import (
    PROTOCOL,
    SequenceEnvironment,
    choose_q,
    evaluate,
    run,
    train,
)


def protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def test_seed_splits_are_new_and_disjoint() -> None:
    plan = protocol()
    ranges = [set(range(start, end + 1)) for start, end in plan["seed_splits"].values()]
    assert all(min(group) >= 120 for group in ranges)
    assert all(not left & right for i, left in enumerate(ranges) for right in ranges[i + 1 :])
    assert plan["registered_before_outcome_generation"] is True


def test_scale_effect_is_delayed_and_second_attempt_is_masked() -> None:
    env = SequenceEnvironment.create("steady", 120, protocol())
    assert env.valid_actions() == (True, True)
    _, _, _, failed = env.step("scale_out")
    assert not failed
    assert env.tick == 1 and env.pending == 1 and env.replicas == 1
    assert env.valid_actions() == (True, False)
    with pytest.raises(ValueError, match="masked"):
        env.step("scale_out")
    env.step("noop")
    assert env.tick == 2 and env.pending == 0 and env.replicas == 2
    assert env.valid_actions() == (True, False)


def test_failed_scale_never_changes_replica_count() -> None:
    plan = protocol()
    plan["scale_failure_probability"] = 1.0
    env = SequenceEnvironment.create("steady", 120, plan)
    _, _, _, failed = env.step("scale_out")
    assert failed
    while env.tick < env.horizon:
        env.step("noop")
    assert env.replicas == 1
    assert env.attempted and env.failed


def test_training_is_deterministic_and_policy_respects_mask() -> None:
    plan = protocol()
    first = train(plan, 11)
    assert np.array_equal(first, train(plan, 11))
    rows = evaluate(plan, "test", "q_seed_11", lambda env: choose_q(first, env))
    assert len(rows) == 100
    assert all(row["scale_attempts"] <= 1 for row in rows)


def test_frozen_output_replay_and_tamper_rejection(tmp_path) -> None:
    output = tmp_path / "sequential"
    manifest = run(output)
    originals = {path.name: path.read_bytes() for path in output.iterdir()}
    assert run(output) == manifest
    assert {path.name: path.read_bytes() for path in output.iterdir()} == originals
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["evidence"] == "SIMULATION_ONLY_CPU"
    assert metrics["mask_violations"] == 0
    (output / "metrics.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="frozen output changed"):
        run(output)
