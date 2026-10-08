"""Paired 8/9/10-node extension and an empirical knee analysis over 5–10 nodes."""
import argparse
from dataclasses import asdict, replace
import gzip
import inspect
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
from catalyst.reused import digest, write_json, write_gzip
from .config import Config
from .policies import sla_aware
from .predictive import ScenarioConfig
from .scenario_model import (ScenarioSimulator, extend_capacity, traffic_hash_payload,
                             validate_scenario_run, scenario_metrics)
from .scenarios import tagged
from .workload import generate_workload

COUNTS = (8, 9, 10)
KEYS = ("seed", "scenario", "policy", "node_count", "workload_hash", "traffic_hash")


def fit_knee(node_counts, values, minimum_slope_reduction=.25):
    """Continuous hinge least-squares fit; candidates exclude endpoints.

    y = intercept + before*x + change*max(0,x-k). An empirical knee requires
    decreasing pre/post slopes and >=25% reduction in slope magnitude. A flat
    or linear curve returns no detected knee. This is descriptive model fitting,
    not proof of a physical phase transition or a significance test.
    """
    x, y = np.asarray(node_counts, dtype=float), np.asarray(values, dtype=float)
    if len(x) < 4 or len(x) != len(y) or not np.isfinite(y).all() or not np.all(np.diff(x) > 0):
        raise ValueError("need >=4 ordered finite observations")
    fits = []
    for candidate in x[1:-1]:
        design = np.column_stack([np.ones(len(x)), x, np.maximum(0, x-candidate)])
        beta = np.linalg.lstsq(design, y, rcond=None)[0]
        fitted = design @ beta
        fits.append(dict(candidate=int(candidate), residual_sum_squares=float(np.sum((fitted-y)**2)),
                         intercept=float(beta[0]), slope_before=float(beta[1]),
                         slope_after=float(beta[1]+beta[2]), fitted_values=fitted.tolist()))
    best = min(fits, key=lambda f: (round(f["residual_sum_squares"], 10), f["candidate"]))
    before, after = best["slope_before"], best["slope_after"]
    reduction = 1-abs(after)/abs(before) if before < -1e-6 else 0.
    detected = before < -1e-6 and after <= 1e-6 and reduction >= minimum_slope_reduction
    return dict(knee_node=best["candidate"] if detected else None, detected=bool(detected),
                slope_reduction_fraction=float(reduction), **best, candidate_fits=fits)


def analyze(combined, output):
    """Paired marginal gains and seed-resampled uncertainty of the fitted knee."""
    metrics = ("sla_breach_pct", "time_average_slot_latency_ms", "average_latency_ms", "replica_seconds")
    marginal = []
    for metric in metrics:
        pivot = combined.pivot(index="seed", columns="node_count", values=metric).sort_index(axis=1)
        for source, target in zip(pivot.columns[:-1], pivot.columns[1:]):
            gain = pivot[source]-pivot[target]
            marginal.append(dict(from_nodes=int(source), to_nodes=int(target), metric=metric,
                                 mean_reduction=float(gain.mean()), paired_std=float(gain.std()),
                                 seeds=len(gain), seeds_improved=int((gain>0).sum())))
    pd.DataFrame(marginal).to_csv(output / "marginal_gains.csv", index=False)
    pivot = combined.pivot(index="seed", columns="node_count", values="sla_breach_pct").sort_index(axis=1)
    values, counts = pivot.to_numpy(), pivot.columns.to_numpy()
    fitted = fit_knee(counts, values.mean(axis=0))
    rng = np.random.default_rng(6801)
    frequencies = {str(n): 0 for n in counts[1:-1]}
    frequencies["none"] = 0
    for _ in range(1000):
        sampled = values[rng.integers(0, len(values), len(values))].mean(axis=0)
        result = fit_knee(counts, sampled)
        frequencies[str(result["knee_node"]) if result["detected"] else "none"] += 1
    write_json(output / "knee_analysis.json", dict(method="continuous hinge least squares on six capacity means",
               slope_reduction_threshold=.25, seed_bootstrap_replicates=1000, seed_bootstrap_rng=6801,
               paired_seed_resampling=True, fitted=fitted, bootstrap_knee_counts=frequencies,
               interpretation="empirical candidate over 5–10 nodes; not a physical inflection or significance claim"))
    return fitted, frequencies


