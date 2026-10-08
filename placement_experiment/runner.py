"""Generate once per seed, compare four algorithms, save CSVs and three plots."""
import argparse
from dataclasses import asdict
import importlib.metadata
import json
from pathlib import Path
import platform
from time import perf_counter_ns
import pandas as pd
from catalyst.reused import digest, write_json
from .algorithms import ALGORITHMS
from .data_generation import Config, generate_scenario
from .metrics import calculate_metrics
from .plotting import create_plots


def run_experiment(config: Config, output: Path):
    """Each algorithm gets identical inputs; only random placement consumes RNG.

    Add future optimizers to ALGORITHMS with the same (config, scenario, seed)
    signature. Metrics independently reject invalid capacity allocations.
    """
    output.mkdir(parents=True, exist_ok=True)
    rows, outcomes = [], []
    inputs = []
    for seed in range(config.first_seed, config.first_seed + config.trials):
        scenario = generate_scenario(config, seed)
        encoded = scenario.to_dict()
        scenario_hash = digest(encoded)
        inputs.append(encoded)
        for name, algorithm in ALGORITHMS.items():
            start = perf_counter_ns()
            assignments = algorithm(config, scenario, seed)
            runtime_ms = (perf_counter_ns() - start) / 1_000_000
            metrics, application_outcomes = calculate_metrics(config, scenario, assignments)
            rows.append(dict(seed=seed, scenario_hash=scenario_hash, algorithm=name,
                             runtime_ms=runtime_ms, **metrics))
            outcomes.extend(dict(seed=seed, algorithm=name, **row) for row in application_outcomes)
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "results.csv", index=False)
    pd.DataFrame(outcomes).to_csv(output / "application_outcomes.csv", index=False)
    metric_names = [column for column in frame if column not in ("seed", "scenario_hash", "algorithm")]
    summary = frame.groupby("algorithm", sort=False)[metric_names].agg(["mean", "std", "count"])
    summary.columns = [f"{metric}_{statistic}" for metric, statistic in summary.columns]
    summary.to_csv(output / "summary.csv")
    write_json(output / "config.json", asdict(config))
    write_json(output / "scenarios.json", inputs)
    write_json(output / "environment.json", dict(python=platform.python_version(), platform=platform.platform(),
                                                packages={p: importlib.metadata.version(p) for p in ("numpy", "pandas", "matplotlib")},
                                                latency_model="network RTT + 12 ms * (1 + CPU utilization + .8 GPU utilization + .3 bandwidth utilization); base processing configurable",
                                                std="sample standard deviation across trial seeds (ddof=1)",
                                                runtime="one algorithm call per trial; excludes generation, metrics and plotting"))
    display = summary[[f"{metric}_{stat}" for metric in
                       ("average_latency_ms", "sla_violation_rate", "unplaced_applications", "runtime_ms")
                       for stat in ("mean", "std")]]
    print(display.round(4).to_string())
    create_plots(frame, config, output)
    # Retain a short exact-lookup table including each node's CPU/GPU statistics.
    lines = ["# Placement experiment results", "",
             f"{config.trials} paired seeds × four methods = {len(frame)} runs. "
             f"{config.node_count} servers and {config.application_count} applications per seed.", "",
             "Values are mean ± sample standard deviation across seeds. SLA failures include "
             "unplaced offered traffic; mean latency is weighted by placed traffic only.", "",
             "| Algorithm | Latency, ms | SLA failure, % | Unplaced apps | Runtime, ms |",
             "|---|---:|---:|---:|---:|"]
    for name, row in summary.iterrows():
        values = []
        for metric, scale in (("average_latency_ms", 1), ("sla_violation_rate", 100),
                              ("unplaced_applications", 1), ("runtime_ms", 1)):
            values.append(f"{row[f'{metric}_mean']*scale:.3f} ± {row[f'{metric}_std']*scale:.3f}")
        lines.append("| " + " | ".join([name, *values]) + " |")
    lines += ["", "| Algorithm | Edge | CPU utilization, % | GPU utilization, % |", "|---|---|---:|---:|"]
    for name, row in summary.iterrows():
        for node in range(config.node_count):
            values = [f"{100*row[f'{resource}_utilization_node_{node}_mean']:.2f} ± "
                      f"{100*row[f'{resource}_utilization_node_{node}_std']:.2f}" for resource in ("cpu", "gpu")]
            lines.append("| " + " | ".join([name, str(node), *values]) + " |")
    lines += ["", "All placements pass independent CPU/GPU/bandwidth capacity validation. "
              "Baseline definitions and the fixed heuristic are in the README. This is a stipulated "
              "static latency model, not a measured telco system or a queueing simulation. "
              "SD bars show scenario variability, not confidence intervals or significance. "
              "The seed fixes inputs and decisions; wall-clock runtime is not deterministic.", "",
              "Inspect `results.csv`, `summary.csv`, `application_outcomes.csv`, and `scenarios.json` "
              "for full trial-level and application-level evidence. Heuristic weights were fixed before "
              "the experiment and were not tuned against these results."]
    (output / "results_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {len(frame)} runs and three plots to {output.resolve()}")
    return frame, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--output", type=Path, default=Path("results/placement"))
    parser.add_argument("--trials", type=int, help="Override trial count (minimum 30)")
    parser.add_argument("--seed", type=int, help="First seed in the consecutive seed range")
    args = parser.parse_args()
    values = asdict(Config.load(args.config))
    if args.trials is not None:
        values["trials"] = args.trials
    if args.seed is not None:
        values["first_seed"] = args.seed
    run_experiment(Config(**values), args.output)


if __name__ == "__main__":
    main()

