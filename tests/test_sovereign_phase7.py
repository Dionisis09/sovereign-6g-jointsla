"""Offline Phase 7 masking, split isolation, deterministic evidence and no promotion."""

import json
from shutil import copyfile

import numpy as np
import pytest

from sovereign_maas.research_data import sha256
from sovereign_maas.research_phase7 import (
    PROTOCOL,
    ROOT,
    RewardProposal,
    evaluate,
    load_cases,
    masked_probabilities,
    policy_action,
    reward,
    run_experiment,
    train,
)

DATASET = ROOT / "results" / "phase2-v1"


@pytest.fixture(scope="module")
def cases():
    return load_cases(DATASET)[0]


def test_frozen_input_split_and_current_state_masks(cases):
    assert len(cases) == 500
    assert {
        split: sum(case.split == split for case in cases) for split in ("train", "validation", "test")
    } == {
        "train": 300,
        "validation": 100,
        "test": 100,
    }
    assert {
        split: sum(case.valid_actions[1] for case in cases if case.split == split)
        for split in ("train", "validation", "test")
    } == {
        "train": 125,
        "validation": 46,
        "test": 32,
    }
    assert all(case.valid_actions[0] for case in cases)
    assert all(len(case.features) == 7 and case.features[0] == 1.0 for case in cases)
    assert set(cases[0].outcomes) == {"noop", "scale_out", "migrate"}
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["migration_mask"] == "always_invalid_without_residency_evidence"


def test_masked_policy_never_samples_denied_action(cases):
    denied = next(case for case in cases if not case.valid_actions[1])
    allowed = next(case for case in cases if case.valid_actions[1])
    theta = np.ones((2, 7))
    assert masked_probabilities(theta, denied).tolist() == [1.0, 0.0]
    assert policy_action(theta, denied) == "noop"
    assert np.isclose(masked_probabilities(theta, allowed).sum(), 1.0)
    with pytest.raises(ValueError, match="invalid masked action"):
        reward(
            denied,
            "scale_out",
            RewardProposal.model_validate(json.loads(PROTOCOL.read_text())["reward_proposals"][0]),
        )
    with pytest.raises(ValueError, match="policy selected a masked action"):
        evaluate((denied,), lambda case: "scale_out")


def test_reinforce_uses_train_only_and_is_seed_reproducible(cases):
    proposal = RewardProposal.model_validate(json.loads(PROTOCOL.read_text())["reward_proposals"][0])
    training = tuple(case for case in cases if case.split == "train")
    first = train(training, proposal, 11, 3, 0.02, 0.9)
    second = train(training, proposal, 11, 3, 0.02, 0.9)
    assert np.array_equal(first, second)
    assert np.isfinite(first).all()
    assert not np.array_equal(first, np.zeros_like(first))
    with pytest.raises(ValueError, match="train split only"):
        train(tuple(case for case in cases if case.split == "test"), proposal, 11, 3, 0.02, 0.9)


def test_dataset_hash_mismatch_is_rejected(tmp_path):
    for name in ("dataset_manifest.json", "episodes.parquet", "actions.parquet"):
        copyfile(DATASET / name, tmp_path / name)
    with (tmp_path / "actions.parquet").open("ab") as output:
        output.write(b"tampered")
    with pytest.raises(RuntimeError, match="dataset checksum mismatch"):
        load_cases(tmp_path)


def test_experiment_is_immutable_and_never_activates_policy(tmp_path):
    output = tmp_path / "phase7"
    metrics = run_experiment(DATASET, output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    model = json.loads((output / "models.json").read_text(encoding="utf-8"))
    reflection = json.loads((output / "reflection.json").read_text(encoding="utf-8"))
    assert metrics["chosen_proposal"] == "action_efficient"
    assert metrics["selection_split"] == "validation"
    assert metrics["test_policy_mean_simulated_slo_rate"] == 0.32
    assert metrics["test_policy_mean_action_rate"] == 0.32
    assert metrics["test_slo_delta_vs_jointsla"] == 0.0
    assert metrics["paired_seed_bootstrap_95pct_slo_delta"] == (0.0, 0.0)
    assert metrics["promotion"]["automatic_runtime_promotion"] is False
    assert model["runtime_enabled"] is False
    assert reflection["source"] == "OFFLINE_FIXTURE"
    assert len(reflection["iterations"]) == 3
    assert len(model["weights"]) == 5
    for name, digest in manifest["output_sha256"].items():
        assert sha256(output / name) == digest
    before = (output / "metrics.json").read_bytes()
    assert run_experiment(DATASET, output) == metrics
    assert (output / "metrics.json").read_bytes() == before
    (output / "metrics.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing overwrite|output differs"):
        run_experiment(DATASET, output)