def plots(combined, trajectories, output, fitted):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .plotting import _save
    means = combined.groupby("node_count").mean(numeric_only=True)
    std = combined.groupby("node_count").std(numeric_only=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for ax, metric, label, color in ((axes[0], "sla_breach_pct", "SLA failure (% of offered requests)", "#2563eb"),
                                    (axes[1], "time_average_slot_latency_ms", "Time-averaged latency (ms)", "#059669")):
        ax.errorbar(means.index, means[metric], yerr=std[metric], color=color, marker="o", capsize=4)
        ax.set(xlabel="Number of edge nodes", ylabel=label, xticks=means.index, ylim=(0, None))
        ax.grid(axis="y", alpha=.2)
        if fitted["detected"]:
            ax.axvline(fitted["knee_node"], color="#d97706", linestyle="--", label="Fitted SLA knee")
            ax.legend(frameon=False)
    axes[0].axhline(15, color="#b91c1c", linestyle=":", label="15% target")
    if fitted["detected"]:
        axes[0].plot(means.index, fitted["fitted_values"], color="#4b5563", linestyle="--", alpha=.7)
    axes[0].legend(frameon=False)
    fig.suptitle("Capacity curve · unchanged SLA-aware policy · 30 paired seeds")
    fig.supxlabel("Bars: sample SD across seeds, not confidence intervals. Historical 5–7-node cases retain identical paired traffic.", fontsize=9)
    _save(fig, output, "capacity_curve")
    gains = pd.read_csv(output / "marginal_gains.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for ax, metric, label in ((axes[0], "sla_breach_pct", "SLA reduction per extra node (percentage points)"),
                             (axes[1], "time_average_slot_latency_ms", "Latency reduction per extra node (ms)")):
        group = gains.loc[gains.metric == metric]
        ax.bar(group.to_nodes, group.mean_reduction, color="#2563eb", alpha=.8)
        ax.errorbar(group.to_nodes, group.mean_reduction, yerr=group.paired_std, fmt="none", color="#374151", capsize=4)
        ax.axhline(0, color="#374151", linewidth=.8)
        ax.set(xlabel="Resulting node count", ylabel=label, xticks=group.to_nodes)
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Marginal benefit from each additional edge node")
    fig.supxlabel("Mean paired reduction ± sample SD of seed-wise differences; negative values indicate worsening.", fontsize=9)
    _save(fig, output, "marginal_benefits")
    fig, ax = plt.subplots(figsize=(12, 5), layout="constrained")
    styles = [("#4b5563", "-"), ("#2563eb", "--"), ("#059669", "-."),
              ("#d97706", ":"), ("#9333ea", (0, (3, 1, 1, 1))), ("#4b5563", (0, (7, 2)))]
    for (count, group), (color, line) in zip(trajectories.groupby("node_count", sort=True), styles):
        series = group.groupby("slot").gpu_utilization.mean()
        ax.plot(series.index, 100*series, color=color, linestyle=line, linewidth=2, label=f"{count} nodes")
    ax.set(xlabel="Time slot", ylabel="Pool GPU compute utilization (%)", ylim=(0, 100))
    ax.grid(axis="y", alpha=.2)
    ax.legend(ncol=3, frameon=False)
    ax.set_title("GPU pressure as the resource pool expands")
    fig.supxlabel("Capacity-weighted GPU busy time within each seed; equal-seed means across 30 paired traces.", fontsize=9)
    _save(fig, output, "gpu_utilization_over_time")


def run(config, output, history, master):
    if config.node_count != 5:
        raise ValueError("the sweep extends the fixed five-node baseline")
    output, history, master = Path(output), Path(history), Path(master)
    output.mkdir(parents=True, exist_ok=True)
    (output / "inputs").mkdir(exist_ok=True)
    prior = pd.read_csv(history / "runs.csv").loc[lambda f: f.scenario.isin(["baseline", "capacity_6", "capacity_7"])].copy()
    seeds = list(range(config.first_seed, config.first_seed+config.trials))
    prior = prior.loc[prior.seed.isin(seeds)]
    assert len(prior) == 3*config.trials and prior.groupby("seed").node_count.nunique().eq(3).all()
    previous_protocol = json.loads((history / "protocol.json").read_text(encoding="utf-8"))
    assert previous_protocol["base_config"] == asdict(config)
    assert previous_protocol["unchanged_sla_aware_function_hash"] == digest(inspect.getsource(sla_aware))
    sources = [*Path("dynamic_placement").glob("*.py"), Path("placement_experiment/data_generation.py"),
               Path("placement_experiment/algorithms.py"), Path("catalyst/reused.py")]
    write_json(output / "protocol.json", dict(config=asdict(config), node_counts=COUNTS,
               historical_node_counts=[5, 6, 7], historical_output=history.as_posix(),
               historical_runs_hash=digest((history / "runs.csv").read_text(encoding="utf-8")),
               historical_protocol_hash=digest((history / "protocol.json").read_text(encoding="utf-8")),
               unchanged_sla_aware_function_hash=digest(inspect.getsource(sla_aware)),
               source_hashes={p.as_posix(): digest(p.read_text(encoding="utf-8")) for p in sources},
               knee_method="continuous hinge least squares; candidates 6–9; >=25% smaller absolute post-knee slope",
               uncertainty="1000 paired-seed bootstrap samples; RNG 6801",
               conditions="same arrivals, deadlines, 3 replicas/service, 2 actions/slot; no prediction or admission control"))
    settings = ScenarioConfig()
    rows, slots_all, nodes_all, checks = [], [], [], []
    traces = {key: [] for key in ("actions", "reservations", "lifecycle")}
    with gzip.GzipFile(filename=str(output / "request_outcomes.csv.gz"), mode="wb", mtime=0) as stream:
        first = True
        for seed in seeds:
            base = generate_workload(config, seed)
            paired_hash = digest(traffic_hash_payload(base))
            assert prior.loc[prior.seed == seed].traffic_hash.eq(paired_hash).all()
            for count in COUNTS:
                case = f"capacity_{count}"
                workload = extend_capacity(base, count-config.node_count)
                assert digest(traffic_hash_payload(workload)) == paired_hash
                fingerprint = digest(workload.to_dict())
                write_gzip(output / "inputs" / f"seed_{seed:03d}_{case}.json.gz", workload.to_dict())
                case_config = replace(config, node_count=count)
                result = ScenarioSimulator(case_config, workload, settings).run()
                check = validate_scenario_run(case_config, workload, settings, result, False)
                checks.append(dict(seed=seed, node_count=count, **check))
                metrics, slots, nodes, outcomes = scenario_metrics(case_config, workload, result)
                rows.append(dict(seed=seed, scenario=case, policy="sla_aware", node_count=count,
                                 workload_hash=fingerprint, traffic_hash=paired_hash, **metrics))
                slots_all.append(tagged(slots, seed, case, fingerprint, paired_hash))
                nodes_all.append(tagged(nodes, seed, case, fingerprint, paired_hash))
                stream.write(tagged(outcomes, seed, case, fingerprint, paired_hash).to_csv(index=False, header=first).encode("utf-8"))
                first = False
                for key in traces:
                    if result[key]:
                        traces[key].append(tagged(pd.DataFrame(result[key]), seed, case, fingerprint, paired_hash))
            print(f"Seed {seed}: {len(base.requests):,} paired requests x 8/9/10 nodes validated", flush=True)
    runs, slots, nodes = pd.DataFrame(rows), pd.concat(slots_all, ignore_index=True), pd.concat(nodes_all, ignore_index=True)
    runs.to_csv(output / "runs.csv", index=False)
    slots.to_csv(output / "slot_trajectories.csv", index=False)
    nodes.to_csv(output / "node_trajectories.csv", index=False)
    for key, name in (("actions", "actions"), ("reservations", "reservation_events"), ("lifecycle", "lifecycle_events")):
        pd.concat(traces[key], ignore_index=True).to_csv(output / f"{name}.csv", index=False)
    combined = pd.concat([prior, runs], ignore_index=True, sort=False)
    combined.to_csv(output / "combined_runs.csv", index=False)
    metrics = [c for c in combined if c not in KEYS]
    summary = combined.groupby(["scenario", "policy", "node_count"], sort=False)[metrics].agg(["mean", "std", "count"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    summary.to_csv(output / "summary.csv")
    fitted, frequencies = analyze(combined, output)
    old_nodes = pd.read_csv(history / "node_trajectories.csv").loc[lambda f: f.scenario.isin(["baseline", "capacity_6", "capacity_7"]) & f.seed.isin(seeds)]
    pool = []
    for (seed, case), group in pd.concat([old_nodes, nodes], ignore_index=True).groupby(["seed", "scenario"], sort=False):
        folder = history if case in ("baseline", "capacity_6", "capacity_7") else output
        with gzip.open(folder / "inputs" / f"seed_{seed:03d}_{case}.json.gz", "rt", encoding="utf-8") as stream:
            units = json.load(stream)["gpu_units"]
        weighted = group.assign(busy=group.gpu_utilization*group.node.map(dict(enumerate(units))))
        fraction = weighted.groupby("slot").busy.sum()/sum(units)
        pool.append(pd.DataFrame(dict(slot=fraction.index, gpu_utilization=fraction.to_numpy(), seed=seed, node_count=len(units))))
    pool_frame = pd.concat(pool, ignore_index=True)
    pool_frame.to_csv(output / "gpu_pool_trajectories.csv", index=False)
    plots(combined, pool_frame, output, fitted)
    targets = [{"nodes": int(count), "mean_sla_failure_pct": float(g.sla_breach_pct.mean()),
                "mean_below_15pct": bool(g.sla_breach_pct.mean()<15), "seeds_below_15pct": int((g.sla_breach_pct<15).sum())}
               for count, g in combined.groupby("node_count")]
    write_json(output / "target_evaluation.json", targets)
    write_json(output / "verification.json", dict(new_runs=len(runs), combined_runs=len(combined), per_run_checks=checks,
               historical_traffic_paired=True, knee_bootstrap_counts=frequencies))
    master_table = pd.read_csv(master / "summary.csv")
    new_cases = [f"capacity_{n}" for n in COUNTS]
    master_table = master_table.loc[~master_table.scenario.isin(new_cases)]
    additions = summary.reset_index().loc[lambda f: f.scenario.isin(new_cases)]
    pd.concat([master_table, additions], ignore_index=True, sort=False).to_csv(master / "summary.csv", index=False)
    for name in ("capacity_curve", "marginal_benefits"):
        for extension in ("png", "svg"):
            shutil.copy2(output / f"{name}.{extension}", master / f"{name}.{extension}")
    lines = ["# Capacity sweep: 5–10 nodes", "", "30 paired seeds per capacity, unchanged SLA-aware policy. Values are mean ± sample SD.", "",
             "| Nodes | SLA failure, % | Time-avg latency, ms | Replica seconds |", "|---|---:|---:|---:|"]
    for (_, _, count), row in summary.iterrows():
        cells = [f"{row[f'{m}_mean']:.2f} ± {row[f'{m}_std']:.2f}" for m in ("sla_breach_pct", "time_average_slot_latency_ms", "replica_seconds")]
        lines.append("| "+" | ".join([str(count), *cells])+" |")
    lines += ["", f"Empirical hinge-fit knee: {fitted['knee_node']}. Pre-knee slope: {fitted['slope_before']:.3f} percentage points/node; post-knee slope: {fitted['slope_after']:.3f}.",
              "", "This is a fitted diminishing-return candidate over six tested capacities. It is not a physical inflection or a guaranteed optimum. "
              "The original 5–7-node runs are reused with verified paired traffic. See knee_analysis.json for bootstrap stability, "
              "marginal_gains.csv for paired increments, and target_evaluation.json for the <15% goal. No requests are dropped."]
    (output / "results_table.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("\n"+"\n".join(lines[4:12]), flush=True)
    return combined, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--output", type=Path, default=Path("results/capacity_sweep"))
    parser.add_argument("--history", type=Path, default=Path("results/dynamic_scenarios"))
    parser.add_argument("--master", type=Path, default=Path("results/dynamic"))
    args = parser.parse_args()
    run(Config.load(args.config), args.output, args.history, args.master)


if __name__ == "__main__":
    main()
