"""Three publication-exportable figures with fixed policy colors and units."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

STYLES = dict(static=("#4b5563", "-", "Static"), reactive=("#d97706", "--", "Reactive"),
              periodic=("#2563eb", "-.", "Periodic"), sla_aware=("#059669", ":", "SLA-aware"))


def _save(fig, output, name):
    fig.savefig(output / f"{name}.png", dpi=180, bbox_inches="tight")
    fig.savefig(output / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def _shade(ax, slots):
    exposure = slots.loc[slots.policy == "static"].groupby("slot").burst_service_fraction.mean()
    for slot, fraction in exposure.items():
        if fraction:
            ax.axvspan(slot - .5, slot + .5, color="#9ca3af", alpha=.12 * fraction, linewidth=0)


def create_plots(slots, nodes, config, output):
    """Slot outcomes are retrospective arrival cohorts, including late completions."""
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]}, layout="constrained")
    for policy, (color, line, label) in STYLES.items():
        series = slots.loc[slots.policy == policy].groupby("slot").latency_ms.agg(["mean", "std"])
        x = series.index.to_numpy()
        axes[0].plot(x, series["mean"], color=color, linestyle=line, label=label, linewidth=2)
    arrivals = slots.loc[slots.policy == "static"].groupby("slot").agg(
        arrivals=("requests", "mean"), expected_rate=("expected_rate_rps", "mean"))
    axes[1].plot(arrivals.index, arrivals.arrivals, color="#6b21a8", label="Observed arrivals")
    axes[1].plot(arrivals.index, arrivals.expected_rate * config.slot_seconds, color="#a855f7", linestyle="--", label="Expected arrivals")
    for ax in axes:
        _shade(ax, slots)
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=.2)
        ax.legend(ncol=4, frameon=False)
    axes[0].set_ylabel("Mean request latency (ms)")
    axes[1].set_ylabel("Requests / slot")
    axes[1].set_xlabel(f"Arrival slot ({config.slot_seconds:g} s per slot)")
    axes[0].set_title(f"Request delay through periodic traffic bursts · {config.trials} paired seeds")
    fig.supxlabel("Equal-seed means of arrival-cohort request means. Gray shading indicates scheduled burst exposure.", fontsize=9)
    _save(fig, output, "latency_over_time")

    fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
    for policy, (color, line, label) in STYLES.items():
        series = slots.loc[slots.policy == policy].groupby("slot").cumulative_sla_breach_pct.agg(["mean", "std"])
        x = series.index.to_numpy()
        ax.plot(x, series["mean"], color=color, linestyle=line, label=label, linewidth=2)
        ax.fill_between(x, np.maximum(0, series["mean"] - series["std"]),
                        np.minimum(100, series["mean"] + series["std"]), color=color, alpha=.09)
    _shade(ax, slots)
    ax.set(xlabel="Arrival slot", ylabel="Cumulative deadline breaches (% of offered requests)",
           ylim=(0, 100), title=f"SLA failure across policies · {config.trials} paired seeds")
    ax.legend(ncol=4, frameon=False)
    ax.grid(axis="y", alpha=.2)
    fig.supxlabel("Bands: ± sample SD across seeds, clipped to [0,100]%; not confidence intervals. Late completions are included.", fontsize=9)
    _save(fig, output, "cumulative_sla_breaches")

    fig, axes = plt.subplots(config.node_count, 1, figsize=(11, 2 * config.node_count), sharex=True, layout="constrained")
    axes = np.atleast_1d(axes)
    for node, ax in enumerate(axes):
        for policy, (color, line, label) in STYLES.items():
            series = nodes.loc[(nodes.node == node) & (nodes.policy == policy)].groupby("slot").gpu_utilization.mean()
            ax.plot(series.index, 100 * series, color=color, linestyle=line, label=label, linewidth=1.8)
        ax.axhline(80, color="#9ca3af", linewidth=.8, linestyle="--")
        _shade(ax, slots)
        ax.set(ylabel=f"Edge {node}\nGPU busy (%)", ylim=(0, 100))
        ax.grid(axis="y", alpha=.2)
    axes[0].legend(ncol=4, frameon=False, loc="upper left")
    axes[0].set_title(f"Finite GPU compute utilization · means across {config.trials} seeds")
    axes[-1].set_xlabel("Time slot")
    fig.supxlabel("Actual busy compute-unit time / available compute-unit time. VRAM reservations and offered overload are separate CSV metrics.", fontsize=9)
    _save(fig, output, "gpu_utilization_over_time")
