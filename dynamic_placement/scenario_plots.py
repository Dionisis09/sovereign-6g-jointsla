"""Updated scenario comparisons; admit-based SLA is shown beside drop costs."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .plotting import _save

STYLES = {"baseline": ("#4b5563", "-", "SLA-aware, 5 nodes"),
          "predictive": ("#d97706", "--", "Predictive prewarming"),
          "capacity_6": ("#2563eb", "-.", "6 nodes"),
          "capacity_7": ("#059669", ":", "7 nodes"),
          "admission": ("#9333ea", (0, (3, 1, 1, 1)), "Bronze admission control")}


def create_scenario_plots(slots, nodes, output, settings):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout="constrained",
                             gridspec_kw={"height_ratios": [3, 1]})
    burst = slots.loc[slots.scenario == "baseline"].groupby("slot").burst_service_fraction.mean()
    for case, (color, line, label) in STYLES.items():
        series = slots.loc[slots.scenario == case].groupby("slot").latency_ms.mean()
        axes[0].plot(series.index, series, color=color, linestyle=line, linewidth=2, label=label)
    arrivals = slots.loc[slots.scenario == "baseline"].groupby("slot").requests.mean()
    axes[1].plot(arrivals.index, arrivals, color="#4b5563", label="Paired offered requests")
    for slot, fraction in burst.items():
        if fraction:
            for ax in axes:
                ax.axvspan(slot-.5, slot+.5, color="#9ca3af", alpha=.15*fraction, linewidth=0)
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
        ax.set_ylim(bottom=0)
    axes[0].legend(ncol=3, frameon=False, fontsize=9)
    axes[0].set(ylabel="Completed-request latency (ms)", title="Three new scenarios · 30 paired seeds · 100 slots")
    axes[1].set(ylabel="Requests / slot", xlabel="Arrival slot (0.1 seconds)")
    fig.supxlabel("Retrospective cohort means include late completions. Dropped requests have no latency; their cost is shown separately.", fontsize=9)
    _save(fig, output, "latency_over_time")

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, layout="constrained")
    fields = [("cumulative_sla_breach_pct", "All-offered SLA failure (%)\nDrops count as failures"),
              ("cumulative_admitted_sla_breach_pct", "Admitted-request breaches (%)"),
              ("cumulative_drop_pct", "Dropped offered requests (%)")]
    for ax, (field, label) in zip(axes, fields):
        for case, (color, line, legend) in STYLES.items():
            series = slots.loc[slots.scenario == case].groupby("slot")[field].mean()
            ax.plot(series.index, series, color=color, linestyle=line, linewidth=2, label=legend)
        ax.set(ylabel=label, ylim=(0, 100))
        ax.grid(axis="y", alpha=.2)
        if "breach" in field:
            ax.axhline(settings.sla_target_pct, color="#b91c1c", linestyle="--", linewidth=.9)
    axes[0].set_title("Cumulative SLA outcomes and the admission-control tradeoff · means across 30 seeds")
    axes[0].legend(ncol=3, frameon=False, fontsize=9)
    axes[-1].set_xlabel("Arrival slot")
    fig.supxlabel("The 15% target applies to all offered traffic. Curves are equal-seed means; no confidence or significance claim.", fontsize=9)
    _save(fig, output, "cumulative_sla_breaches")

    fig, axes = plt.subplots(7, 1, figsize=(12, 13), sharex=True, layout="constrained")
    for node, ax in enumerate(axes):
        for case, (color, line, label) in STYLES.items():
            series = nodes.loc[(nodes.scenario == case) & (nodes.node == node)].groupby("slot").gpu_utilization.mean()
            if len(series):
                ax.plot(series.index, 100*series, color=color, linestyle=line, linewidth=1.8, label=label)
        ax.set(ylabel=f"Edge {node}\nGPU busy (%)", ylim=(0, 100))
        ax.grid(axis="y", alpha=.2)
        ax.axhline(80, color="#9ca3af", linestyle="--", linewidth=.7)
    axes[0].set_title("GPU utilization under scaling, extra capacity and admission control")
    axes[0].legend(ncol=3, frameon=False, fontsize=9)
    axes[-1].set_xlabel("Time slot")
    fig.supxlabel("Actual busy compute-unit time; shared [0,100]% axes. Edges 5 and 6 exist only in the expanded-capacity cases.", fontsize=9)
    _save(fig, output, "gpu_utilization_over_time")
