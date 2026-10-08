"""Generate all reported results directly from exported CSVs."""
import pandas as pd
from .accounting import POLICIES, LABELS, PRIMARY

METRIC_LABELS = dict(sla_breach_rate="SLA breach rate", mean_request_latency_ms="Mean request latency",
                     p95_latency_ms="p95 latency", p99_latency_ms="p99 latency")


def generate(output, config, seeds):
    summary = pd.read_csv(output/"summary_statistics.csv").set_index(["policy", "metric"])
    tests = pd.read_csv(output/"paired_tests.csv")
    raw = pd.read_csv(output/"raw_policy_results.csv")
    differences = pd.read_csv(output/"paired_seed_differences.csv")
    def cell(policy, metric, factor=1):
        r = summary.loc[(policy, metric)]
        precision=4 if metric=="decision_runtime_mean_ms" else 2
        return f"{r['mean']*factor:.{precision}f} [{r.ci95_lower*factor:.{precision}f}, {r.ci95_upper*factor:.{precision}f}]"
    def table(metrics):
        lines = ["| Policy | "+" | ".join(label for metric, label, factor in metrics)+" |",
                 "|---|"+"---:|"*len(metrics)]
        for policy in POLICIES:
            lines.append("| "+" | ".join([LABELS[policy], *[cell(policy, m, f) for m, label, f in metrics]])+" |")
        return lines
    main_table = table((("sla_breach_rate", "SLA failure (%)", 100),
                        ("mean_request_latency_ms", "Request mean (ms)", 1),
                        ("p95_latency_ms", "p95 (ms)", 1), ("p99_latency_ms", "p99 (ms)", 1)))
    (output/"main_results_table.md").write_text("\n".join(["Mean [95% CI of mean]; seed-level summaries.", "", *main_table])+"\n", encoding="utf-8")
    costs = []
    for baseline in POLICIES[:-1]:
        for metric in ("total_actions", "scale_outs", "scale_ins", "cold_starts", "average_replicas",
                       "replica_seconds", "vram_gb_seconds", "triggered_downtime_seconds", "decision_runtime_mean_ms"):
            a = raw.loc[raw.policy == "sla_aware", metric].mean()
            b = raw.loc[raw.policy == baseline, metric].mean()
            costs.append(dict(baseline=baseline, metric=metric, baseline_mean=b, sla_aware_mean=a,
                              sla_aware_minus_baseline=a-b, proposed_higher_cost=bool(a>b),
                              interpretation="resource/lifecycle cost; runtime is host-dependent"))
    pd.DataFrame(costs).to_csv(output/"cost_tradeoffs.csv", index=False)
    supported, claims = [], []
    for i, r in tests.iterrows():
        if r.supported_improvement:
            sentence = (f"The SLA-aware policy reduced {METRIC_LABELS[r.metric].lower()} by "
                        f"{r.relative_improvement_percent:.2f}% relative to {LABELS[r.policy_B]} across "
                        f"{int(r.n)} paired synthetic workloads (Holm-adjusted p={r.p_value_holm:.3g}).")
            supported.append("- "+sentence)
            claims.append(dict(claim_id=f"primary_{i}", metric=r.metric, baseline=r.policy_B,
                               relative_improvement_percent=r.relative_improvement_percent,
                               p_value_holm=r.p_value_holm, sentence=sentence))
    pd.DataFrame(claims).to_csv(output/"claim_ledger.csv", index=False)
    lines = ["# Experimental Setup", "",
             f"Research question: under identical dynamic AI-edge workloads, does the existing SLA-aware policy reduce SLA violations and latency relative to Static, Reactive and Periodic, and at what resource/reconfiguration cost?", "",
             f"The main experiment uses seeds {min(seeds)}–{max(seeds)}: {len(seeds)} independent generated workloads and {len(raw)} successful seed-policy runs. "
             f"Each has {config.node_count} heterogeneous nodes, {config.service_count} services and {config.slots} slots of {config.slot_seconds:g} s. "
             "Every policy receives the same immutable workload, traffic tape and initial greedy placement within its seed. "
             "Existing simulator, policy, traffic and SLA parameters are unchanged. Controllers receive past/current snapshots only.", "",
             "All offered arrival cohorts are retained and admitted requests drain after the arrival horizon. Drops and unplaced requests remain failures. "
             "Rates in CSV are fractions unless the legacy name ends in `_pct`; displayed rates are percentages. "
             "Each seed, not each request or slot, is the statistical replication unit.", "",
             "Mean confidence intervals use 10,000 percentile bootstrap resamples of complete seeds at 95% confidence, with fixed root RNG seed 73001 and stable keyed substreams. "
             "Paired differences and ratios of means resample aligned policy pairs. Intervals are pointwise, not simultaneous. "
             "Wilcoxon tests are two-sided; primary inference uses Holm correction across all 12 baseline/metric comparisons. "
             "Zero differences are excluded; differences are rounded to 12 decimals for ranks. Exact p-values are used only without zeros/tied magnitudes; otherwise a tie-corrected asymptotic method is disclosed.", "",
             "# Main Results", "", "Values are mean [95% bootstrap CI of the mean] across seeds.", "", *main_table, "",
             "# SLA Compliance", "",
             "The all-offered rate counts deadline violations and admission failures. Lower values are better. Relative improvements below are ratios of policy means, not averages of per-seed percentages.", "",
             "| Baseline | Absolute reduction (percentage points) | Relative reduction (%) [95% CI] | Wins / ties / losses |",
             "|---|---:|---:|---:|"]
    for r in tests.loc[tests.metric == "sla_breach_rate"].itertuples():
        lines.append(f"| {LABELS[r.policy_B]} | {100*r.absolute_difference:.2f} | {r.relative_improvement_percent:.2f} [{r.relative_ci95_lower:.2f}, {r.relative_ci95_upper:.2f}] | {r.wins}/{r.ties}/{r.losses} |")
    lines += ["", "# Latency", "",
              "Request latency is service queue waiting + node resource waiting + network delay + CPU preprocessing + GPU inference + CPU postprocessing + lifecycle penalty. "
              "The request mean weights all completed requests equally within a seed. The preserved slot mean weights nonempty arrival-slot request means equally. "
              "Neither invents latency for dropped/unplaced requests; counts and failures disclose that selection.", "",
              *table((("mean_request_latency_ms", "Request mean (ms)", 1), ("mean_slot_latency_ms", "Slot mean (ms)", 1))), "",
              "# Tail Latency", "",
              "Median, p95 and p99 use NumPy linear quantiles of every completed request's actual end-to-end latency within a run, including late completions. "
              "The main table and figures show the mean of 30 per-run quantiles, with CIs across seeds. These are neither pooled-request quantiles nor quantiles of slot averages.", "",
              "# Per-Tier Analysis", "",
              "Each tier uses its own offered-request denominator, rather than equal weighting of services.", "",
              *table(tuple((f"{tier}_breach_rate", f"{tier} failure (%)", 100) for tier in ("Gold", "Silver", "Bronze"))), "",
              "# Statistical Significance", "",
              "The signed-rank test assesses whether paired differences are consistent with a distribution symmetric about zero; it is not a direct test of mean equality. "
              "Independent seed generation and a defensible symmetry/location interpretation are assumptions. Bootstrap mean-difference CIs provide a separate estimate of average benefit. "
              "A supported improvement requires Holm-adjusted p <0.05, positive mean improvement and a positive lower paired mean-difference CI.", "",
              "| Baseline | Metric | Wilcoxon W | p (raw) | p (Holm) | Method | Supported improvement |",
              "|---|---|---:|---:|---:|---|---|"]
    for r in tests.itertuples():
        lines.append(f"| {LABELS[r.policy_B]} | {METRIC_LABELS[r.metric]} | {r.test_statistic:g} | {r.p_value:.3g} | {r.p_value_holm:.3g} | {r.wilcoxon_method} | {'yes' if r.supported_improvement else 'no'} |")
    lines += ["", "# Effect Sizes", "",
              "Matched-pairs rank-biserial correlation = (positive rank sum − negative rank sum) / total nonzero rank sum, where differences are baseline minus SLA-aware. "
              "+1 indicates all nonzero ranks favor SLA-aware; −1 favors the baseline. This is a directional paired effect size, not a percentage reduction.", "",
              "| Baseline | Metric | Rank-biserial | Relative improvement (%) | Wins / ties / losses |",
              "|---|---|---:|---:|---:|"]
    for r in tests.itertuples():
        lines.append(f"| {LABELS[r.policy_B]} | {METRIC_LABELS[r.metric]} | {r.rank_biserial_correlation:.4f} | {r.relative_improvement_percent:.2f} | {r.wins}/{r.ties}/{r.losses} |")
    nonwins = differences.loc[differences.outcome != "win"]
    lines += ["", "All non-winning primary observations:", "",
              "| Seed | Baseline | Metric | Outcome | Baseline value | SLA-aware value |",
              "|---:|---|---|---|---:|---:|"]
    for r in nonwins.itertuples():
        lines.append(f"| {r.seed} | {LABELS[r.baseline_policy]} | {METRIC_LABELS[r.metric]} | {r.outcome} | {r.baseline_value:.6f} | {r.sla_aware_value:.6f} |")
    if nonwins.empty:
        lines.append("No ties or losses in the primary metrics.")
    lines += ["", "# Reconfiguration Costs", "",
              "Average allocated replicas is the exact replica-seconds integral divided by the arrival horizon, including cold replicas. "
              "Peak replicas is sampled at slot ends plus the initial allocation; it is not an event-level transient peak. "
              "Accepted actions and actual cold-start events are counted separately. Downtime is the sum of triggered replica downtime, not elapsed system-wide outage.", "",
              *table((("scale_outs", "Scale-outs", 1), ("scale_ins", "Scale-ins", 1), ("migrations", "Migrations", 1),
                      ("cold_starts", "Cold starts", 1), ("average_replicas", "Average replicas", 1))), "",
              *table((("replica_seconds", "Replica-seconds", 1), ("vram_gb_seconds", "VRAM GB-seconds", 1),
                      ("decision_runtime_mean_ms", "Decision runtime (ms)", 1))), "",
              "Higher SLA-aware cost metrics (descriptive; not additional primary significance tests):", ""]
    for r in pd.DataFrame(costs).loc[lambda f: f.proposed_higher_cost].itertuples():
        lines.append(f"- Versus {LABELS[r.baseline]}: `{r.metric}` rises from {r.baseline_mean:.3f} to {r.sla_aware_mean:.3f}.")
    lines += ["", "CPU/GPU utilization averages give equal weight to node-slots over the arrival horizon, then to seeds. "
              "Weighted-pool alternatives are exported. Higher busy utilization is not automatically a performance regression; it may shift work out of the post-horizon drain. "
              "Reserved VRAM and GPU compute busy time are distinct.", "",
              *table((("average_cpu_utilization", "CPU busy (%)", 100), ("average_gpu_utilization", "GPU busy (%)", 100),
                      ("mean_gpu_vram_reserved_pct", "VRAM residency (%)", 1))), "",
              "# Capacity Analysis", ""]
    if (output/"capacity_summary.csv").exists():
        capacity = pd.read_csv(output/"capacity_summary.csv")
        lines += ["Existing verified capacity runs are reused: 30 paired seeds 0–29 at each of 5–10 nodes. "
                  "The unchanged heuristic operates on nested topology pools; initial greedy placement adapts to the pool. "
                  "These results do not isolate GPU capacity from topology/initial-placement changes. Supplemental workloads share 29 seeds with the main run and are not an independent replication.", "",
                  "| Nodes | SLA failure (%) [95% CI] | Request mean latency (ms) [95% CI] |",
                  "|---:|---:|---:|"]
        for r in capacity.itertuples():
            lines.append(f"| {r.nodes} | {100*r.mean_breach_rate:.2f} [{100*r.breach_rate_ci95_lower:.2f}, {100*r.breach_rate_ci95_upper:.2f}] | {r.mean_latency_ms:.2f} [{r.latency_ms_ci95_lower:.2f}, {r.latency_ms_ci95_upper:.2f}] |")
        best = capacity.loc[capacity.mean_breach_rate.idxmin()]
        lines.append(f"\nThe lowest observed mean is {100*best.mean_breach_rate:.2f}% at {int(best.nodes)} nodes. "
                     f"The <15% mean target is {'met' if best.mean_breach_rate<.15 else 'not met'}. These CIs quantify seed variability and do not establish an exact physical inflection.")
    else:
        lines.append("No verified 30-seed raw capacity results were available. Existing results are preserved; new runs are required before reporting statistical CIs.")
    lines += ["", "# Admission Control", ""]
    if (output/"scenario_summary_statistics.csv").exists():
        scenarios = pd.read_csv(output/"scenario_summary_statistics.csv").set_index(["scenario", "metric"])
        def sc(case, metric, factor=1):
            r = scenarios.loc[(case, metric)]
            return f"{r['mean']*factor:.2f} [{r.ci95_lower*factor:.2f}, {r.ci95_upper*factor:.2f}]"
        lines += ["Existing seeds 0–29 are reused without modifying admission control. All-offered failures include drops; conditional admitted rates cannot establish success alone.", "",
                  "| Case | All-offered failure (%) [95% CI] | Drop (%) [95% CI] | Gold/Silver failure (%) [95% CI] |",
                  "|---|---:|---:|---:|"]
        for case in ("baseline", "admission"):
            lines.append("| "+" | ".join([case, sc(case, "sla_breach_rate",100), sc(case,"drop_rate",100), sc(case,"Gold_Silver_breach_rate",100)])+" |")
        lines += ["", f"Admission's conditional admitted breach rate is {sc('admission','admitted_breach_rate',100)}%; "
                  f"Bronze drop rate is {sc('admission','Bronze_drop_rate',100)}%. Gold and Silver have no administrative drops in these records.", "",
                  "# Prewarming", "",
                  f"Existing prewarming all-offered failure is {sc('predictive','sla_breach_rate',100)}%, compared with {sc('baseline','sla_breach_rate',100)}% for its paired baseline. "
                  "This configuration does not demonstrate a lower mean failure rate. The ten-slot moving-average predictor learns burst phase from past observations and uses the configured period; it does not predict individual Poisson arrivals.", "",
                  f"Cold starts: baseline {sc('baseline','cold_starts')}, prewarming {sc('predictive','cold_starts')}. "
                  f"Accepted prewarm actions: {sc('predictive','prewarm_actions')}. Negative results are retained. Supplemental comparisons are exploratory."]
    else:
        lines += ["No verified existing raw intervention data were available.", "", "# Prewarming", "", "No verified existing raw data were available."]
    lines += ["", "# Main Findings", "", *supported,
              "", "The corresponding per-seed outcomes and complete cost tradeoffs remain visible; aggregate improvements do not imply every seed or metric improves.", "",
              "# Limitations", "",
              "- Synthetic, uncalibrated workload and service throughput; one default operating configuration and finite seed count.",
              "- This is retrospective statistical evaluation of an existing heuristic, not a preregistered independent confirmatory study; 29 main seeds overlap previous experiments.",
              "- Gold/Silver/Bronze priorities and deadlines vary together, so tier comparisons do not isolate priority alone.",
              "- Service components remain colocated; FIFO queues and serial replica pipelines constrain throughput. No real network, GPU interference, failures or deployed telco system is tested.",
              "- Static/Periodic do not scale; the proposed method may use more replicas and memory. Comparisons assess full policy behavior, not equal-resource algorithm efficiency.",
              "- Bootstrap intervals describe means across generated seeds; n=30 does not guarantee nominal coverage for heavy tails. They are pointwise and do not include model uncertainty.",
              "- Wilcoxon assumes independent seed pairs and a symmetry/location interpretation; it does not prove mean equality, causal mechanisms or real-world generalization.",
              "- p95/p99 are averages of per-run completed-request quantiles. Completion selection, all-offered failure and drop counts must be read together.",
              "- Utilization covers arrival slots only; latency includes drained requests. Runtime is machine-dependent and not a production benchmark.",
              "- Sampled replica peaks can miss transient within-slot peaks. Higher utilization is not by itself evidence of inefficiency.", "",
              "## Safe Paper Claims", "", *supported, "",
              "## Claims We Cannot Make", "",
              "- First-ever SLA-aware edge orchestrator or established bibliographic novelty.",
              "- Globally optimal placement, universal SLA guarantee or production-ready telco system.",
              "- A mean SLA failure rate below 15% in the tested configurations.",
              "- Improvement for every seed in every metric, free improvement at identical resource cost, or successful prewarming in this configuration.", "",
              "## Reproducibility and Method References", "",
              "Run `python run_paper_experiments.py --seeds 1:30`; use `--reuse-results` to analyze existing verified main outcomes, or `--force` for a full main rerun. "
              "Supplemental simulations are never rerun by this command. Install `requirements-paper.txt` first.", "",
              "Statistical implementation follows [SciPy Wilcoxon documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html) "
              "and the [percentile bootstrap definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html). "
              "All empirical values come from CSVs in this output directory. `claim_ledger.csv` maps supported claims to comparison results; `validation.json` records independent checks."]
    (output/"report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
