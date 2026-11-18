"""Frozen-seed, multi-service CPU counterfactual data; no GPU claims."""

import argparse
import gzip
import io
import json
from pathlib import Path
from typing import Any

from .domain import Tier
from .research_data import sha256
from .research_subscription import PROTOCOL as PARENT_PROTOCOL
from .research_subscription import ROOT, State, _choose, p95, traffic

PROTOCOL = ROOT / "docs" / "SUBSCRIPTION_FORECAST_PROTOCOL.json"
TIERS = (Tier.GOLD, Tier.SILVER, Tier.BRONZE)


def _latency(queue: float, replicas: int, parent: dict[str, Any]) -> float:
    return float(parent["network_ms"]) + float(parent["cycle_ms"]) * (1 + queue / replicas)


def _future_labels(
    state: State, target: int, future: tuple[dict[Tier, float], ...], parent: dict[str, Any]
) -> dict[str, Any]:
    """Simulate one target for one service; future tape is used only for labels."""
    current = state.replicas
    slo = float(parent["tiers"][state.tier.value]["slo_ms"])
    capacity_per_replica = 1000 / float(parent["cycle_ms"])
    baseline_queue = state.queue
    action_queue = state.queue
    incident = _latency(state.queue, current, parent) > slo
    first_noop_breach: int | None = 0 if incident else None
    first_action_slo: int | None = 0 if not incident else None
    any_action_breach = incident
    post_action_slo = not incident
    for index, arrivals in enumerate(future, start=1):
        arrival = arrivals[state.tier]
        baseline_queue = max(0.0, baseline_queue + arrival - current * capacity_per_replica)
        if first_noop_breach is None and _latency(baseline_queue, current, parent) > slo:
            first_noop_breach = index
        active = current if target > current and index <= int(parent["scale_ready_after_ticks"]) else target
        action_queue = max(0.0, action_queue + arrival - active * capacity_per_replica)
        post_action_slo = _latency(action_queue, active, parent) <= slo
        any_action_breach |= not post_action_slo
        if first_action_slo is None and post_action_slo:
            first_action_slo = index
    return {
        "ttv_tick": first_noop_breach,
        "ttv_censored": first_noop_breach is None,
        "ttr_tick": first_action_slo,
        "ttr_censored": first_action_slo is None,
        "post_slo": post_action_slo,
        "any_action_breach": any_action_breach,
    }


def _step(
    states: dict[Tier, State], arrivals: dict[Tier, float], parent: dict[str, Any], policy: str
) -> None:
    targets, _ = _choose(policy, states, parent)
    for tier in TIERS:
        state = states[tier]
        target = targets[tier]
        if target < state.replicas:
            state.replicas = target
        elif target > state.replicas:
            state.pending_target = target
            state.pending_ticks = int(parent["scale_ready_after_ticks"]) + 1
        if state.pending_ticks:
            state.pending_ticks -= 1
            if state.pending_ticks == 0:
                state.replicas = state.pending_target
                state.pending_target = 0
        state.queue = max(
            0.0, state.queue + arrivals[tier] - state.replicas * 1000 / float(parent["cycle_ms"])
        )
        state.observed_arrival = arrivals[tier]


def episode_rows(
    family: str, seed: int, behavior: str, protocol: dict[str, Any], parent: dict[str, Any]
) -> list[dict[str, Any]]:
    """Capture pre-action features and feasible single-service action outcomes."""
    tape = traffic(family, seed, parent)
    states = {
        tier: State(
            tier,
            2.0,
            int(parent["tiers"][tier.value]["initial_replicas"]),
            float(parent["tiers"][tier.value]["base_arrival_rps"]),
        )
        for tier in TIERS
    }
    horizon = int(protocol["horizon_ticks"])
    rows = []
    for tick, arrivals in enumerate(tape):
        if tick + horizon <= len(tape) and not any(s.pending_ticks for s in states.values()):
            future = tape[tick : tick + horizon]
            for tier in TIERS:
                state = states[tier]
                other = sum(s.replicas for key, s in states.items() if key != tier)
                floor = 2 if tier == Tier.GOLD else 1
                for target in range(floor, int(parent["max_replicas_per_service"]) + 1):
                    if other + target > int(parent["pod_budget"]):
                        continue
                    row = {
                        "family": family,
                        "seed": seed,
                        "behavior": behavior,
                        "tick": tick,
                        "tier": tier.value,
                        "queue": round(state.queue, 6),
                        "ready_replicas": state.replicas,
                        "observed_arrival_rps": round(state.observed_arrival, 6),
                        "current_p95_ms": round(p95(state, parent), 6),
                        "slo_ms": float(parent["tiers"][tier.value]["slo_ms"]),
                        "target_replicas": target,
                        "other_ready_replicas": other,
                    }
                    row.update(_future_labels(state, target, future, parent))
                    rows.append(row)
        _step(states, arrivals, parent, behavior)
    return rows


def generate_split(split: str, protocol: dict[str, Any], parent: dict[str, Any]) -> list[dict[str, Any]]:
    low, high = protocol["seed_splits"][split]
    return [
        row
        for seed in range(low, high + 1)
        for family in protocol["scenario_families"]
        for behavior in protocol["behavior_policies"]
        for row in episode_rows(family, seed, behavior, protocol, parent)
    ]


def _gzip_jsonl(rows: list[dict[str, Any]]) -> bytes:
    data = ("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(data)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "subscription-forecast-v1")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    parent = json.loads(PARENT_PROTOCOL.read_text(encoding="utf-8"))
    splits = [set(range(a, b + 1)) for a, b in protocol["seed_splits"].values()]
    if any(left & right for i, left in enumerate(splits) for right in splits[i + 1 :]):
        raise ValueError("seed split overlap")
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("refusing to overwrite nonempty output")
    args.output.mkdir(parents=True, exist_ok=True)
    counts = {}
    for split in ("train", "validation", "test"):
        rows = generate_split(split, protocol, parent)
        (args.output / f"{split}.jsonl.gz").write_bytes(_gzip_jsonl(rows))
        counts[split] = {
            "rows": len(rows),
            "ttv_observed": sum(not row["ttv_censored"] for row in rows),
            "ttr_observed": sum(not row["ttr_censored"] for row in rows),
            "post_slo_positive": sum(row["post_slo"] for row in rows),
        }
    (args.output / "counts.json").write_bytes((json.dumps(counts, indent=2) + "\n").encode("utf-8"))
    paths = [
        PROTOCOL,
        PARENT_PROTOCOL,
        Path(__file__),
        ROOT / "sovereign_maas/research_subscription.py",
        *(args.output / f"{split}.jsonl.gz" for split in ("train", "validation", "test")),
        args.output / "counts.json",
    ]
    manifest = {path.relative_to(ROOT).as_posix(): sha256(path) for path in paths}
    (args.output / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
