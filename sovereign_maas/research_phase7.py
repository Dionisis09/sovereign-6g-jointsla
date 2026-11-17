"""Offline masked one-step policy gradient and bounded reward proposal audit."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from .decision import decide, propose
from .domain import ServiceBundle, StrictModel, TelemetrySnapshot, TopologyNode, TypedIntent
from .research_data import sha256, split_plan
from .research_models import load_frames

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "PHASE7_PROTOCOL.json"
ACTIONS = ("noop", "scale_out")


class RewardProposal(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    source: Literal["OFFLINE_FIXTURE"] = "OFFLINE_FIXTURE"
    slo_weight: float = Field(ge=0, le=2)
    latency_weight: float = Field(ge=0, le=1)
    recovery_weight: float = Field(ge=0, le=1)
    failure_weight: float = Field(ge=0, le=2)
    action_cost: float = Field(ge=0, le=1)


@dataclass(frozen=True)
class Outcome:
    post_sla: int
    post_p95_ms: float
    ttr_s: float
    action_failed: bool


@dataclass(frozen=True)
class Case:
    episode_id: str
    family: str
    seed: int
    split: str
    features: tuple[float, ...]
    valid_actions: tuple[bool, bool]
    headroom_ms: float
    slo_ms: float
    outcomes: dict[str, Outcome]


def features(row: Any) -> tuple[float, ...]:
    """Current-state features only; no scenario ID, seed or future outcome."""
    return (
        1.0,
        float(row.queue_depth) / 20.0,
        float(row.arrival_rps) / 100.0,
        float(row.cycle_ms) / 50.0,
        float(row.network_ms) / 100.0,
        float(row.slo_ms) / 200.0,
        float(row.headroom_ms) / 200.0,
    )


def current_state_mask(row: Any) -> tuple[bool, bool]:
    """Reuse the independent runtime gate under a fixed synthetic research profile."""
    service = ServiceBundle(
        tenant_id="offline-research",
        intent=TypedIntent(
            service_name="research-vision",
            tier="Gold",
            latency_p95_ms=float(row.slo_ms),
            minimum_model_quality=0.9,
            max_replicas=2,
            allowed_regions=("eu-gr",),
            allowed_actions=("scale_out",),
        ),
    )
    snapshot = TelemetrySnapshot(
        seed=int(row.seed),
        queue_depth=int(row.queue_depth),
        arrival_rps=float(row.arrival_rps),
        cycle_ms=float(row.cycle_ms),
        observed_p95_ms=float(row.observed_p95_ms),
        nodes=(
            TopologyNode(id="edge-a", region="eu-gr", network_ms=float(row.network_ms), replica_capacity=2),
            TopologyNode(id="cloud-a", region="eu-de", network_ms=80.0, replica_capacity=1),
        ),
    )
    candidates = propose(service, snapshot)
    decision = decide(service, snapshot, candidates)
    scale_allowed = decision.selected_candidate_id == "jointsla-scale" and not any(
        item.candidate_id == "jointsla-scale" for item in decision.rejected
    )
    return True, scale_allowed


def load_cases(dataset_dir: Path) -> tuple[tuple[Case, ...], dict[str, Any]]:
    episodes, actions, manifest = load_frames(dataset_dir)
    if set(actions["action_kind"]) != {"noop", "scale_out", "migrate"}:
        raise ValueError("unexpected action kinds")
    outcomes: dict[str, dict[str, Outcome]] = {}
    for row in actions.itertuples(index=False):
        outcome = Outcome(
            post_sla=int(row.post_sla),
            post_p95_ms=float(row.post_p95_ms),
            ttr_s=float(row.ttr_s),
            action_failed=bool(row.action_failed),
        )
        if row.action_kind in outcomes.setdefault(row.episode_id, {}):
            raise ValueError("duplicate action outcome")
        outcomes[row.episode_id][row.action_kind] = outcome
    cases = []
    for row in episodes.itertuples(index=False):
        if set(outcomes[row.episode_id]) != {"noop", "scale_out", "migrate"}:
            raise ValueError("missing action outcome")
        cases.append(
            Case(
                episode_id=row.episode_id,
                family=row.scenario_family,
                seed=int(row.seed),
                split=row.split,
                features=features(row),
                valid_actions=current_state_mask(row),
                headroom_ms=float(row.headroom_ms),
                slo_ms=float(row.slo_ms),
                outcomes=outcomes[row.episode_id],
            )
        )
    return tuple(cases), manifest


def reward(case: Case, action: str, proposal: RewardProposal) -> float:
    if action not in ACTIONS or not case.valid_actions[ACTIONS.index(action)]:
        raise ValueError("invalid masked action")
    outcome = case.outcomes[action]
    return (
        proposal.slo_weight * outcome.post_sla
        - proposal.latency_weight * min(outcome.post_p95_ms / case.slo_ms, 4.0)
        - proposal.recovery_weight * min(outcome.ttr_s / 12.0, 1.0)
        - proposal.failure_weight * int(outcome.action_failed)
        - proposal.action_cost * int(action != "noop")
    )


def masked_probabilities(theta: np.ndarray, case: Case) -> np.ndarray:
    logits = theta @ np.asarray(case.features)
    logits = np.where(case.valid_actions, logits, -np.inf)
    finite = np.isfinite(logits)
    probabilities = np.zeros(len(ACTIONS))
    shifted = np.exp(np.clip(logits[finite] - max(logits[finite]), -50, 0))
    probabilities[finite] = shifted / shifted.sum()
    return probabilities


def train(
    cases: tuple[Case, ...],
    proposal: RewardProposal,
    training_seed: int,
    epochs: int,
    learning_rate: float,
    baseline_decay: float,
) -> np.ndarray:
    if not cases or any(case.split != "train" for case in cases):
        raise ValueError("training requires train split only")
    theta = np.zeros((len(ACTIONS), len(cases[0].features)), dtype=float)
    rng = np.random.default_rng(training_seed)
    baseline = 0.0
    for _ in range(epochs):
        for index in rng.permutation(len(cases)):
            case = cases[int(index)]
            if not case.valid_actions[1]:
                continue
            probabilities = masked_probabilities(theta, case)
            chosen = int(rng.choice(len(ACTIONS), p=probabilities))
            observed_reward = reward(case, ACTIONS[chosen], proposal)
            advantage = observed_reward - baseline
            baseline = baseline_decay * baseline + (1 - baseline_decay) * observed_reward
            gradient = -probabilities
            gradient[chosen] += 1.0
            theta += learning_rate * advantage * gradient[:, None] * np.asarray(case.features)[None, :]
            np.clip(theta, -10, 10, out=theta)
    return theta


def policy_action(theta: np.ndarray, case: Case) -> str:
    return ACTIONS[int(np.argmax(masked_probabilities(theta, case)))]


def evaluate(
    cases: tuple[Case, ...], chooser: Callable[[Case], str]
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if not cases:
        raise ValueError("empty evaluation split")
    rows = []
    for case in cases:
        action = chooser(case)
        if action not in ACTIONS or not case.valid_actions[ACTIONS.index(action)]:
            raise ValueError("policy selected a masked action")
        outcome = case.outcomes[action]
        rows.append(
            {
                "episode_id": case.episode_id,
                "family": case.family,
                "seed": case.seed,
                "action": action,
                "post_sla": outcome.post_sla,
                "post_p95_ms": outcome.post_p95_ms,
                "action_failed": outcome.action_failed,
            }
        )
    frame = pd.DataFrame(rows)
    by_family = {
        family: {
            "n": len(group),
            "simulated_slo_rate": float(group["post_sla"].mean()),
            "action_rate": float((group["action"] != "noop").mean()),
        }
        for family, group in frame.groupby("family", sort=True)
    }
    return (
        {
            "n": len(frame),
            "simulated_slo_rate": float(frame["post_sla"].mean()),
            "action_rate": float((frame["action"] != "noop").mean()),
            "mean_simulated_post_p95_ms": float(frame["post_p95_ms"].mean()),
            "failed_action_rate": float(frame["action_failed"].mean()),
            "by_family": by_family,
        },
        tuple(rows),
    )


def noop(case: Case) -> str:
    return "noop"


def sla_threshold(case: Case) -> str:
    return "scale_out" if case.valid_actions[1] and case.headroom_ms < 70 else "noop"


def jointsla_gate(case: Case) -> str:
    return "scale_out" if case.valid_actions[1] else "noop"


def paired_seed_interval(
    policy_rows: list[tuple[dict[str, Any], ...]],
    baseline_rows: tuple[dict[str, Any], ...],
    draws: int,
    seed: int,
) -> tuple[float, float]:
    baseline = {(row["seed"], row["family"]): row["post_sla"] for row in baseline_rows}
    diffs: dict[int, list[float]] = {}
    for rows in policy_rows:
        for row in rows:
            key = (row["seed"], row["family"])
            diffs.setdefault(row["seed"], []).append(row["post_sla"] - baseline[key])
    seed_values = np.asarray([np.mean(diffs[item]) for item in sorted(diffs)])
    rng = np.random.default_rng(seed)
    samples = rng.choice(seed_values, size=(draws, len(seed_values)), replace=True).mean(axis=1)
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def run_experiment(dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    plan = split_plan()
    for split in ("train", "validation", "test"):
        expected = plan[f"{split}_seeds"]
        if protocol[f"{split}_seeds"] != [min(expected), max(expected)]:
            raise RuntimeError("Phase 7 split protocol mismatch")
    cases, dataset_manifest = load_cases(dataset_dir)
    partitions = {
        name: tuple(case for case in cases if case.split == name) for name in ("train", "validation", "test")
    }
    if [len(partitions[name]) for name in ("train", "validation", "test")] != [300, 100, 100]:
        raise RuntimeError("unexpected split sizes")
    proposals = [RewardProposal.model_validate(item) for item in protocol["reward_proposals"]]
    if len({item.id for item in proposals}) != len(proposals):
        raise ValueError("duplicate reward proposal")
    baselines = {"noop": noop, "sla_threshold_70ms": sla_threshold, "jointsla_gate": jointsla_gate}
    validation_baselines = {
        name: evaluate(partitions["validation"], chooser)[0] for name, chooser in baselines.items()
    }
    reflections = []
    trained: dict[str, list[np.ndarray]] = {}
    validation_scores: dict[str, dict[str, Any]] = {}
    for proposal in proposals:
        models = [
            train(
                partitions["train"],
                proposal,
                int(seed),
                int(protocol["epochs"]),
                float(protocol["learning_rate"]),
                float(protocol["reward_baseline_decay"]),
            )
            for seed in protocol["policy_training_seeds"]
        ]
        trained[proposal.id] = models
        scores = [evaluate(partitions["validation"], partial(policy_action, theta))[0] for theta in models]
        summary = {
            "mean_simulated_slo_rate": float(np.mean([item["simulated_slo_rate"] for item in scores])),
            "mean_action_rate": float(np.mean([item["action_rate"] for item in scores])),
            "per_training_seed": dict(zip(protocol["policy_training_seeds"], scores, strict=True)),
        }
        validation_scores[proposal.id] = summary
        reflections.append(
            {
                "proposal_id": proposal.id,
                "source": proposal.source,
                "validation": summary,
                "outcome": (
                    "NO_SLO_GAIN_OVER_JOINTSLA"
                    if summary["mean_simulated_slo_rate"]
                    <= validation_baselines["jointsla_gate"]["simulated_slo_rate"]
                    else "SIMULATED_VALIDATION_SLO_GAIN"
                ),
            }
        )
    chosen = min(
        proposals,
        key=lambda item: (
            -float(validation_scores[item.id]["mean_simulated_slo_rate"]),
            float(validation_scores[item.id]["mean_action_rate"]),
            item.id,
        ),
    )
    test_baselines = {name: evaluate(partitions["test"], chooser) for name, chooser in baselines.items()}
    test_policies = [
        evaluate(partitions["test"], partial(policy_action, theta)) for theta in trained[chosen.id]
    ]
    test_slo = float(np.mean([item[0]["simulated_slo_rate"] for item in test_policies]))
    test_action = float(np.mean([item[0]["action_rate"] for item in test_policies]))
    joint_slo = test_baselines["jointsla_gate"][0]["simulated_slo_rate"]
    joint_action = test_baselines["jointsla_gate"][0]["action_rate"]
    interval = paired_seed_interval(
        [item[1] for item in test_policies],
        test_baselines["jointsla_gate"][1],
        int(protocol["bootstrap"]["draws"]),
        int(protocol["bootstrap"]["seed"]),
    )
    review_eligible = interval[0] >= 0 and test_action <= joint_action
    policy_rows = [item[1] for item in test_policies]
    decisions_hash = hashlib.sha256(_json_bytes(policy_rows)).hexdigest()
    metrics = {
        "protocol_version": protocol["protocol_version"],
        "evidence": "SIMULATION_ONLY",
        "algorithm": protocol["algorithm"],
        "chosen_proposal": chosen.id,
        "selection_split": "validation",
        "test_seed_range": protocol["test_seeds"],
        "policy_training_seeds": protocol["policy_training_seeds"],
        "validation_baselines": validation_baselines,
        "validation_proposals": validation_scores,
        "test_baselines": {name: value[0] for name, value in test_baselines.items()},
        "test_policy_per_training_seed": dict(
            zip(protocol["policy_training_seeds"], (item[0] for item in test_policies), strict=True)
        ),
        "test_policy_mean_simulated_slo_rate": test_slo,
        "test_policy_mean_action_rate": test_action,
        "test_slo_delta_vs_jointsla": test_slo - joint_slo,
        "paired_seed_bootstrap_95pct_slo_delta": interval,
        "test_action_delta_vs_jointsla": test_action - joint_action,
        "test_decisions_sha256": decisions_hash,
        "promotion": {
            "status": "OFFLINE_REVIEW_CANDIDATE" if review_eligible else "REJECTED_OFFLINE",
            "automatic_runtime_promotion": False,
            "requires_manual_review": True,
            "reason": "paired SLO lower bound and action-rate gate"
            if review_eligible
            else "offline evidence gate not met",
        },
        "limitations": [
            "one-step contextual bandit, not PPO or multi-step RL",
            "full synthetic counterfactual outcomes, not logged real-world propensities",
            "Phase 2 test seeds reused; no fresh independent holdout",
            "no hardware or Kubernetes outcome validation",
        ],
    }
    model_artifact = {
        "proposal": chosen.model_dump(),
        "feature_names": protocol["features"],
        "actions": ACTIONS,
        "policy_training_seeds": protocol["policy_training_seeds"],
        "weights": [theta.tolist() for theta in trained[chosen.id]],
        "stage": metrics["promotion"]["status"],
        "runtime_enabled": False,
    }
    reflection = {
        "source": "OFFLINE_FIXTURE",
        "iterations": reflections,
        "selected_on": "validation_only",
        "selected_proposal": chosen.id,
    }
    files = {
        "metrics.json": _json_bytes(metrics),
        "models.json": _json_bytes(model_artifact),
        "reflection.json": _json_bytes(reflection),
    }
    source_paths = {
        "phase7_trainer": Path(__file__),
        "phase7_protocol": PROTOCOL,
        "phase2_dataset_manifest": dataset_dir / "dataset_manifest.json",
        "phase2_split_plan": ROOT / "docs" / "PHASE2_SPLITS.json",
        "decision_gate": ROOT / "sovereign_maas" / "decision.py",
        "simulator": ROOT / "sovereign_maas" / "simulation.py",
        "jointsla_adapter": ROOT / "prototype" / "controller.py",
    }
    manifest = {
        "protocol_version": protocol["protocol_version"],
        "evidence": "SIMULATION_ONLY",
        "dataset_files": dataset_manifest["files"],
        "source_sha256": {name: sha256(path) for name, path in source_paths.items()},
        "output_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    files["manifest.json"] = _json_bytes(manifest)
    if output_dir.exists() and any(output_dir.iterdir()):
        if {path.name for path in output_dir.iterdir()} != set(files):
            raise FileExistsError("existing Phase 7 output differs; refusing overwrite")
        for name, content in files.items():
            if (output_dir / name).read_bytes() != content:
                raise FileExistsError(f"existing Phase 7 output differs: {name}")
        return metrics
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output_dir / name).write_bytes(content)
    return metrics


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Offline masked bandit experiment on frozen simulation data")
    parser.add_argument("--dataset", type=Path, default=ROOT / "results" / "phase2-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "phase7-v1")
    args = parser.parse_args()
    metrics = run_experiment(args.dataset, args.output)
    print(
        json.dumps(
            {
                "chosen_proposal": metrics["chosen_proposal"],
                "promotion": metrics["promotion"],
                "test_slo_delta_vs_jointsla": metrics["test_slo_delta_vs_jointsla"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
