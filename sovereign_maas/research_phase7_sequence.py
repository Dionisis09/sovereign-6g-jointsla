"""CPU-only multi-step queue experiment; no Kubernetes or hardware effects."""

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from .research_data import profile, seeded_rng, sha256
from .research_phase7 import current_state_mask
from .simulation import latency

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "PHASE7_SEQUENCE_PROTOCOL.json"
ACTIONS = ("noop", "scale_out")


@dataclass
class SequenceEnvironment:
    family: str
    seed: int
    horizon: int
    delay: int
    failure_probability: float
    queue: float
    base_arrival: float
    base_cycle: float
    base_network: float
    slo: float
    tick: int = 0
    replicas: int = 1
    pending: int = 0
    attempted: bool = False
    failed: bool = False

    @classmethod
    def create(cls, family: str, seed: int, protocol: dict[str, Any]) -> "SequenceEnvironment":
        rng = seeded_rng(family, seed)
        queue = rng.randint(0, 5)
        arrival = round(rng.uniform(43, 58), 3)
        cycle = round(rng.uniform(18, 25), 3)
        network = round(rng.uniform(8, 20), 3)
        slo = round(latency(queue, 1, network, cycle) + rng.uniform(40, 100), 3)
        return cls(
            family=family,
            seed=seed,
            horizon=int(protocol["horizon_ticks"]),
            delay=int(protocol["scale_ready_after_ticks"]),
            failure_probability=float(protocol["scale_failure_probability"]),
            queue=float(queue),
            base_arrival=arrival,
            base_cycle=cycle,
            base_network=network,
            slo=slo,
        )

    def observed(self) -> SimpleNamespace:
        arrival, cycle, network = profile(
            self.family, self.tick, self.base_arrival, self.base_cycle, self.base_network
        )
        p95 = latency(self.queue, self.replicas, network, cycle)
        return SimpleNamespace(
            seed=self.seed,
            queue_depth=round(self.queue),
            arrival_rps=arrival,
            cycle_ms=cycle,
            network_ms=network,
            slo_ms=self.slo,
            observed_p95_ms=p95,
            headroom_ms=self.slo - p95,
        )

    def valid_actions(self) -> tuple[bool, bool]:
        if self.attempted or self.pending or self.replicas > 1:
            return True, False
        return current_state_mask(self.observed())

    def features(self) -> np.ndarray:
        row = self.observed()
        return np.asarray(
            [
                1.0,
                min(row.queue_depth / 20, 4),
                row.arrival_rps / 100,
                row.cycle_ms / 50,
                row.network_ms / 100,
                row.slo_ms / 200,
                max(-4, min(row.headroom_ms / 200, 4)),
                self.tick / self.horizon,
                self.replicas / 2,
                self.pending / 2,
                float(self.attempted),
            ],
            dtype=float,
        )

    def step(self, action: str) -> tuple[float, bool, float, bool]:
        if self.tick >= self.horizon:
            raise ValueError("episode already complete")
        if action not in ACTIONS or not self.valid_actions()[ACTIONS.index(action)]:
            raise ValueError("masked or unknown action")
        failure_now = False
        if action == "scale_out":
            self.attempted = True
            self.pending = self.delay
            failure_now = seeded_rng(self.family, self.seed, "sequence_scale_failure").random() < (
                self.failure_probability
            )
            self.failed = failure_now
        next_tick = self.tick + 1
        arrival, cycle, network = profile(
            self.family, next_tick, self.base_arrival, self.base_cycle, self.base_network
        )
        if self.pending:
            self.pending -= 1
            if self.pending == 0 and not self.failed:
                self.replicas = 2
        self.queue = max(0.0, self.queue + arrival - self.replicas * 1000 / cycle)
        self.tick = next_tick
        p95 = latency(self.queue, self.replicas, network, cycle)
        breach = p95 > self.slo
        reward = (
            1.0
            - float(breach)
            - 0.1 * min(p95 / self.slo, 4.0)
            - 0.05 * float(action == "scale_out")
            - 0.2 * float(failure_now)
        )
        return reward, breach, p95, failure_now


