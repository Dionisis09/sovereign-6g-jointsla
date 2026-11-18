"""Leakage, feasibility and frozen-output checks for subscription forecasts."""

import gzip
import json

from sovereign_maas.domain import Tier
from sovereign_maas.research_data import sha256
from sovereign_maas.research_subscription import ROOT, State
from sovereign_maas.research_subscription_data import (
    PROTOCOL,
    _future_labels,
    _gzip_jsonl,
    episode_rows,
)


def plans() -> tuple[dict, dict]:
    return (
        json.loads(PROTOCOL.read_text(encoding="utf-8")),
        json.loads((ROOT / "docs/SUBSCRIPTION_EXPERIMENT_PROTOCOL.json").read_text(encoding="utf-8")),
    )


def test_future_is_used_for_labels_not_current_features() -> None:
    _, parent = plans()
    state = State(Tier.GOLD, 2.0, 2, 34.0)
    quiet = tuple({Tier.GOLD: 10.0} for _ in range(4))
    overload = tuple({Tier.GOLD: 100.0} for _ in range(4))
    assert _future_labels(state, 2, quiet, parent)["post_slo"]
    assert not _future_labels(state, 2, overload, parent)["post_slo"]
    assert state.queue == 2.0 and state.observed_arrival == 34.0


def test_ttv_label_is_common_to_actions_at_same_snapshot() -> None:
    protocol, parent = plans()
    rows = episode_rows("burst", 300, "fixed_floor", protocol, parent)
    same_snapshot = [r for r in rows if r["tick"] == 0 and r["tier"] == "Gold"]
    assert len(same_snapshot) >= 2
    assert len({(r["ttv_tick"], r["ttv_censored"]) for r in same_snapshot}) == 1
    assert all(r["target_replicas"] + r["other_ready_replicas"] <= parent["pod_budget"] for r in rows)


def test_compressed_output_is_deterministic_and_decodable() -> None:
    rows = [{"tier": "Gold", "post_slo": True}, {"tier": "Bronze", "post_slo": False}]
    first = _gzip_jsonl(rows)
    assert first == _gzip_jsonl(rows)
    assert [json.loads(line) for line in gzip.decompress(first).decode().splitlines()] == rows


def test_frozen_data_hashes_and_split_separation() -> None:
    protocol, _ = plans()
    bounds = [set(range(low, high + 1)) for low, high in protocol["seed_splits"].values()]
    assert all(not left & right for i, left in enumerate(bounds) for right in bounds[i + 1 :])
    manifest = json.loads(
        (ROOT / "results/subscription-forecast-v1/manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest) == 8
    assert all(sha256(ROOT / path) == digest for path, digest in manifest.items())
