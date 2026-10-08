"""Three scenario families, two capacity variants, and a fresh paired baseline."""
import argparse
from dataclasses import asdict, replace
import gzip
import importlib.metadata
from pathlib import Path
import platform
import shutil
import pandas as pd
from catalyst.reused import digest, write_json, write_gzip
from .config import Config
from .workload import generate_workload
from .policies import sla_aware
from .predictive import ScenarioConfig, PredictivePrewarming
from .scenario_model import (ScenarioSimulator, extend_capacity, traffic_hash_payload,
                             validate_scenario_run, scenario_metrics)
from .scenario_plots import create_scenario_plots

CASES = ("baseline", "predictive", "capacity_6", "capacity_7", "admission")


def tagged(frame, seed, case, fingerprint, traffic_hash):
    return frame.assign(seed=seed, scenario=case, policy="sla_aware", workload_hash=fingerprint, traffic_hash=traffic_hash)


def update_original_summary(output, original):
    """Keep original four rows and original figures archived; append new cases."""
    original = Path(original)
    if not (original / "summary.csv").exists():
        raise FileNotFoundError("original dynamic summary.csv is required for the combined table")
    backup = original / "original_summary.csv"
    if not backup.exists():
        shutil.copy2(original / "summary.csv", backup)
    old = pd.read_csv(backup)
    old.insert(0, "scenario", "original")
    old.insert(2, "node_count", 5)
    new = pd.read_csv(output / "summary.csv")
    # The fresh baseline is included in the scenario output, not duplicated in the master table.
    additions = new.loc[new.scenario != "baseline"]
    pd.concat([old, additions], ignore_index=True, sort=False).to_csv(original / "summary.csv", index=False)
    archive = original / "original_figures"
    archive.mkdir(exist_ok=True)
    for stem in ("latency_over_time", "cumulative_sla_breaches", "gpu_utilization_over_time"):
        for extension in ("png", "svg"):
            name = f"{stem}.{extension}"
            if not (archive / name).exists():
                shutil.copy2(original / name, archive / name)
            shutil.copy2(output / name, original / name)