def choose_q(weights: np.ndarray, env: SequenceEnvironment) -> str:
    values = weights @ env.features()
    valid = env.valid_actions()
    values = np.where(valid, values, -np.inf)
    return ACTIONS[int(np.argmax(values))]


def q_policy(weights: np.ndarray) -> Callable[[SequenceEnvironment], str]:
    def choose(env: SequenceEnvironment) -> str:
        return choose_q(weights, env)

    return choose


def train(protocol: dict[str, Any], policy_seed: int) -> np.ndarray:
    weights = np.zeros((2, 11), dtype=float)
    rng = np.random.default_rng(policy_seed)
    episodes = [
        (family, seed)
        for seed in range(*_inclusive_range(protocol["seed_splits"]["train"]))
        for family in protocol["scenario_families"]
    ]
    for _ in range(int(protocol["epochs"])):
        for index in rng.permutation(len(episodes)):
            family, seed = episodes[int(index)]
            env = SequenceEnvironment.create(family, seed, protocol)
            while env.tick < env.horizon:
                state = env.features()
                valid = env.valid_actions()
                if valid[1] and rng.random() < float(protocol["exploration_epsilon"]):
                    action = ACTIONS[int(rng.integers(0, 2))]
                else:
                    action = choose_q(weights, env)
                reward, _, _, _ = env.step(action)
                index_action = ACTIONS.index(action)
                target = reward
                if env.tick < env.horizon:
                    future = weights @ env.features()
                    target += float(protocol["discount"]) * float(
                        np.max(np.where(env.valid_actions(), future, -np.inf))
                    )
                error = target - float(weights[index_action] @ state)
                weights[index_action] += float(protocol["learning_rate"]) * error * state
                np.clip(weights, -10, 10, out=weights)
    return weights


def _inclusive_range(bounds: list[int]) -> tuple[int, int]:
    return int(bounds[0]), int(bounds[1]) + 1


def evaluate(
    protocol: dict[str, Any], split: str, name: str, chooser: Callable[[SequenceEnvironment], str]
) -> list[dict[str, Any]]:
    rows = []
    for seed in range(*_inclusive_range(protocol["seed_splits"][split])):
        for family in protocol["scenario_families"]:
            env = SequenceEnvironment.create(family, seed, protocol)
            breaches = 0
            cumulative_reward = 0.0
            attempts = 0
            failures = 0
            for _ in range(env.horizon):
                action = chooser(env)
                reward, breach, _, failed = env.step(action)
                breaches += int(breach)
                cumulative_reward += reward
                attempts += int(action == "scale_out")
                failures += int(failed)
            rows.append(
                {
                    "policy": name,
                    "split": split,
                    "family": family,
                    "seed": seed,
                    "breach_ticks": breaches,
                    "any_breach": int(breaches > 0),
                    "scale_attempts": attempts,
                    "failed_attempts": failures,
                    "return": round(cumulative_reward, 6),
                }
            )
    return rows


def summary(rows: list[dict[str, Any]], horizon: int) -> dict[str, float | int]:
    return {
        "episodes": len(rows),
        "simulated_breach_tick_rate": sum(r["breach_ticks"] for r in rows) / (len(rows) * horizon),
        "simulated_any_breach_rate": sum(r["any_breach"] for r in rows) / len(rows),
        "action_rate": sum(r["scale_attempts"] for r in rows) / len(rows),
        "failed_attempt_rate": sum(r["failed_attempts"] for r in rows) / len(rows),
        "mean_return": sum(r["return"] for r in rows) / len(rows),
    }


def paired_interval(
    policy_rows: list[dict[str, Any]], baseline_rows: list[dict[str, Any]], protocol: dict[str, Any]
) -> dict[str, float]:
    a = {(r["family"], r["seed"]): r for r in policy_rows}
    b = {(r["family"], r["seed"]): r for r in baseline_rows}
    if a.keys() != b.keys():
        raise ValueError("paired episodes differ")
    keys = sorted(a)
    gains = np.asarray([b[key]["any_breach"] - a[key]["any_breach"] for key in keys])
    rng = np.random.default_rng(protocol["bootstrap"]["seed"])
    samples = rng.integers(0, len(keys), size=(int(protocol["bootstrap"]["draws"]), len(keys)))
    bootstrap = gains[samples].mean(axis=1)
    return {
        "breach_reduction": float(gains.mean()),
        "lower_95pct": float(np.quantile(bootstrap, 0.025)),
        "upper_95pct": float(np.quantile(bootstrap, 0.975)),
    }


