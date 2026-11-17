"""Prospective, simulation-only evaluation of frozen Phase 7 policy weights."""

import hashlib
import json
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from .research_data import after_action, episode, sha256, split_plan
from .research_phase7 import (
    ACTIONS,
    ROOT,
    Case,
    Outcome,
    current_state_mask,
    evaluate,
    features,
    jointsla_gate,
    noop,
    paired_seed_interval,
    policy_action,
    sla_threshold,
)

PROTOCOL = ROOT / "docs" / "PHASE7_FRESH_PROTOCOL.json"
MODEL = ROOT / "results" / "phase7-v1" / "models.json"
PHASE7_MANIFEST = ROOT / "results" / "phase7-v1" / "manifest.json"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def fresh_cases(protocol: dict[str, Any]) -> dict[str, tuple[Case, ...]]:
    """Create fresh seeds and explicit arrival pressure from the frozen simulator."""
    split = split_plan()
    seeds = range(protocol["seed_range_inclusive"][0], protocol["seed_range_inclusive"][1] + 1)
    prior = set(split["train_seeds"] + split["validation_seeds"] + split["test_seeds"])
    if set(seeds) & prior or len(seeds) != 20 or min(seeds) < 100:
        raise ValueError("fresh seeds must be twenty unused seeds at or above 100")
    if protocol["scenario_families"] != split["scenario_families"]:
        raise ValueError("scenario family drift")
    if protocol["horizon_s"] != split["horizon_s"]:
        raise ValueError("simulation horizon drift")
    if protocol["arrival_pressure_factors"] != [1.0, 1.2, 1.5]:
        raise ValueError("pressure protocol drift")
    result: dict[str, list[Case]] = {str(factor): [] for factor in protocol["arrival_pressure_factors"]}
    for seed in seeds:
        for family in protocol["scenario_families"]:
            row, actions = episode(family, seed, "fresh_test", protocol["horizon_s"])
            for factor in protocol["arrival_pressure_factors"]:
                current = dict(row)
                current["arrival_rps"] = row["arrival_rps"] * factor
                snapshot = SimpleNamespace(**current)
                outcomes: dict[str, Outcome] = {}
                for action in actions:
                    kind = action["action_kind"]
                    post = after_action(
                        family,
                        row["queue_depth"],
                        current["arrival_rps"],
                        row["cycle_ms"],
                        row["network_ms"],
                        kind,
                        action["ttr_s"],
                        action["action_failed"],
                    )
                    if factor == 1.0 and post != action["post_p95_ms"]:
                        raise RuntimeError("baseline simulator replay changed")
                    outcomes[kind] = Outcome(
                        post_sla=int(post <= row["slo_ms"]),
                        post_p95_ms=post,
                        ttr_s=action["ttr_s"],
                        action_failed=action["action_failed"],
                    )
                result[str(factor)].append(
                    Case(
                        episode_id=f"{row['episode_id']}-pressure-{factor}",
                        family=family,
                        seed=seed,
                        split="fresh_test",
                        features=features(snapshot),
                        valid_actions=current_state_mask(snapshot),
                        headroom_ms=row["headroom_ms"],
                        slo_ms=row["slo_ms"],
                        outcomes=outcomes,
                    )
                )
    return {factor: tuple(cases) for factor, cases in result.items()}


