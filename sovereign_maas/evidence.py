"""Read-only integrity gate for frozen simulation evidence and its source lineage."""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class EvidenceError(RuntimeError):
    """A frozen result or a source named in its manifest has changed."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EvidenceError(f"cannot read evidence JSON: {path}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"expected JSON object: {path}")
    return value


def _expect_hash(path: Path, expected: str) -> None:
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(char not in "0123456789abcdef" for char in expected)
    ):
        raise EvidenceError(f"invalid SHA-256 digest for {path}")
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise EvidenceError(f"missing evidence file: {path}") from error
    if actual != expected:
        raise EvidenceError(f"SHA-256 mismatch: {path}")


def _check_mapping(root: Path, hashes: dict[str, str], paths: dict[str, str]) -> int:
    if set(hashes) != set(paths):
        raise EvidenceError(f"manifest keys differ: expected {sorted(paths)}, got {sorted(hashes)}")
    for name, relative in paths.items():
        _expect_hash(root / relative, hashes[name])
    return len(paths)


def verify_repository(root: Path = ROOT) -> dict[str, int]:
    """Verify frozen files and recorded source hashes without regenerating data."""
    checked: dict[str, int] = {}
    phase2 = root / "results" / "phase2-v1"
    data = _read_json(phase2 / "dataset_manifest.json")
    checked["phase2_dataset"] = _check_mapping(
        root,
        data["files"],
        {name: f"results/phase2-v1/{name}" for name in ("actions.parquet", "episodes.parquet")},
    )
    _expect_hash(root / "sovereign_maas/research_data.py", data["generator_sha256"])
    _expect_hash(root / "docs/PHASE2_SPLITS.json", data["split_sha256"])
    checked["phase2_dataset"] += 2

    model = _read_json(phase2 / "model_manifest.json")
    if model["dataset_files"] != data["files"] or model["split_sha256"] != data["split_sha256"]:
        raise EvidenceError("Phase 2 model input lineage mismatch")
    _expect_hash(phase2 / "models.json", model["model_sha256"])
    _expect_hash(root / "sovereign_maas/research_models.py", model["trainer_sha256"])
    phase2_metrics = _read_json(phase2 / "metrics.json")
    if phase2_metrics["model_sha256"] != model["model_sha256"]:
        raise EvidenceError("Phase 2 metrics/model mismatch")
    _expect_hash(root / "sovereign_maas/research_models.py", phase2_metrics["evaluator_sha256"])
    checked["phase2_model"] = 3

    phase4 = root / "results" / "phase4-v1"
    phase4_metrics = _read_json(phase4 / "metrics.json")
    if (
        phase4_metrics["dataset_files"] != data["files"]
        or phase4_metrics["model_sha256"] != model["model_sha256"]
    ):
        raise EvidenceError("Phase 4 input lineage mismatch")
    checked["phase4"] = _check_mapping(
        root,
        {
            "dataset_manifest": phase4_metrics["dataset_manifest_sha256"],
            "decisions": phase4_metrics["decisions_sha256"],
            "evaluator": phase4_metrics["evaluator_sha256"],
            "fixture": phase4_metrics["fixture_sha256"],
            "policy": phase4_metrics["policy_sha256"],
        },
        {
            "dataset_manifest": "results/phase2-v1/dataset_manifest.json",
            "decisions": "results/phase4-v1/decisions.json",
            "evaluator": "sovereign_maas/research_phase4.py",
            "fixture": "sovereign_maas/judgment.py",
            "policy": "sovereign_maas/decision.py",
        },
    )

    phase7 = root / "results" / "phase7-v1"
    phase7_manifest = _read_json(phase7 / "manifest.json")
    if phase7_manifest["dataset_files"] != data["files"]:
        raise EvidenceError("Phase 7 dataset lineage mismatch")
    checked["phase7_outputs"] = _check_mapping(
        root,
        phase7_manifest["output_sha256"],
        {name: f"results/phase7-v1/{name}" for name in ("metrics.json", "models.json", "reflection.json")},
    )
    checked["phase7_sources"] = _check_mapping(
        root,
        phase7_manifest["source_sha256"],
        {
            "phase7_trainer": "sovereign_maas/research_phase7.py",
            "phase7_protocol": "docs/PHASE7_PROTOCOL.json",
            "phase2_dataset_manifest": "results/phase2-v1/dataset_manifest.json",
            "phase2_split_plan": "docs/PHASE2_SPLITS.json",
            "decision_gate": "sovereign_maas/decision.py",
            "simulator": "sovereign_maas/simulation.py",
            "jointsla_adapter": "prototype/controller.py",
        },
    )

    fresh = root / "results" / "phase7-fresh-v1"
    fresh_manifest = _read_json(fresh / "manifest.json")
    fresh_protocol = _read_json(root / "docs" / "PHASE7_FRESH_PROTOCOL.json")
    if fresh_protocol["frozen_model_sha256"] != phase7_manifest["output_sha256"]["models.json"]:
        raise EvidenceError("fresh protocol model hash differs from Phase 7 manifest")
    if not fresh_protocol["registered_before_outcome_generation"]:
        raise EvidenceError("fresh protocol registration flag missing")
    checked["fresh_outputs"] = _check_mapping(
        root, fresh_manifest["output_sha256"], {"metrics.json": "results/phase7-fresh-v1/metrics.json"}
    )
    checked["fresh_sources"] = _check_mapping(
        root,
        fresh_manifest["source_sha256"],
        {
            "fresh_protocol": "docs/PHASE7_FRESH_PROTOCOL.json",
            "frozen_model": "results/phase7-v1/models.json",
            "frozen_phase7_manifest": "results/phase7-v1/manifest.json",
            "fresh_evaluator": "sovereign_maas/research_phase7_fresh.py",
            "phase2_simulator": "sovereign_maas/research_data.py",
            "phase7_policy": "sovereign_maas/research_phase7.py",
            "decision_gate": "sovereign_maas/decision.py",
        },
    )
    _expect_hash(phase7 / "manifest.json", fresh_protocol["frozen_phase7_manifest_sha256"])
    checked["fresh_sources"] += 1

    sequence = root / "results" / "phase7-sequence-v1"
    sequence_manifest = _read_json(sequence / "manifest.json")
    if sequence_manifest["protocol_version"] != "phase7-sequence-v1":
        raise EvidenceError("unexpected sequential protocol version")
    checked["sequence_outputs"] = _check_mapping(
        root,
        sequence_manifest["output_sha256"],
        {
            name: f"results/phase7-sequence-v1/{name}"
            for name in ("models.json", "metrics.json", "episodes.jsonl")
        },
    )
    checked["sequence_sources"] = _check_mapping(
        root,
        sequence_manifest["source_sha256"],
        {
            name: name
            for name in (
                "docs/PHASE7_SEQUENCE_PROTOCOL.json",
                "sovereign_maas/research_phase7_sequence.py",
                "sovereign_maas/research_data.py",
                "sovereign_maas/research_phase7.py",
                "sovereign_maas/decision.py",
                "sovereign_maas/simulation.py",
            )
        },
    )
    return checked


def main() -> None:
    print(json.dumps({"status": "PASS", "checked": verify_repository()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
