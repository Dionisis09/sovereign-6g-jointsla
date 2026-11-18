"""Reproducibility and shared-budget checks for the synthetic study."""

import json

from sovereign_maas.domain import Tier
from sovereign_maas.research_data import sha256
from sovereign_maas.research_subscription import (
    POLICIES,
    PROTOCOL,
    ROOT,
    State,
    _bounded_targets,
    evaluate,
    run_episode,
    summarize,
    traffic,
)


def protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def test_matched_tape_is_deterministic() -> None:
    plan = protocol()
    assert traffic("burst", 220, plan) == traffic("burst", 220, plan)
    assert traffic("burst", 220, plan) != traffic("burst", 221, plan)


def test_shared_budget_prefers_gold_when_scaling_is_contested() -> None:
    states = {tier: State(tier, 0, 2 if tier == Tier.GOLD else 1, 20) for tier in Tier}
    target = _bounded_targets(states, {tier: 4 for tier in Tier}, 5)
    assert target == {Tier.GOLD: 3, Tier.SILVER: 1, Tier.BRONZE: 1}


def test_every_policy_replays_same_seed_with_bounded_resources() -> None:
    plan = protocol()
    for policy in POLICIES:
        row = run_episode("ramp", 220, policy, plan)
        assert row == run_episode("ramp", 220, policy, plan)
        assert 0 <= row["all_breach_ticks"] <= 3 * plan["horizon_ticks"]
        assert row["pod_ticks"] <= plan["pod_budget"] * plan["horizon_ticks"]


def test_seed_splits_and_result_shape() -> None:
    plan = protocol()
    dev = set(range(plan["seed_splits"]["development"][0], plan["seed_splits"]["development"][1] + 1))
    test = set(range(plan["seed_splits"]["test"][0], plan["seed_splits"]["test"][1] + 1))
    assert not dev & test
    rows = evaluate(plan, "test")
    assert len(rows) == len(test) * len(plan["scenario_families"]) * len(POLICIES)
    assert {entry["policy"] for entry in summarize(rows, plan)} == set(POLICIES)


def test_frozen_subscription_output_hashes() -> None:
    manifest = json.loads((ROOT / "results/subscription-v1/manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 6
    assert all(sha256(ROOT / path) == digest for path, digest in manifest.items())
