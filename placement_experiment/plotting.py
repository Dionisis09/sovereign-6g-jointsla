"""Three matplotlib figures from saved trial rows; error bars are sample SD."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from .algorithms import ALGORITHMS

COLORS = ("#3575A5", "#D99532", "#7D8751", "#AD6695")
LABELS = ("Random", "Greedy", "Shortest latency", "SLA weighted")


def _summary_bars(axis, frame, metric, label, percent=False):
    grouped = frame.groupby("algorithm")[metric]
    order = list(ALGORITHMS)
    scale = 100 if percent else 1
    means = grouped.mean().reindex(order).to_numpy() * scale
    deviation = grouped.std(ddof=1).reindex(order).to_numpy() * scale
    axis.bar(np.arange(4), means, color=COLORS, edgecolor="#333333", linewidth=.6)
    axis.errorbar(np.arange(4), means, yerr=deviation, fmt="none", color="#333333", capsize=4)
    axis.set_xticks(np.arange(4), ["Random", "Greedy", "Shortest\nlatency", "SLA\nweighted"])
    axis.set_ylabel(label)
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", alpha=.2)
    axis.set_axisbelow(True)
    if percent:
        axis.set_ylim(0, min(100, max(10, float(np.nanmax(means + deviation)) * 1.15)))


def create_plots(frame, config, output):
    """Use consistent category colors/order; never infer significance from SD bars."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    subtitle = f"{config.trials} paired seeds; {config.node_count} nodes, {config.application_count} applications; mean ± sample SD"

    def save(figure, filename, caption):
        figure.suptitle(caption + "\n" + subtitle, fontsize=12)
        figure.tight_layout(rect=(0, .04, 1, .9))
        figure.savefig(output / f"{filename}.png", dpi=180)
        figure.savefig(output / f"{filename}.svg")
        plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    _summary_bars(axes[0], frame, "average_latency_ms", "Placed-traffic mean latency (ms)")
    _summary_bars(axes[1], frame, "sla_violation_rate", "Offered traffic failing SLA (%)", percent=True)
    figure.text(.5, .025, "SLA failures include unplaced traffic; latency excludes unplaced applications.", ha="center", fontsize=9)
    save(figure, "latency_and_sla", "Placement latency and SLA failures")

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    x = np.arange(config.node_count)
    width = .18
    for axis, resource in zip(axes, ("cpu", "gpu")):
        for j, (algorithm, label, color) in enumerate(zip(ALGORITHMS, LABELS, COLORS)):
            subset = frame[frame.algorithm == algorithm]
            columns = [f"{resource}_utilization_node_{i}" for i in range(config.node_count)]
            axis.bar(x + (j - 1.5) * width, subset[columns].mean().to_numpy() * 100, width,
                     yerr=subset[columns].std(ddof=1).to_numpy() * 100, capsize=2,
                     label=label, color=color, edgecolor="#333333", linewidth=.5,
                     error_kw={"linewidth": .8})
        axis.set_title(resource.upper())
        axis.set_xticks(x, [f"Edge {i}" for i in range(config.node_count)])
        axis.set_ylim(0, 105)
        axis.axhline(100, color="#333333", linestyle="--", linewidth=1)
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Reserved capacity utilization (%)")
    figure.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=4, frameon=False)
    save(figure, "node_utilization", "CPU and GPU utilization by edge node")

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    _summary_bars(axes[0], frame, "unplaced_applications", "Unplaced applications (of 20)")
    axes[0].set_ylabel(f"Unplaced applications (of {config.application_count})")
    _summary_bars(axes[1], frame, "runtime_ms", "Algorithm runtime (ms)")
    figure.text(.5, .025, "Lower SD bounds are clipped at zero. Runtime depends on the host and system load.", ha="center", fontsize=9)
    save(figure, "admission_and_runtime", "Unplaced applications and algorithm runtime")

