"""Independent reconstruction of saved metrics; no reruns or parameter changes."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from catalyst.reused import digest, write_json
from catalyst.scenario import load_config


def main():
    config = load_config()
    output = Path("results/phase0-v1")
    manifest = json.loads((output / "pre_run_manifest.json").read_text())
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in manifest["files"].items())
    source_checks = json.loads(Path("docs/reuse-provenance.json").read_text())
    assert all(hashlib.sha256(Path(r["source"]).read_bytes()).hexdigest() == r["sha256"] for r in source_checks)
    checked, samples_checked, requests_checked, false_blocks, audited_blocks = 0, 0, 0, 0, 0
    incomplete = []
    for case in sorted((output / "evidence").iterdir()):
        tape = json.loads(gzip.decompress((case / "workload.json.gz").read_bytes()))
        expected_ids = {r["request_id"] for r in tape["requests"]}
        assert digest(tape["requests"]) == tape["sha256"]
        for policy in ("B0", "B1", "CATALYST", "A1", "A2"):
            evidence = json.loads(gzip.decompress((case / f"{policy}.json.gz").read_bytes()))
            summary, outcomes = evidence["summary"], evidence["outcomes"]
            assert summary["tape_hash"] == tape["sha256"]
            assert summary["outcomes_hash"] == digest(outcomes)
            assert len(outcomes) == len(expected_ids) and {r["request_id"] for r in outcomes} == expected_ids
            assert summary["rejected_requests"] == 0
            completion = np.array([r["completion_s"] for r in outcomes])
            arrival = np.array([r["arrival_s"] for r in outcomes])
            latency = np.array([r["latency_ms"] for r in outcomes])
            quality = np.array([r["quality"] for r in outcomes])
            assert np.allclose(latency, 1000 * (completion - arrival))
            assert np.allclose(latency, np.array([r["network_ms"] + config.gateway_ms + r["inference_ms"] for r in outcomes]))
            assert np.isclose(summary["p99_latency_ms"], np.quantile(latency, .99))
            breached_seconds = 0.
            for sample in evidence["samples"]:
                now = sample["time_s"]
                delivered = completion <= now
                window = delivered & (completion > now - config.metric_window_s)
                overdue = np.sum((arrival < now - config.request_timeout_ms / 1000) & ~delivered)
                count = np.sum(window)
                available = float(np.sum(window & (latency <= config.request_timeout_ms)) / (count + overdue)) if count + overdue else 1.
                p99 = float(np.quantile(latency[window], .99)) if count else 0.
                minimum_quality = float(quality[window].min()) if count else 1.
                assert np.isclose(p99, sample["latency_ms"])
                assert np.isclose(available, sample["availability"])
                assert np.isclose(minimum_quality, sample["quality"])
                expected = []
                if p99 > config.intent.end_to_end_latency_ms:
                    expected.append("END_TO_END_LATENCY")
                if minimum_quality < config.intent.minimum_model_quality:
                    expected.append("MINIMUM_MODEL_QUALITY")
                if available < config.intent.service_availability:
                    expected.append("SERVICE_AVAILABILITY")
                assert sample["disruption_s"] == 0.  # Declared primary matrix uses zero outage.
                assert sample["violations"] == expected
                breached_seconds += bool(expected) * config.tick_s
                samples_checked += 1
            assert breached_seconds == summary["total_service_contract_breach_seconds"]
            assert len(evidence["samples"]) == round(config.duration_s / config.tick_s)
            audited_blocks += summary["audited_contract_blocks"]
            false_blocks += summary["false_blocks"]
            if not summary["rollout_completed"]:
                incomplete.append(dict(case=case.name, policy=policy))
            checked += 1
            requests_checked += len(outcomes)
    assert checked == 500
    result = dict(passed=True, checked_runs=checked, checked_samples=samples_checked,
                  checked_request_outcomes=requests_checked, source_and_protocol_hashes_unchanged=True,
                  previous_sources_unchanged=True, request_conservation=True,
                  independently_reconstructed_primary_metric=True, false_blocks=false_blocks,
                  audited_contract_blocks=audited_blocks, incomplete_rollouts=incomplete)
    write_json(output / "verification.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
