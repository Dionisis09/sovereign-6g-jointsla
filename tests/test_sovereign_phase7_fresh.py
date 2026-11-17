"""Checks for prospective frozen-weight synthetic evaluation."""

import json

import pytest

from sovereign_maas.research_data import sha256, split_plan
from sovereign_maas.research_phase7_fresh import (
    MODEL,
    PHASE7_MANIFEST,
    PROTOCOL,
    fresh_cases,
    run_evaluation,
)


def test_protocol_precedes_fresh_data_and_model_is_frozen() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    split = split_plan()
    assert protocol["registered_before_outcome_generation"] is True
    assert protocol["seed_range_inclusive"] == [100, 119]
    assert not set(range(100, 120)) & set(
        split["train_seeds"] + split["validation_seeds"] + split["test_seeds"]
    )
    assert sha256(MODEL) == protocol["frozen_model_sha256"]
    assert sha256(PHASE7_MANIFEST) == protocol["frozen_phase7_manifest_sha256"]
    assert json.loads(MODEL.read_text(encoding="utf-8"))["runtime_enabled"] is False


def test_fresh_cases_cover_registered_pressure_and_preserve_action_mask() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    groups = fresh_cases(protocol)
    assert set(groups) == {"1.0", "1.2", "1.5"}
    for cases in groups.values():
        assert len(cases) == 100
        assert {case.seed for case in cases} == set(range(100, 120))
        assert {case.family for case in cases} == set(protocol["scenario_families"])
        assert all(case.valid_actions[0] for case in cases)
        assert all(case.split == "fresh_test" for case in cases)
        assert all(set(case.outcomes) == {"noop", "scale_out", "migrate"} for case in cases)


def test_fresh_artifact_is_exactly_reproducible_and_refuses_tampering(tmp_path) -> None:
    output = tmp_path / "fresh"
    first = run_evaluation(output)
    original = {file.name: file.read_bytes() for file in output.iterdir()}
    second = run_evaluation(output)
    assert first == second
    assert {file.name: file.read_bytes() for file in output.iterdir()} == original
    assert first["promotion"]["automatic_runtime_promotion"] is False
    assert all(item["n_cases"] == 100 for item in first["pressure"].values())
    (output / "metrics.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(FileExistsError, match="existing fresh output differs"):
        run_evaluation(output)


def test_changed_frozen_model_hash_is_rejected(monkeypatch, tmp_path) -> None:
    import sovereign_maas.research_phase7_fresh as evaluator

    replacement = tmp_path / "models.json"
    replacement.write_bytes(MODEL.read_bytes() + b" ")
    monkeypatch.setattr(evaluator, "MODEL", replacement)
    with pytest.raises(RuntimeError, match="model hash mismatch"):
        run_evaluation(tmp_path / "fresh")