def run_scenarios(config, settings, output, original=Path("results/dynamic")):
    if config.node_count != 5:
        raise ValueError("scenario protocol requires the original five-node baseline")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "inputs").mkdir(exist_ok=True)
    sources = [*Path("dynamic_placement").glob("*.py"), Path("placement_experiment/data_generation.py"),
               Path("placement_experiment/algorithms.py"), Path("catalyst/reused.py")]
    original_summary_path = Path(original) / "original_summary.csv"
    if not original_summary_path.exists():
        original_summary_path = Path(original) / "summary.csv"
    write_json(output / "protocol.json", dict(base_config=asdict(config), scenarios=asdict(settings), cases=CASES,
                source_hashes={p.as_posix(): digest(p.read_text(encoding="utf-8")) for p in sorted(sources)},
                unchanged_sla_aware_function_hash=digest(__import__("inspect").getsource(sla_aware)),
                original_summary_hash=digest(original_summary_path.read_text(encoding="utf-8")),
                denominators="offered failure includes drops; admitted breach and per-tier drop rates separate",
                prediction="known period; phase learned from past 10-slot MA; no future arrivals",
                capacity="append independent nodes; original services, requests, links and ingress fixed",
                admission="new Bronze only; depth/budget > .8; budget=ready replicas*ceil(deadline/compute)",
                target="mean all-offered SLA failure <15%; no outcome-based parameter tuning"))
    rows, slots_all, nodes_all, traffic_all = [], [], [], []
    extras = {key: [] for key in ("actions", "reservations", "lifecycle", "forecasts", "admission")}
    checks = []
    with gzip.GzipFile(filename=str(output / "request_outcomes.csv.gz"), mode="wb", mtime=0) as stream, \
         gzip.GzipFile(filename=str(output / "admission_events.csv.gz"), mode="wb", mtime=0) as admission_stream:
        first, admission_first = True, True
        for seed in range(config.first_seed, config.first_seed+config.trials):
            base = generate_workload(config, seed)
            traffic_hash = digest(traffic_hash_payload(base))
            traffic_all.append(pd.DataFrame(base.traffic).assign(seed=seed, traffic_hash=traffic_hash))
            for case in CASES:
                count = int(case.rsplit("_", 1)[1]) if case.startswith("capacity_") else config.node_count
                workload = extend_capacity(base, count-config.node_count) if count != config.node_count else base
                assert digest(traffic_hash_payload(workload)) == traffic_hash
                fingerprint = digest(workload.to_dict())
                write_gzip(output / "inputs" / f"seed_{seed:03d}_{case}.json.gz", workload.to_dict())
                case_config = replace(config, node_count=count)
                controller = PredictivePrewarming(settings) if case == "predictive" else None
                result = ScenarioSimulator(case_config, workload, settings, controller, admission=case == "admission").run()
                check = validate_scenario_run(case_config, workload, settings, result, case == "admission")
                checks.append(dict(seed=seed, scenario=case, **check))
                metrics, slots, nodes, outcomes = scenario_metrics(case_config, workload, result, controller)
                rows.append(dict(seed=seed, scenario=case, policy="sla_aware", node_count=count,
                                 workload_hash=fingerprint, traffic_hash=traffic_hash, **metrics))
                slots_all.append(tagged(slots, seed, case, fingerprint, traffic_hash))
                nodes_all.append(tagged(nodes, seed, case, fingerprint, traffic_hash))
                stream.write(tagged(outcomes, seed, case, fingerprint, traffic_hash).to_csv(index=False, header=first).encode("utf-8"))
                first = False
                admission_stream.write(tagged(pd.DataFrame(result["admission"]), seed, case, fingerprint, traffic_hash)
                                       .to_csv(index=False, header=admission_first).encode("utf-8"))
                admission_first = False
                for key in ("actions", "reservations", "lifecycle"):
                    if result[key]:
                        extras[key].append(tagged(pd.DataFrame(result[key]), seed, case, fingerprint, traffic_hash))
                if controller:
                    extras["forecasts"].append(tagged(pd.DataFrame(controller.forecasts), seed, case, fingerprint, traffic_hash))
                    proposals = controller.prewarm_proposals
                    if proposals:
                        extras["admission"].append(tagged(pd.DataFrame(proposals), seed, case, fingerprint, traffic_hash))
            print(f"Seed {seed}: {len(base.requests):,} offered requests x 5 paired cases validated", flush=True)
    runs, slots, nodes = pd.DataFrame(rows), pd.concat(slots_all, ignore_index=True), pd.concat(nodes_all, ignore_index=True)
    runs.to_csv(output / "runs.csv", index=False)
    slots.to_csv(output / "slot_trajectories.csv", index=False)
    nodes.to_csv(output / "node_trajectories.csv", index=False)
    pd.concat(traffic_all, ignore_index=True).to_csv(output / "traffic.csv", index=False)
    for key, name in (("actions", "actions"), ("reservations", "reservation_events"), ("lifecycle", "lifecycle_events"),
                      ("forecasts", "forecast_trajectories"), ("admission", "prewarm_proposals")):
        (pd.concat(extras[key], ignore_index=True) if extras[key] else pd.DataFrame(columns=["seed", "scenario"])).to_csv(output / f"{name}.csv", index=False)
    metric_names = [c for c in runs if c not in ("seed", "scenario", "policy", "node_count", "workload_hash", "traffic_hash")]
    summary = runs.groupby(["scenario", "policy", "node_count"], sort=False)[metric_names].agg(["mean", "std", "count"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    summary.to_csv(output / "summary.csv")
    differences = []
    for case in CASES[1:]:
        for metric in ("average_latency_ms", "time_average_slot_latency_ms", "sla_breach_pct", "admitted_sla_breach_pct",
                       "drop_pct", "gold_silver_sla_breach_pct", "replica_seconds", "cold_start_count", "cold_starts_overlapping_bursts"):
            pivot = runs.pivot(index="seed", columns="scenario", values=metric)
            delta = pivot[case]-pivot.baseline
            differences.append(dict(scenario=case, metric=metric, paired_mean=float(delta.mean()), paired_std=float(delta.std()), seeds=len(delta)))
    pd.DataFrame(differences).to_csv(output / "paired_differences.csv", index=False)
    target = [{"scenario": case, "mean_offered_failure_pct": float(group.sla_breach_pct.mean()),
               "mean_admitted_breach_pct": float(group.admitted_sla_breach_pct.mean()),
               "target_met": bool(group.sla_breach_pct.mean() < settings.sla_target_pct),
               "seeds_below_target": int((group.sla_breach_pct < settings.sla_target_pct).sum())}
              for case, group in runs.groupby("scenario", sort=False)]
    write_json(output / "target_evaluation.json", dict(target_pct=settings.sla_target_pct, evaluations=target))
    write_json(output / "verification.json", dict(runs=len(runs), paired_seeds=config.trials,
               cases=CASES, per_run_checks=checks, common_traffic_hash_per_seed=bool(runs.groupby("seed").traffic_hash.nunique().eq(1).all()),
               same_offered_requests_per_seed=bool(runs.groupby("seed").requests.nunique().eq(1).all())))
    write_json(output / "environment.json", dict(python=platform.python_version(), platform=platform.platform(),
                packages={p: importlib.metadata.version(p) for p in ("numpy", "pandas", "matplotlib", "simpy")},
                std="sample SD across seeds; ddof=1; structural missing node metrics have count zero"))
    create_scenario_plots(slots, nodes, output, settings)
    columns = [("time_average_slot_latency_ms", "Latency, ms"), ("sla_breach_pct", "Offered failure, %"),
               ("admitted_sla_breach_pct", "Admitted breaches, %"), ("drop_pct", "Drops, %"),
               ("gold_silver_sla_breach_pct", "Gold/Silver breaches, %"), ("replica_seconds", "Replica seconds")]
    lines = ["# Dynamic scenario comparison", "", "30 paired seeds, 100 slots. Capacity is one scenario with 6- and 7-node variants.", "",
             "Mean ± sample SD across seeds. Offered failures include drops. Latency uses completed requests, averaged equally over nonempty arrival slots.", "",
             "| Scenario | " + " | ".join(label for _, label in columns) + " |", "|---|"+"---:|"*len(columns)]
    for (case, _, count), row in summary.iterrows():
        values = [f"{row[f'{metric}_mean']:.2f} ± {row[f'{metric}_std']:.2f}" for metric, _ in columns]
        lines.append("| " + " | ".join([f"{case} ({count} nodes)", *values]) + " |")
    lines += ["", "The <15% target applies to all-offered failure, including rejected traffic. "
              "Conditional admitted breaches are reported separately and cannot establish success by omitting drops. "
              "Gold/Silver have zero administrative drops. All workloads and weights were fixed before the measured run.", "",
              "Cold-start counts, first-request penalties, starts overlapping observed bursts, scale/migration counts, per-tier "
              "failures/drops, GPU/CPU metrics and runtimes are included in summary.csv and runs.csv. "
              "Forecasts have no future trace access; the first burst has no learned phase. "
              "A compound Poisson process is unpredictable at the request level; forecasting targets the periodic rate envelope."]
    (output / "results_table.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    update_original_summary(output, original)
    print("\n"+"\n".join(lines[6:13]), flush=True)
    return runs, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--output", type=Path, default=Path("results/dynamic_scenarios"))
    parser.add_argument("--original", type=Path, default=Path("results/dynamic"))
    parser.add_argument("--trials", type=int)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    values = asdict(Config.load(args.config))
    if args.trials is not None:
        values["trials"] = args.trials
    if args.seed is not None:
        values["first_seed"] = args.seed
    run_scenarios(Config(**values), ScenarioConfig(), args.output, args.original)


if __name__ == "__main__":
    main()
