"""Matched synthetic multi-service study; no live forecasts or actuation."""

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from joint_sla_v2.policy import required_warm

from .domain import Tier
from .research_data import sha256
from .subscription_optimizer import PodForecast, SubscriptionService, optimize

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "SUBSCRIPTION_EXPERIMENT_PROTOCOL.json"
POLICIES = ("fixed_floor", "reactive", "jointsla_warm", "subscription_optimizer")
TIERS = (Tier.GOLD, Tier.SILVER, Tier.BRONZE)


@dataclass
class State:
    tier: Tier
    queue: float
    replicas: int
    observed_arrival: float
    pending_target: int = 0
    pending_ticks: int = 0


def _rng(family: str, seed: int) -> random.Random:
    digest = hashlib.sha256(f"subscription-v1:{family}:{seed}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def traffic(family: str, seed: int, protocol: dict[str, Any]) -> tuple[dict[Tier, float], ...]:
    """Exogenous tape; policies observe only the previous tick's arrival."""
    rng = _rng(family, seed)
    tape = []
    for tick in range(int(protocol["horizon_ticks"])):
        row = {}
        for tier in TIERS:
            base = float(protocol["tiers"][tier.value]["base_arrival_rps"])
            if family == "ramp":
                base += (1.8 if tier == Tier.GOLD else 1.2) * tick
            elif family == "burst" and tick >= 5:
                base += {Tier.GOLD: 12, Tier.SILVER: 9, Tier.BRONZE: 7}[tier]
            row[tier] = max(0.0, base + rng.gauss(0, 2.0))
        tape.append(row)
    return tuple(tape)


def p95(state: State, protocol: dict[str, Any]) -> float:
    return float(protocol["network_ms"]) + float(protocol["cycle_ms"]) * (1 + state.queue / state.replicas)


def _forecast(state: State, protocol: dict[str, Any]) -> SubscriptionService:
    """Deliberately uncalibrated, current-observation-only analytic forecast."""
    cycle = float(protocol["cycle_ms"])
    network = float(protocol["network_ms"])
    slo = float(protocol["tiers"][state.tier.value]["slo_ms"])
    current_latency = p95(state, protocol)
    incident = current_latency > slo
    growth = max(0.0, state.observed_arrival - state.replicas * 1000 / cycle)
    queue_margin = max(0.0, (slo - network) / cycle - 1) * state.replicas - state.queue
    ttv = 0.0 if incident else (queue_margin / growth if growth > 0 else 1_000_000.0)
    options = []
    for target in range(1, int(protocol["max_replicas_per_service"]) + 1):
        ready = float(protocol["scale_ready_after_ticks"]) if target > state.replicas else 0.0
        pre_queue = max(0.0, state.queue + ready * (state.observed_arrival - state.replicas * 1000 / cycle))
        projected_queue = max(0.0, pre_queue + 3 * (state.observed_arrival - target * 1000 / cycle))
        projected_latency = network + cycle * (1 + projected_queue / target)
        # Logistic score is a synthetic heuristic, not calibrated probability.
        breach = 1 / (1 + math.exp(max(-40, min(40, (slo - projected_latency) / 35))))
        recovery = (
            2.0
            if target < state.replicas
            else (
                min(20.0, pre_queue / max(1.0, target * 1000 / cycle - state.observed_arrival))
                if target > state.replicas
                else 0.0
            )
        )
        options.append(PodForecast(target, breach, recovery, ready, 1 - breach))
    return SubscriptionService(
        state.tier.value.lower(),
        state.tier,
        state.replicas,
        int(protocol["max_replicas_per_service"]),
        max(0.0, current_latency / slo),
        ttv,
        0.0,
        False,
        incident,
        tuple(options),
    )


def _bounded_targets(states: dict[Tier, State], desired: dict[Tier, int], budget: int) -> dict[Tier, int]:
    """Apply downscales first, then allocate spare pods Gold→Silver→Bronze."""
    targets = {tier: min(states[tier].replicas, desired[tier]) for tier in TIERS}
    spare = budget - sum(targets.values())
    for tier in TIERS:
        extra = min(max(0, desired[tier] - targets[tier]), max(0, spare))
        targets[tier] += extra
        spare -= extra
    return targets


def _choose(policy: str, states: dict[Tier, State], protocol: dict[str, Any]) -> tuple[dict[Tier, int], bool]:
    current = {tier: states[tier].replicas for tier in TIERS}
    if policy == "fixed_floor":
        return current, False
    if any(state.pending_ticks for state in states.values()):
        return current, False
    if policy == "subscription_optimizer":
        try:
            allocation = optimize(
                tuple(_forecast(states[tier], protocol) for tier in TIERS),
                pod_budget=int(protocol["pod_budget"]),
            )
        except ValueError as error:
            if str(error) not in {"NO_TIER_SAFE_ALLOCATION", "POD_BUDGET_INFEASIBLE"}:
                raise
            return current, True
        return {Tier(name.capitalize()): count for name, count in allocation.targets}, False
    desired = {}
    for tier in TIERS:
        state = states[tier]
        floor = int(protocol["tiers"][tier.value]["initial_replicas"])
        if policy == "reactive":
            slo = float(protocol["tiers"][tier.value]["slo_ms"])
            desired[tier] = min(4, state.replicas + 1) if p95(state, protocol) > 0.9 * slo else floor
        elif policy == "jointsla_warm":
            desired[tier] = required_warm(
                round(state.queue),
                state.observed_arrival,
                float(protocol["scale_ready_after_ticks"]),
                float(protocol["cycle_ms"]) / 1000,
                float(protocol["tiers"][tier.value]["slo_ms"]) / 1000,
                tier.value,
                int(protocol["max_replicas_per_service"]),
            )
        else:
            raise ValueError("unknown policy")
    return _bounded_targets(states, desired, int(protocol["pod_budget"])), False


def run_episode(family: str, seed: int, policy: str, protocol: dict[str, Any]) -> dict[str, Any]:
    states = {
        tier: State(
            tier,
            2.0,
            int(protocol["tiers"][tier.value]["initial_replicas"]),
            float(protocol["tiers"][tier.value]["base_arrival_rps"]),
        )
        for tier in TIERS
    }
    tape = traffic(family, seed, protocol)
    breaches = {tier: 0 for tier in TIERS}
    pod_ticks = 0
    infeasible = 0
    for arrivals in tape:
        targets, failed = _choose(policy, states, protocol)
        infeasible += int(failed)
        for tier in TIERS:
            state = states[tier]
            target = targets[tier]
            if target < state.replicas:
                state.replicas = target
            elif target > state.replicas:
                state.pending_target = target
                state.pending_ticks = int(protocol["scale_ready_after_ticks"]) + 1
            if state.pending_ticks:
                state.pending_ticks -= 1
                if state.pending_ticks == 0:
                    state.replicas = state.pending_target
                    state.pending_target = 0
            pod_ticks += state.replicas
            state.queue = max(
                0.0, state.queue + arrivals[tier] - state.replicas * 1000 / float(protocol["cycle_ms"])
            )
            state.observed_arrival = arrivals[tier]
            breaches[tier] += int(p95(state, protocol) > float(protocol["tiers"][tier.value]["slo_ms"]))
    return {
        "family": family,
        "seed": seed,
        "policy": policy,
        "Gold_breach_ticks": breaches[Tier.GOLD],
        "Silver_breach_ticks": breaches[Tier.SILVER],
        "Bronze_breach_ticks": breaches[Tier.BRONZE],
        "all_breach_ticks": sum(breaches.values()),
        "pod_ticks": pod_ticks,
        "infeasible_decisions": infeasible,
    }


def evaluate(protocol: dict[str, Any], split: str) -> list[dict[str, Any]]:
    low, high = protocol["seed_splits"][split]
    return [
        run_episode(family, seed, policy, protocol)
        for seed in range(low, high + 1)
        for family in protocol["scenario_families"]
        for policy in POLICIES
    ]


def summarize(rows: list[dict[str, Any]], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    denominator = len(rows) / len(POLICIES) * int(protocol["horizon_ticks"])
    return [
        {
            "policy": policy,
            "Gold_breach_rate": sum(r["Gold_breach_ticks"] for r in rows if r["policy"] == policy)
            / denominator,
            "Silver_breach_rate": sum(r["Silver_breach_ticks"] for r in rows if r["policy"] == policy)
            / denominator,
            "Bronze_breach_rate": sum(r["Bronze_breach_ticks"] for r in rows if r["policy"] == policy)
            / denominator,
            "all_breach_rate": sum(r["all_breach_ticks"] for r in rows if r["policy"] == policy)
            / (3 * denominator),
            "pod_ticks_per_episode": sum(r["pod_ticks"] for r in rows if r["policy"] == policy)
            / (denominator / int(protocol["horizon_ticks"])),
            "infeasible_decisions": sum(r["infeasible_decisions"] for r in rows if r["policy"] == policy),
        }
        for policy in POLICIES
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "subscription-v1")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if set(
        range(*[protocol["seed_splits"]["development"][0], protocol["seed_splits"]["development"][1] + 1])
    ) & set(range(protocol["seed_splits"]["test"][0], protocol["seed_splits"]["test"][1] + 1)):
        raise ValueError("seed split overlap")
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("refusing to overwrite nonempty output")
    args.output.mkdir(parents=True, exist_ok=True)
    output = {}
    for split in ("development", "test"):
        rows = evaluate(protocol, split)
        (args.output / f"{split}_episodes.json").write_text(
            json.dumps(rows, indent=2) + "\n", encoding="utf-8"
        )
        output[split] = summarize(rows, protocol)
    (args.output / "summary.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    files = [
        PROTOCOL,
        Path(__file__),
        ROOT / "sovereign_maas" / "subscription_optimizer.py",
        *(args.output / name for name in ("development_episodes.json", "test_episodes.json", "summary.json")),
    ]
    (args.output / "manifest.json").write_text(
        json.dumps({str(p.relative_to(ROOT)): sha256(p) for p in files}, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output["test"], indent=2))


if __name__ == "__main__":
    main()
