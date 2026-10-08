"""Run 30 paired Monte Carlo seeds; export evidence, summaries and figures."""
import argparse
from dataclasses import asdict
import gzip
import importlib.metadata
from pathlib import Path
import platform
from time import perf_counter
import pandas as pd
from catalyst.reused import digest, write_gzip, write_json
from .config import Config
from .workload import generate_workload
from .simulator import Simulator
from .policies import POLICIES
from .metrics import calculate_metrics, validate_run
from .plotting import create_plots


def _tag(frame, seed, policy, workload_hash):
    frame.insert(0, "workload_hash", workload_hash)
    frame.insert(0, "policy", policy)
    frame.insert(0, "seed", seed)
    return frame


def run_experiment(config, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "inputs").mkdir(exist_ok=True)
    # Record parameters and code before any measured runs.
    sources = [*Path("dynamic_placement").glob("*.py"), Path("placement_experiment/data_generation.py"),
               Path("placement_experiment/algorithms.py"), Path("catalyst/reused.py")]
    source_hashes = {str(p): digest(p.read_text(encoding="utf-8")) for p in sorted(sources)}
    write_json(output / "config.json", asdict(config))
    write_json(output / "protocol.json", dict(config_hash=digest(asdict(config)), source_hashes=source_hashes,
                                               decisions_use="previous-slot arrivals, queues, completions and utilization only",
                                               initial_placement="same greedy placement on declared mean demands",
                                               trials="consecutive fixed seeds; no scenario resampling or weight tuning"))
    rows, slot_frames, node_frames, traffic_frames = [], [], [], []
    action_frames, reservation_frames, lifecycle_frames, validation = [], [], [], []
    started = perf_counter()
    with gzip.GzipFile(filename=str(output / "request_outcomes.csv.gz"), mode="wb", mtime=0) as request_file:
        header = True
        for seed in range(config.first_seed, config.first_seed + config.trials):
            workload = generate_workload(config, seed)
            encoded = workload.to_dict()
            workload_hash = digest(encoded)
            write_gzip(output / "inputs" / f"seed_{seed:03d}.json.gz", encoded)
            traffic = pd.DataFrame(workload.traffic)
            traffic.insert(0, "seed", seed)
            traffic_frames.append(traffic)
            for policy in POLICIES:
                result = Simulator(config, workload, policy).run()
                checks = validate_run(config, workload, result)
                validation.append(dict(seed=seed, policy=policy, **checks))
                metrics, slots, nodes, outcomes = calculate_metrics(config, workload, result)
                rows.append(dict(seed=seed, policy=policy, workload_hash=workload_hash, **metrics))
                slot_frames.append(_tag(slots, seed, policy, workload_hash))
                node_frames.append(_tag(nodes, seed, policy, workload_hash))
                request_file.write(_tag(outcomes, seed, policy, workload_hash).to_csv(index=False, header=header).encode("utf-8"))
                header = False
                for key, store in (("actions", action_frames), ("reservations", reservation_frames), ("lifecycle", lifecycle_frames)):
                    if result[key]:
                        store.append(_tag(pd.DataFrame(result[key]), seed, policy, workload_hash))
            print(f"Seed {seed}: {len(workload.requests):,} paired requests, four policies validated", flush=True)
    frame, slots, nodes = pd.DataFrame(rows), pd.concat(slot_frames, ignore_index=True), pd.concat(node_frames, ignore_index=True)
    frame.to_csv(output / "runs.csv", index=False)
    slots.to_csv(output / "slot_trajectories.csv", index=False)
    nodes.to_csv(output / "node_trajectories.csv", index=False)
    pd.concat(traffic_frames, ignore_index=True).to_csv(output / "traffic.csv", index=False)
    for name, frames in (("actions", action_frames), ("reservation_events", reservation_frames), ("lifecycle_events", lifecycle_frames)):
        (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["seed", "policy"])).to_csv(output / f"{name}.csv", index=False)
    names = [c for c in frame if c not in ("seed", "policy", "workload_hash")]
    summary = frame.groupby("policy", sort=False)[names].agg(["mean", "std", "count"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    summary.to_csv(output / "summary.csv")
    # Paired differences are descriptive sample variation, not a significance test.
    paired = []
    for baseline in ("static", "reactive", "periodic"):
        for metric in ("average_latency_ms", "time_average_slot_latency_ms", "sla_breach_pct", "total_actions", "replica_seconds"):
            pivot = frame.pivot(index="seed", columns="policy", values=metric)
            delta = pivot.sla_aware - pivot[baseline]
            paired.append(dict(baseline=baseline, metric=metric, proposed_minus_baseline_mean=float(delta.mean()),
                               paired_difference_std=float(delta.std()), seeds=len(delta)))
    pd.DataFrame(paired).to_csv(output / "paired_differences.csv", index=False)
    write_json(output / "environment.json", dict(python=platform.python_version(), platform=platform.platform(),
                packages={p: importlib.metadata.version(p) for p in ("numpy", "pandas", "matplotlib", "simpy")},
                std="sample standard deviation across seeds, ddof=1; seeds are the statistical units",
                runtime="each policy decision plus action validation/application; excludes snapshot construction, request events and exports"))
    assert frame.groupby("seed").workload_hash.nunique().eq(1).all()
    assert frame.groupby("seed").requests.nunique().eq(1).all()
    assert slots.groupby(["seed", "policy"]).size().eq(config.slots).all()
    write_json(output / "verification.json", dict(runs=len(rows), paired_seeds=config.trials,
                per_run_checks=validation, source_hashes=source_hashes,
                all_policies_share_input_hash_and_request_count=True,
                all_requests_complete_or_are_explicitly_unplaced=True,
                trial_metrics_finite=bool(frame[names].notna().all().all())))
    create_plots(slots, nodes, config, output)
    columns = [("time_average_slot_latency_ms", "Time-avg latency, ms"), ("average_latency_ms", "Request-avg latency, ms"),
               ("sla_breach_pct", "SLA breaches, %"),
               ("total_actions", "Actions"), ("migrations", "Migrations"),
               ("replica_seconds", "Replica seconds"), ("decision_runtime_mean_ms", "Decision time, ms")]
    lines = ["# Dynamic placement results", "", f"{config.trials} paired seeds × {config.slots} slots × four policies.", "",
             "Mean ± sample SD across seeds. Time-averaged latency gives each nonempty arrival slot equal weight; request-averaged latency gives each completed request equal weight. Both include late completions. SLA includes every offered request; admission failures have no finite latency.", "",
             "| Policy | " + " | ".join(label for _, label in columns) + " |",
             "|---|" + "---:|" * len(columns)]
    for policy, row in summary.iterrows():
        lines.append("| " + " | ".join([policy, *[f"{row[f'{m}_mean']:.3f} ± {row[f'{m}_std']:.3f}" for m, _ in columns]]) + " |")
    lines += ["", "The three baseline definitions and proposed risk score are fixed in the package README. "
              "Actual CPU/GPU/link busy utilization is capacity bounded. Offered-load ratios above one measure "
              "nominal incoming demand pressure, not physical overbooking. Both are exported per node and slot.", "",
              "Scale-out uses additional replicas and VRAM under the same node budgets. Replica seconds and "
              "VRAM GB-seconds disclose this cost. The periodic policy only migrates; it does not add capacity. "
              "A node threshold can miss a service queue bottleneck when that service is waiting on its serial pipeline. "
              "These synthetic results are not a reproduction of published DRL performance percentages.", "",
              "Full metrics (including per-tier breaches, CPU/GPU profiles, queue delays, offered overload, "
              "scale-up/down counts and runtime) are in `summary.csv`; per-seed evidence is in `runs.csv`."]
    (output / "results_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines[4:12]))
    print(f"Saved {len(rows)} runs to {output.resolve()} in {perf_counter()-started:.1f} s")
    return frame, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--output", type=Path, default=Path("results/dynamic"))
    parser.add_argument("--trials", type=int)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    values = asdict(Config.load(args.config))
    if args.trials is not None:
        values["trials"] = args.trials
    if args.seed is not None:
        values["first_seed"] = args.seed
    run_experiment(Config(**values), args.output)


if __name__ == "__main__":
    main()