def run_evaluation(output_dir: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if sha256(MODEL) != protocol["frozen_model_sha256"]:
        raise RuntimeError("frozen Phase 7 model hash mismatch")
    if sha256(PHASE7_MANIFEST) != protocol["frozen_phase7_manifest_sha256"]:
        raise RuntimeError("frozen Phase 7 manifest hash mismatch")
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    if model["runtime_enabled"] or tuple(model["actions"]) != ACTIONS:
        raise RuntimeError("unexpected frozen model configuration")
    weights = [np.asarray(item, dtype=float) for item in model["weights"]]
    if len(weights) != 5 or any(theta.shape != (2, 7) or not np.isfinite(theta).all() for theta in weights):
        raise RuntimeError("unexpected frozen model weights")
    cases_by_pressure = fresh_cases(protocol)
    pressure_metrics: dict[str, Any] = {}
    decision_rows: dict[str, Any] = {}
    gates = []
    for index, (pressure, cases) in enumerate(cases_by_pressure.items()):
        if len(cases) != 100:
            raise RuntimeError("fresh case count changed")
        baselines = {
            "noop": evaluate(cases, noop),
            "sla_threshold_70ms": evaluate(cases, sla_threshold),
            "jointsla_gate": evaluate(cases, jointsla_gate),
        }
        policies = [evaluate(cases, partial(policy_action, theta)) for theta in weights]
        slo_rate = float(np.mean([item[0]["simulated_slo_rate"] for item in policies]))
        action_rate = float(np.mean([item[0]["action_rate"] for item in policies]))
        baseline_slo = baselines["jointsla_gate"][0]["simulated_slo_rate"]
        baseline_action = baselines["jointsla_gate"][0]["action_rate"]
        interval = paired_seed_interval(
            [item[1] for item in policies],
            baselines["jointsla_gate"][1],
            protocol["bootstrap"]["draws"],
            protocol["bootstrap"]["seed"] + index,
        )
        agreement = float(
            np.mean(
                [
                    policy_row["action"] == baseline_row["action"]
                    for _, rows in policies
                    for policy_row, baseline_row in zip(rows, baselines["jointsla_gate"][1], strict=True)
                ]
            )
        )
        pressure_metrics[pressure] = {
            "n_cases": len(cases),
            "n_models": len(weights),
            "baselines": {name: result[0] for name, result in baselines.items()},
            "policy_per_training_seed": dict(
                zip(model["policy_training_seeds"], (item[0] for item in policies), strict=True)
            ),
            "policy_mean_simulated_slo_rate": slo_rate,
            "policy_mean_action_rate": action_rate,
            "slo_delta_vs_jointsla": slo_rate - baseline_slo,
            "action_delta_vs_jointsla": action_rate - baseline_action,
            "paired_seed_bootstrap_95pct_slo_delta": interval,
            "action_agreement_with_jointsla": agreement,
        }
        decision_rows[pressure] = {
            "jointsla_gate": baselines["jointsla_gate"][1],
            "policies": [item[1] for item in policies],
        }
        gates.append(interval[0] > 0 and action_rate <= baseline_action)
    metrics = {
        "protocol_version": protocol["protocol_version"],
        "evidence": "SIMULATION_ONLY",
        "fresh_seed_range": protocol["seed_range_inclusive"],
        "policy_training_seeds": model["policy_training_seeds"],
        "pressure": pressure_metrics,
        "decisions_sha256": hashlib.sha256(_json_bytes(decision_rows)).hexdigest(),
        "promotion": {
            "status": "OFFLINE_REVIEW_CANDIDATE" if all(gates) else "REJECTED_OFFLINE",
            "automatic_runtime_promotion": False,
            "manual_review_required": True,
            "reason": "all preregistered pressure gates passed"
            if all(gates)
            else "one or more preregistered pressure gates failed",
        },
        "limitations": [
            "fresh seeds are independent draws from the same frozen synthetic generator, not an external dataset",
            "pressure changes initial arrival rate only, not the physical testbed or telemetry stack",
            "one-step contextual bandit, not PPO or multi-step RL",
            "full simulated counterfactual outcomes; no hardware or Kubernetes validation",
        ],
    }
    files = {"metrics.json": _json_bytes(metrics)}
    sources = {
        "fresh_protocol": PROTOCOL,
        "frozen_model": MODEL,
        "frozen_phase7_manifest": PHASE7_MANIFEST,
        "fresh_evaluator": Path(__file__),
        "phase2_simulator": ROOT / "sovereign_maas" / "research_data.py",
        "phase7_policy": ROOT / "sovereign_maas" / "research_phase7.py",
        "decision_gate": ROOT / "sovereign_maas" / "decision.py",
    }
    manifest = {
        "protocol_version": protocol["protocol_version"],
        "evidence": "SIMULATION_ONLY",
        "source_sha256": {name: sha256(path) for name, path in sources.items()},
        "output_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    files["manifest.json"] = _json_bytes(manifest)
    if output_dir.exists() and any(output_dir.iterdir()):
        if {path.name for path in output_dir.iterdir()} != set(files):
            raise FileExistsError("existing fresh output differs; refusing overwrite")
        for name, content in files.items():
            if (output_dir / name).read_bytes() != content:
                raise FileExistsError(f"existing fresh output differs: {name}")
        return metrics
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output_dir / name).write_bytes(content)
    return metrics


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate frozen Phase 7 weights on prospective synthetic cases"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "phase7-fresh-v1")
    args = parser.parse_args()
    metrics = run_evaluation(args.output)
    print(
        json.dumps(
            {
                "promotion": metrics["promotion"],
                "pressure": {
                    name: {
                        "slo_delta": item["slo_delta_vs_jointsla"],
                        "ci": item["paired_seed_bootstrap_95pct_slo_delta"],
                    }
                    for name, item in metrics["pressure"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
