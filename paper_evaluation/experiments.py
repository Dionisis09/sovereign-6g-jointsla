"""Run the unchanged engine with one immutable workload per seed."""
from dataclasses import asdict, replace
import gzip
import importlib.metadata
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
from catalyst.reused import digest, write_gzip, write_json
from dynamic_placement.config import Config
from dynamic_placement.workload import generate_workload
from dynamic_placement.simulator import Simulator
from dynamic_placement.metrics import calculate_metrics, validate_run
from dynamic_placement.scenario_model import traffic_hash_payload
from .accounting import POLICIES, augment_metrics, validate_pairing

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SOURCES = [*(ROOT/"dynamic_placement").glob("*.py"),
                  ROOT/"placement_experiment/data_generation.py",
                  ROOT/"placement_experiment/algorithms.py", ROOT/"catalyst/reused.py"]


def engine_hashes():
    return {p.relative_to(ROOT).as_posix(): digest(p.read_text(encoding="utf-8")) for p in sorted(ENGINE_SOURCES)}


def tag(frame, seed, policy, workload_hash, traffic_hash):
    return frame.assign(seed=seed, policy=policy, workload_hash=workload_hash, traffic_hash=traffic_hash)


def run(config, seeds, output):
    """No alternate simulator, controller wrapper, or request filtering is used."""
    output.mkdir(parents=True, exist_ok=True)
    (output/"inputs").mkdir(exist_ok=True)
    write_json(output/"config.json", asdict(config))
    write_json(output/"simulation_protocol.json", dict(seeds=list(seeds), policies=list(POLICIES),
               config_hash=digest(asdict(config)), source_hashes=engine_hashes(),
               controller_inputs="existing past/current snapshot only; no future traffic",
               accounting="all offered arrival cohorts; drain after the arrival horizon"))
    rows, slot_frames, node_frames, traffic_frames, checks = [], [], [], [], []
    audits = {name: [] for name in ("actions", "reservations", "lifecycle")}
    with gzip.GzipFile(filename=str(output/"request_outcomes.csv.gz"), mode="wb", mtime=0) as stream:
        first = True
        for seed in seeds:
            workload = generate_workload(config, seed)
            fingerprint = digest(workload.to_dict())
            tape = digest(traffic_hash_payload(workload))
            write_gzip(output/"inputs"/f"seed_{seed:03d}.json.gz", workload.to_dict())
            traffic_frames.append(pd.DataFrame(workload.traffic).assign(seed=seed, traffic_hash=tape))
            for policy in POLICIES:
                result = Simulator(config, workload, policy).run()
                checks.append(dict(seed=seed, policy=policy, **validate_run(config, workload, result)))
                metrics, slots, nodes, outcomes = calculate_metrics(config, workload, result)
                m = augment_metrics(config, workload, result, metrics, outcomes, slots, nodes)
                rows.append(dict(seed=seed, policy=policy, workload_hash=fingerprint, traffic_hash=tape, **m))
                slot_frames.append(tag(slots, seed, policy, fingerprint, tape))
                node_frames.append(tag(nodes, seed, policy, fingerprint, tape))
                stream.write(tag(outcomes, seed, policy, fingerprint, tape).to_csv(index=False, header=first).encode("utf-8"))
                first = False
                for name in audits:
                    if result[name]:
                        audits[name].append(tag(pd.DataFrame(result[name]), seed, policy, fingerprint, tape))
            if digest(workload.to_dict()) != fingerprint:
                raise AssertionError("engine mutated shared workload")
            print(f"Seed {seed}: {len(workload.requests):,} common requests; four policies validated", flush=True)
    raw = pd.DataFrame(rows)
    validate_pairing(raw, seeds)
    numeric = raw.select_dtypes(include="number")
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("nonfinite main raw metric")
    raw.to_csv(output/"raw_policy_results.csv", index=False)
    for name, frames in (("slot_trajectories", slot_frames), ("node_trajectories", node_frames), ("traffic", traffic_frames)):
        pd.concat(frames, ignore_index=True).to_csv(output/f"{name}.csv", index=False)
    for name, frames in audits.items():
        filename = {"reservations": "reservation_events", "lifecycle": "lifecycle_events"}.get(name, name)
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["seed", "policy", "kind"])
        frame.to_csv(output/f"{filename}.csv", index=False)
    write_json(output/"simulation_validation.json", dict(successful_runs=len(raw), per_run_checks=checks))
    write_json(output/"environment.json", dict(python=platform.python_version(), platform=platform.platform(),
               packages={p: importlib.metadata.version(p) for p in ("numpy", "pandas", "matplotlib", "simpy", "scipy")}))
    return raw


def load_or_run(config, seeds, output, reuse=False, force=False):
    """Default preserves outputs; reuse checks engine/config/seeds before analysis."""
    file = output/"raw_policy_results.csv"
    if force and reuse:
        raise ValueError("--force and --reuse-results are mutually exclusive")
    if file.exists() and not force:
        if not reuse:
            raise ValueError("outputs exist: specify --reuse-results or --force")
        protocol = json.loads((output/"simulation_protocol.json").read_text(encoding="utf-8"))
        if protocol["seeds"] != list(seeds) or protocol["config_hash"] != digest(asdict(config)) or protocol["source_hashes"] != engine_hashes():
            raise ValueError("reuse refused: seeds, config or engine source changed")
        raw = pd.read_csv(file)
        validate_pairing(raw, seeds)
        return raw
    if reuse:
        raise ValueError("--reuse-results requires a complete existing raw experiment")
    return run(config, seeds, output)
