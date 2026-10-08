"""Matplotlib-only paper figures: seed-level means and bootstrap 95% CIs."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from .accounting import POLICIES, LABELS

COLORS = ("#475569", "#2563eb", "#d97706", "#059669")


def save(fig, folder, name, caption):
    fig.text(.5, .015, caption, ha="center", va="bottom", fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, 1))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(folder/f"{name}.{ext}", dpi=300, facecolor="white")
    plt.close(fig)


def points(ax, summary, metric, label, factor=1):
    values = summary.loc[summary.metric == metric].set_index("policy").loc[list(POLICIES)]
    for x, (_, r), color in zip(range(4), values.iterrows(), COLORS):
        mean = r["mean"]*factor
        err = np.array([[mean-r.ci95_lower*factor], [r.ci95_upper*factor-mean]])
        ax.errorbar(x, mean, yerr=np.maximum(0, err), fmt="o", color=color, ms=7, capsize=5, lw=1.6)
    ax.set_xticks(range(4), [LABELS[p] for p in POLICIES])
    ax.set_ylabel(label)
    ax.set_xlim(-.45, 3.45)
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=.22)
    ax.spines[["top", "right"]].set_visible(False)


def create(output):
    """Plot only generated CSV values; PNG 300 dpi plus SVG/PDF vectors."""
    folder = output/"figures"
    folder.mkdir(exist_ok=True)
    summary = pd.read_csv(output/"summary_statistics.csv")
    raw = pd.read_csv(output/"raw_policy_results.csv")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 13,
                         "axes.labelsize": 11, "svg.fonttype": "none", "pdf.fonttype": 42})
    caption = "Means across 30 paired seeds (1–30); error bars: 95% bootstrap CIs of means."
    names = (("01_sla_breach_comparison", "sla_breach_rate", "SLA failure (% of offered requests)", 100),
             ("02_mean_latency_comparison", "mean_request_latency_ms", "Mean request latency (ms)", 1),
             ("03_p95_latency_comparison", "p95_latency_ms", "Request-level p95 latency (ms)", 1),
             ("04_p99_latency_comparison", "p99_latency_ms", "Request-level p99 latency (ms)", 1))
    for name, metric, label, factor in names:
        fig, ax = plt.subplots(figsize=(7.3, 4.6))
        points(ax, summary, metric, label, factor)
        ax.set_title(label.split(" (")[0]+" by orchestration policy")
        save(fig, folder, name, caption)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.7), sharey=True)
    for tier, ax in zip(("Gold", "Silver", "Bronze"), axes):
        points(ax, summary, f"{tier}_breach_rate", "SLA failure within tier (%)", 100)
        ax.set_title(tier)
        ax.tick_params(axis="x", rotation=25)
    fig.suptitle("SLA failures by service tier")
    save(fig, folder, "05_per_tier_breach_rates", caption)
    fig, axes = plt.subplots(2, 3, figsize=(12.5, 8))
    for row, (metric, label, factor) in enumerate((("sla_breach_rate", "SLA failure (%)", 100), ("p99_latency_ms", "p99 latency (ms)", 1))):
        pivot = raw.pivot(index="seed", columns="policy", values=metric)
        upper = pivot.to_numpy().max()*factor*1.06
        for col, baseline in enumerate(POLICIES[:-1]):
            ax = axes[row, col]
            x, y = pivot[baseline]*factor, pivot.sla_aware*factor
            losing = y > x+1e-10
            ax.scatter(x[~losing], y[~losing], c=COLORS[3], s=28, alpha=.8)
            ax.scatter(x[losing], y[losing], c="#dc2626", marker="x", s=55)
            for seed in pivot.index[losing]:
                ax.annotate(f"seed {seed}", (x.loc[seed], y.loc[seed]), xytext=(-5, 7), textcoords="offset points", ha="right", fontsize=9)
            ax.plot([0, upper], [0, upper], "--", color="#94a3b8", lw=1)
            ax.set(xlim=(0, upper), ylim=(0, upper), xlabel=f"{LABELS[baseline]}: {label}", ylabel=f"SLA-aware: {label}")
            ax.set_aspect("equal", adjustable="box")
            ax.grid(alpha=.16)
    fig.suptitle("Paired workloads: points below the diagonal favor SLA-aware")
    save(fig, folder, "06_sla_aware_vs_baselines_paired", "One point per seed. Dashed diagonal: equality. Red crosses: SLA-aware has a higher value.")
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    costs = (("migrations", "Migrations / run"), ("scale_outs", "Scale-outs / run"),
             ("scale_ins", "Scale-ins / run"), ("cold_starts", "Cold starts / run"),
             ("average_replicas", "Time-averaged allocated replicas"), ("triggered_downtime_seconds", "Triggered downtime (replica-seconds)"))
    for ax, (metric, label) in zip(axes.flat, costs):
        points(ax, summary, metric, label)
        ax.set_title(label)
        ax.tick_params(axis="x", rotation=20)
    fig.suptitle("Reconfiguration and replica costs")
    save(fig, folder, "07_reconfiguration_costs", caption)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.7))
    for ax, metric, label, factor in zip(axes, ("average_cpu_utilization", "average_gpu_utilization", "mean_gpu_vram_reserved_pct"),
                                         ("CPU busy utilization (%)", "GPU compute busy utilization (%)", "GPU VRAM residency (%)"), (100, 100, 1)):
        points(ax, summary, metric, label, factor)
        ax.set_ylim(0, 100)
        ax.set_title(label.split(" (%)")[0])
        ax.tick_params(axis="x", rotation=25)
    fig.suptitle("Resource use over the arrival horizon")
    save(fig, folder, "08_resource_utilization", "Equal-node/slot utilization, then equal-seed means. Error bars: 95% bootstrap CIs. VRAM is reserved residency.")
    if (output/"capacity_summary.csv").exists():
        data = pd.read_csv(output/"capacity_summary.csv")
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.9))
        for ax, field, label, factor in zip(axes, ("breach_rate", "latency_ms"), ("SLA failure (%)", "Mean request latency (ms)"), (100, 1)):
            mean = data[f"mean_{field}"]*factor
            err = np.array([mean-data[f"{field}_ci95_lower"]*factor, data[f"{field}_ci95_upper"]*factor-mean])
            ax.errorbar(data.nodes, mean, yerr=err, fmt="o-", color=COLORS[1], capsize=4)
            ax.set(xlabel="Number of edge nodes", ylabel=label, xticks=data.nodes)
            ax.set_ylim(bottom=0)
            ax.grid(alpha=.2)
        axes[0].axhline(15, color="#dc2626", ls=":", label="15% target")
        axes[0].legend(frameon=False)
        fig.suptitle("Capacity sweep with unchanged SLA-aware policy")
        save(fig, folder, "09_capacity_sweep", "Existing 30 paired seeds (0–29); no rerun. Error bars: 95% bootstrap CIs of means.")
    if (output/"scenario_summary_statistics.csv").exists():
        data = pd.read_csv(output/"scenario_summary_statistics.csv")
        fig, axes = plt.subplots(1, 3, figsize=(12, 4.8))
        cases = ("baseline", "predictive", "admission")
        labels = ("Baseline", "Prewarming", "Admission")
        for ax, metric, label, factor in zip(axes, ("sla_breach_rate", "drop_rate", "cold_starts"), ("All-offered SLA failure (%)", "Dropped offered requests (%)", "Cold starts / run"), (100, 100, 1)):
            f = data.loc[data.metric == metric].set_index("scenario").loc[list(cases)]
            mean = f["mean"].to_numpy()*factor
            err = np.array([mean-f.ci95_lower.to_numpy()*factor, f.ci95_upper.to_numpy()*factor-mean])
            ax.errorbar(range(3), mean, yerr=err, fmt="o", color=COLORS[1], capsize=4)
            ax.set(xticks=range(3), xticklabels=labels, ylabel=label)
            ax.tick_params(axis="x", rotation=20)
            ax.set_ylim(bottom=0)
            ax.grid(axis="y", alpha=.2)
        fig.suptitle("Existing five-node intervention results")
        save(fig, folder, "10_scenario_tradeoffs", "Existing 30 paired seeds (0–29). Drops count as failures. Error bars: 95% bootstrap CIs of means.")
