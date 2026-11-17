"""Matched synthetic comparison of classic ML and a clearly labeled judgment fixture."""

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .decision import decide, propose
from .domain import ActionKind, ServiceBundle, TelemetrySnapshot, TopologyNode, TypedIntent
from .judgment import FixtureJudgmentProvider
from .research_data import sha256
from .research_models import TrainedForecastProvider, load_frames

VERSION = "phase4-fixture-comparison-v1"


def _paired_interval(rows: list[dict[str, float]], field: str, seed: int = 4704) -> list[float]:
    """Bootstrap grouped seeds; each seed contributes its five family episodes."""
    by_seed: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        by_seed[int(row["seed"])].append(row[field])
    seeds = sorted(by_seed)
    rng = random.Random(seed)
    draws = []
    for _ in range(1000):
        sample = [rng.choice(seeds) for _ in seeds]
        draws.append(sum(sum(by_seed[item]) for item in sample) / sum(len(by_seed[item]) for item in sample))
    return [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))]


def evaluate(model_dir: Path, output: Path) -> dict[str, Any]:
    episodes, actions, dataset_manifest = load_frames(model_dir)
    provider = TrainedForecastProvider(model_dir)
    fixture = FixtureJudgmentProvider()
    test_ep = episodes[episodes["split"] == "test"]
    test_actions = actions[actions["split"] == "test"]
    if len(test_ep) != 100 or len(test_actions) != 300:
        raise RuntimeError("unexpected Phase 2 held-out row count")
    outcomes = {
        (str(row.episode_id), str(row.action_kind)): int(row.post_sla)
        for row in test_actions.itertuples(index=False)
    }
    rows: list[dict[str, float]] = []
    decisions: list[dict[str, Any]] = []
    for row in test_ep.itertuples(index=False):
        service = ServiceBundle(
            tenant_id="research",
            intent=TypedIntent(
                service_name=f"service-{row.seed}",
                tier="Gold",
                latency_p95_ms=row.slo_ms,
                minimum_model_quality=0.9,
                max_replicas=2,
                allowed_regions=("eu-gr", "eu-de"),
                allowed_actions=(ActionKind.SCALE_OUT, ActionKind.MIGRATE),
            ),
        )
        snapshot = TelemetrySnapshot(
            seed=row.seed,
            queue_depth=row.queue_depth,
            arrival_rps=row.arrival_rps,
            cycle_ms=row.cycle_ms,
            observed_p95_ms=row.observed_p95_ms,
            nodes=(
                TopologyNode(id="edge-a", region="eu-gr", network_ms=row.network_ms, replica_capacity=4),
                TopologyNode(id="cloud-a", region="eu-de", network_ms=80, replica_capacity=2),
            ),
        )
        candidates = propose(service, snapshot)
        forecast = provider.predict(service, snapshot, candidates)
        classic = decide(service, snapshot, candidates, forecast=forecast)
        proxy = fixture.judge(service, snapshot, candidates)
        # No calibrated q10 TTV or action q90 TTR comes from a fixture. The only
        # safe fixture-only action under the Phase 2 trained-prediction gate is no-op.
        fixture_action = "noop"
        chosen = next(item for item in candidates if item.id == classic.selected_candidate_id)
        label = int(row.breach_within_horizon)
        ml_warning = forecast.breach_probability_12s
        fixture_warning = proxy.breach_probability_12s
        assert fixture_warning is not None
        review = int(
            (proxy.review_probability or 0) >= 0.5
            or min(proxy.incident_confidence or 0, proxy.urgency_confidence or 0, proxy.ttv_confidence or 0)
            < 0.6
        )
        rows.append(
            {
                "seed": float(row.seed),
                "ml_brier": (ml_warning - label) ** 2,
                "fixture_brier": (fixture_warning - label) ** 2,
                "brier_delta_fixture_minus_ml": (fixture_warning - label) ** 2 - (ml_warning - label) ** 2,
                "classic_slo": float(outcomes[(row.episode_id, chosen.kind.value)]),
                "fixture_slo": float(outcomes[(row.episode_id, fixture_action)]),
                "slo_delta_fixture_minus_classic": float(
                    outcomes[(row.episode_id, fixture_action)] - outcomes[(row.episode_id, chosen.kind.value)]
                ),
                "review": float(review),
            }
        )
        decisions.append(
            {
                "episode_id": row.episode_id,
                "seed": int(row.seed),
                "classic_action": chosen.kind.value,
                "fixture_only_action": fixture_action,
                "hybrid_action": chosen.kind.value,
            }
        )
    n = len(rows)
    decisions_text = json.dumps(decisions, indent=2, sort_keys=True) + "\n"
    metrics: dict[str, Any] = {
        "protocol_version": VERSION,
        "evidence": "SIMULATION_ONLY_FIXTURE_PROXY_NOT_JEV",
        "model_sha256": provider.manifest["model_sha256"],
        "dataset_manifest_sha256": sha256(model_dir / "dataset_manifest.json"),
        "dataset_files": dataset_manifest["files"],
        "evaluator_sha256": sha256(Path(__file__)),
        "fixture_sha256": sha256(Path(__file__).with_name("judgment.py")),
        "policy_sha256": sha256(Path(__file__).with_name("decision.py")),
        "decisions_sha256": hashlib.sha256(decisions_text.encode()).hexdigest(),
        "test_seed_range": [80, 99],
        "n_episodes": n,
        "classic_ml": {
            "breach_brier": sum(row["ml_brier"] for row in rows) / n,
            "selected_actions": {
                kind: sum(item["classic_action"] == kind for item in decisions)
                for kind in ("scale_out", "migrate", "noop")
            },
            "simulated_slo_rate": sum(row["classic_slo"] for row in rows) / n,
        },
        "fixture_only": {
            "breach_brier_uncalibrated_proxy": sum(row["fixture_brier"] for row in rows) / n,
            "selected_actions": {"scale_out": 0, "migrate": 0, "noop": n},
            "simulated_slo_rate": sum(row["fixture_slo"] for row in rows) / n,
            "review_rate": sum(row["review"] for row in rows) / n,
        },
        "hybrid_advisory_only": {
            "same_actions_as_classic_ml": all(
                item["classic_action"] == item["hybrid_action"] for item in decisions
            ),
            "simulated_slo_rate": sum(row["classic_slo"] for row in rows) / n,
            "review_rate": sum(row["review"] for row in rows) / n,
        },
        "paired_seed_bootstrap_95pct": {
            "fixture_minus_ml_brier": _paired_interval(rows, "brier_delta_fixture_minus_ml"),
            "fixture_minus_classic_slo_rate": _paired_interval(rows, "slo_delta_fixture_minus_classic"),
        },
        "live_jev_latency_ms": None,
        "live_jev_cost_usd": None,
        "live_jev_accuracy": None,
        "note": "The fixture is a deterministic rule proxy, not Jev output; held-out test seeds were reused from Phase 2 without threshold tuning.",
    }
    output.mkdir(parents=True, exist_ok=True)
    path = output / "metrics.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != metrics or sha256(output / "decisions.json") != metrics["decisions_sha256"]:
            raise RuntimeError("Phase 4 metrics changed; refusing overwrite")
        return existing
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "decisions.json").write_bytes(decisions_text.encode())
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4 fixture-only matched synthetic comparison")
    parser.add_argument("--models", type=Path, default=Path("results/phase2-v1"))
    parser.add_argument("--output", type=Path, default=Path("results/phase4-v1"))
    args = parser.parse_args()
    print(json.dumps(evaluate(args.models, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