def run(output: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    splits = [
        set(range(*_inclusive_range(protocol["seed_splits"][name])))
        for name in ("train", "validation", "test")
    ]
    if any(left & right for i, left in enumerate(splits) for right in splits[i + 1 :]):
        raise ValueError("overlapping seed splits")
    if min(splits[0]) < 120 or protocol["registered_before_outcome_generation"] is not True:
        raise ValueError("invalid preregistration or seed reuse")
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, digest in manifest["output_sha256"].items():
            if sha256(output / name) != digest:
                raise RuntimeError(f"frozen output changed: {name}")
        for name, digest in manifest["source_sha256"].items():
            if sha256(ROOT / name) != digest:
                raise RuntimeError(f"frozen source changed: {name}")
        return manifest
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory is not empty")
    output.mkdir(parents=True, exist_ok=True)
    policies: dict[str, Callable[[SequenceEnvironment], str]] = {
        "noop": lambda env: "noop",
        "sla_threshold_70ms": lambda env: (
            "scale_out" if env.valid_actions()[1] and env.observed().headroom_ms < 70 else "noop"
        ),
        "jointsla_gate": lambda env: "scale_out" if env.valid_actions()[1] else "noop",
    }
    models = {}
    for seed in protocol["training_policy_seeds"]:
        weights = train(protocol, int(seed))
        name = f"q_seed_{seed}"
        models[name] = weights.tolist()
        policies[name] = q_policy(weights)
    validation = {name: evaluate(protocol, "validation", name, chooser) for name, chooser in policies.items()}
    candidates = [name for name in policies if name.startswith("q_seed_")]
    selected = min(
        candidates,
        key=lambda name: (
            summary(validation[name], protocol["horizon_ticks"])["simulated_any_breach_rate"],
            summary(validation[name], protocol["horizon_ticks"])["action_rate"],
            int(name.removeprefix("q_seed_")),
        ),
    )
    test = {
        name: evaluate(protocol, "test", name, policies[name])
        for name in (*tuple(name for name in policies if not name.startswith("q_seed_")), selected)
    }
    interval = paired_interval(test[selected], test["jointsla_gate"], protocol)
    test_summary = {name: summary(rows, protocol["horizon_ticks"]) for name, rows in test.items()}
    metrics = {
        "evidence": "SIMULATION_ONLY_CPU",
        "selected_policy": selected,
        "validation": {name: summary(rows, protocol["horizon_ticks"]) for name, rows in validation.items()},
        "test": test_summary,
        "paired_vs_jointsla": interval,
        "mask_violations": 0,
        "promotion_eligible": bool(
            interval["lower_95pct"] > 0
            and test_summary[selected]["action_rate"] <= test_summary["jointsla_gate"]["action_rate"]
        ),
    }
    (output / "models.json").write_text(json.dumps(models, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output / "episodes.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for split_rows in (validation, test):
            for rows in split_rows.values():
                for row in rows:
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
    sources = (
        "docs/PHASE7_SEQUENCE_PROTOCOL.json",
        "sovereign_maas/research_phase7_sequence.py",
        "sovereign_maas/research_data.py",
        "sovereign_maas/research_phase7.py",
        "sovereign_maas/decision.py",
        "sovereign_maas/simulation.py",
    )
    manifest = {
        "protocol_version": protocol["protocol_version"],
        "evidence": "SIMULATION_ONLY_CPU",
        "output_sha256": {
            name: sha256(output / name) for name in ("models.json", "metrics.json", "episodes.jsonl")
        },
        "source_sha256": {name: sha256(ROOT / name) for name in sources},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "phase7-sequence-v1")
    args = parser.parse_args()
    manifest = run(args.output)
    print(json.dumps({"status": "PASS", "protocol_version": manifest["protocol_version"]}, sort_keys=True))


if __name__ == "__main__":
    main()
