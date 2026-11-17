"""Frozen-evidence integrity checks without loading API native dependencies."""

import shutil

import pytest

from sovereign_maas.evidence import ROOT, EvidenceError, verify_repository


def test_committed_evidence_lineage_is_intact() -> None:
    checked = verify_repository()
    assert sum(checked.values()) == 40
    assert checked["fresh_outputs"] == 1
    assert checked["sequence_outputs"] == 3


def test_evidence_gate_rejects_changed_frozen_output(tmp_path) -> None:
    for name in ("phase2-v1", "phase4-v1", "phase7-v1", "phase7-fresh-v1", "phase7-sequence-v1"):
        shutil.copytree(ROOT / "results" / name, tmp_path / "results" / name)
    sources = (
        "docs/PHASE2_SPLITS.json",
        "docs/PHASE7_PROTOCOL.json",
        "docs/PHASE7_FRESH_PROTOCOL.json",
        "docs/PHASE7_SEQUENCE_PROTOCOL.json",
        "prototype/controller.py",
        "sovereign_maas/research_data.py",
        "sovereign_maas/research_models.py",
        "sovereign_maas/research_phase4.py",
        "sovereign_maas/research_phase7.py",
        "sovereign_maas/research_phase7_fresh.py",
        "sovereign_maas/research_phase7_sequence.py",
        "sovereign_maas/judgment.py",
        "sovereign_maas/decision.py",
        "sovereign_maas/simulation.py",
    )
    for relative in sources:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    assert verify_repository(tmp_path) == verify_repository()
    (tmp_path / "results/phase7-fresh-v1/metrics.json").write_text("{}", encoding="utf-8")
    with pytest.raises(EvidenceError, match="SHA-256 mismatch"):
        verify_repository(tmp_path)
