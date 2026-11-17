"""Frozen-seed, simulation-only replay data with explicit TTV censoring."""

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import pandas as pd

from .simulation import latency

SPLIT_PATH = Path(__file__).resolve().parents[1] / "docs" / "PHASE2_SPLITS.json"
VERSION = "phase2-replay-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_plan() -> dict[str, Any]:
    plan = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    sets = [set(plan[f"{name}_seeds"]) for name in ("train", "validation", "test")]
    if any(a & b for i, a in enumerate(sets) for b in sets[i + 1 :]):
        raise ValueError("seed split overlap")
    if set(plan["scenario_families"]) != {"steady", "ramp", "burst", "network", "capacity"}:
        raise ValueError("scenario family drift")
    return plan


def seeded_rng(family: str, seed: int, suffix: str = "episode") -> random.Random:
    digest = hashlib.sha256(f"{VERSION}:{family}:{seed}:{suffix}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def profile(
    family: str, tick: int, arrival: float, cycle: float, network: float
) -> tuple[float, float, float]:
    if family == "ramp":
        arrival += 1.5 * tick
    elif family == "burst" and tick >= 4:
        arrival += 13.0
    elif family == "network" and tick >= 5:
        network += 70.0
    elif family == "capacity" and tick >= 4:
        cycle *= 1.5
    return arrival, cycle, network


def after_action(
    family: str,
    queue: int,
    arrival: float,
    cycle: float,
    network: float,
    action: str,
    ttr_s: float,
    failed: bool,
) -> float:
    current_queue = float(queue)
    ready_tick = math.ceil(ttr_s)
    verification_tick = max(5, ready_tick + 1)
    observed = 0.0
    for tick in range(1, verification_tick + 1):
        rate, current_cycle, current_network = profile(family, tick, arrival, cycle, network)
        applied = action != "noop" and not failed and tick >= ready_tick
        replicas = 2 if applied and action == "scale_out" else 1
        if applied and action == "migrate":
            current_network = 80.0
        current_queue = max(0.0, current_queue + rate - replicas * 1000 / current_cycle)
        observed = latency(current_queue, replicas, current_network, current_cycle)
    return observed


def episode(family: str, seed: int, split: str, horizon: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rng = seeded_rng(family, seed)
    queue = rng.randint(0, 5)
    arrival = round(rng.uniform(43, 58), 3)
    cycle = round(rng.uniform(18, 25), 3)
    network = round(rng.uniform(8, 20), 3)
    initial_p95 = latency(queue, 1, network, cycle)
    slo = round(initial_p95 + rng.uniform(40, 100), 3)
    current_queue = float(queue)
    first_breach: int | None = None
    for tick in range(1, horizon + 1):
        rate, current_cycle, current_network = profile(family, tick, arrival, cycle, network)
        current_queue = max(0.0, current_queue + rate - 1000 / current_cycle)
        p95 = latency(current_queue, 1, current_network, current_cycle)
        if first_breach is None and p95 > slo:
            first_breach = tick
    episode_id = f"{family}-{seed:03d}"
    row = {
        "episode_id": episode_id,
        "scenario_family": family,
        "seed": seed,
        "split_group": f"seed-{seed:03d}",
        "split": split,
        "scenario_version": VERSION,
        "evidence": "SIMULATED",
        "queue_depth": queue,
        "arrival_rps": arrival,
        "cycle_ms": cycle,
        "network_ms": network,
        "slo_ms": slo,
        "observed_p95_ms": initial_p95,
        "headroom_ms": round(slo - initial_p95, 3),
        "breach_within_horizon": int(first_breach is not None),
        "ttv_observed_s": float(first_breach) if first_breach is not None else None,
        "ttv_censored": first_breach is None,
        "followup_s": float(first_breach if first_breach is not None else horizon),
    }
    actions = []
    for kind in ("scale_out", "migrate", "noop"):
        action_rng = seeded_rng(family, seed, kind)
        if kind == "scale_out":
            ttr = round(1.0 + 0.1 * queue + action_rng.uniform(0, 1.2), 3)
        elif kind == "migrate":
            ttr = round(2.0 + 0.1 * queue + action_rng.uniform(0, 1.6), 3)
        else:
            ttr = 0.0
        failed = kind != "noop" and action_rng.random() < 0.05
        post_p95 = after_action(family, queue, arrival, cycle, network, kind, ttr, failed)
        actions.append(
            {
                "episode_id": episode_id,
                "scenario_family": family,
                "seed": seed,
                "split_group": row["split_group"],
                "split": split,
                "action_kind": kind,
                "target_replicas": 2 if kind == "scale_out" else 1,
                "target_network_ms": 80.0 if kind == "migrate" else network,
                "ttr_s": ttr,
                "action_failed": failed,
                "post_p95_ms": post_p95,
                "post_sla": int(post_p95 <= slo),
                "evidence": "SIMULATED",
            }
        )
    return row, actions


def generate(output: Path) -> dict[str, Any]:
    """Create new evidence once; refuse to overwrite an existing dataset."""
    plan = split_plan()
    manifest_path = output / "dataset_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["split_sha256"] != sha256(SPLIT_PATH):
            raise RuntimeError("frozen split plan changed")
        if manifest["generator_sha256"] != sha256(Path(__file__)):
            raise RuntimeError("replay generator changed")
        for name, digest in manifest["files"].items():
            if sha256(output / name) != digest:
                raise RuntimeError(f"dataset checksum mismatch: {name}")
        return manifest
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory already contains files; refusing to overwrite")
    output.mkdir(parents=True, exist_ok=True)
    episode_rows: list[dict[str, Any]] = []
    action_rows: list[dict[str, Any]] = []
    for split in ("train", "validation", "test"):
        for seed in plan[f"{split}_seeds"]:
            for family in plan["scenario_families"]:
                row, actions = episode(family, seed, split, plan["horizon_s"])
                episode_rows.append(row)
                action_rows.extend(actions)
    pd.DataFrame(episode_rows).to_parquet(output / "episodes.parquet", index=False)
    pd.DataFrame(action_rows).to_parquet(output / "actions.parquet", index=False)
    manifest = {
        "protocol_version": VERSION,
        "data_source": "SIMULATED",
        "horizon_s": plan["horizon_s"],
        "split_sha256": sha256(SPLIT_PATH),
        "generator_sha256": sha256(Path(__file__)),
        "rows": {"episodes": len(episode_rows), "actions": len(action_rows)},
        "files": {name: sha256(output / name) for name in ("episodes.parquet", "actions.parquet")},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
