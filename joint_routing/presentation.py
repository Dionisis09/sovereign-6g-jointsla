"""CSV-backed report and eight publication figures for the frozen experiment."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from .router import LABELS

FOCUS=("sla_aware","sla_rr","sla_shortest_queue","joint_sla")
COLORS=("#475569","#2563eb","#d97706","#059669")
METRICS=dict(sla_breach_rate="SLA failure",mean_request_latency_ms="Request mean latency",p95_latency_ms="p95 latency",p99_latency_ms="p99 latency")


def create(output,settings):
    raw=pd.read_csv(output/"raw_policy_results.csv")
    summary=pd.read_csv(output/"summary_statistics.csv")
    indexed=summary.set_index(["policy","metric"])
    tests=pd.read_csv(output/"paired_tests.csv")
    ablations=pd.read_csv(output/"ablation_tests.csv")
    differences=pd.read_csv(output/"paired_seed_differences.csv")
    hypotheses=json.loads((output/"hypotheses.json").read_text(encoding="utf-8"))
    folder=output/"figures";folder.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"svg.fonttype":"none","pdf.fonttype":42})
    def interval(ax,metric,label,factor=1,policies=FOCUS):
        for i,p in enumerate(policies):
            row=indexed.loc[(p,metric)];mean=row["mean"]*factor
            err=[[max(0,mean-row.ci95_lower*factor)],[max(0,row.ci95_upper*factor-mean)]]
            ax.errorbar(mean,i,xerr=err,fmt="o",color=COLORS[FOCUS.index(p)] if p in FOCUS else "#475569",capsize=4,ms=6)
        ax.set(yticks=range(len(policies)),yticklabels=[LABELS[p] for p in policies],xlabel=label)
        ax.set_xlim(left=0);ax.invert_yaxis();ax.grid(axis="x",alpha=.2)
        ax.spines[["top","right"]].set_visible(False)
    def save(fig,name,caption="Means across 30 paired seeds; bars: 95% bootstrap CIs of seed means."):
        fig.text(.5,.015,caption,ha="center",fontsize=9)
        fig.tight_layout(rect=(0,.07,1,1))
        for ext in ("png","svg","pdf"):
            fig.savefig(folder/f"{name}.{ext}",dpi=300,facecolor="white")
        plt.close(fig)
    for name,metric,label,factor in (("01_joint_sla_breaches","sla_breach_rate","SLA failure (% of offered requests)",100),
                                    ("02_joint_mean_latency","mean_request_latency_ms","Mean request latency (ms)",1),
                                    ("03_joint_p95","p95_latency_ms","Request-level p95 latency (ms)",1),
                                    ("04_joint_p99","p99_latency_ms","Request-level p99 latency (ms)",1)):
        fig,ax=plt.subplots(figsize=(8.4,4.8));interval(ax,metric,label,factor)
        ax.set_title(label.split(" (")[0]+": deployment and routing")
        save(fig,name)
    fig,axes=plt.subplots(1,3,figsize=(14,4.8))
    for ax,tier in zip(axes,("Gold","Silver","Bronze")):
        interval(ax,f"{tier}_breach_rate","SLA failure within tier (%)",100);ax.set_title(tier)
    fig.suptitle("Per-tier SLA outcomes")
    save(fig,"05_joint_per_tier")
    fig,axes=plt.subplots(2,3,figsize=(14,8))
    for ax,(metric,label,factor) in zip(axes.flat,(("average_replicas","Average allocated replicas",1),
          ("mean_gpu_vram_reserved_pct","VRAM residency (%)",1),("cold_starts","Cold starts / run",1),
          ("migrations","Migrations / run",1),("total_actions","Total controller actions / run",1),
          ("average_gpu_utilization","GPU busy utilization (%)",100))):
        interval(ax,metric,label,factor)
    fig.suptitle("Operational resource and reconfiguration costs")
    save(fig,"06_joint_resource_cost")
    new_focus=FOCUS[1:]
    fig,axes=plt.subplots(1,3,figsize=(14,4.9))
    for ax,(metric,label) in zip(axes,(("routed_away_from_lowest_network_fraction","Away from minimum network delay (%)"),
                                     ("queue_changed_choice_fraction","Differs from no-queue score (%)"),
                                     ("multi_eligible_fraction","Multiple eligible replicas (%)"))):
        interval(ax,metric,label,100,new_focus);ax.set_xlim(0,100)
    fig.suptitle("First successful request assignments")
    save(fig,"07_joint_routing_effect","30 paired seed means and 95% CIs. Counterfactual score differences are descriptive, not causal routing effects.")
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    interval(axes[0,0],"controller_decision_mean_ms","Policy + action application (ms)")
    interval(axes[0,1],"controller_total_instrumented_mean_ms","New controller incl. snapshot (ms)",policies=new_focus)
    interval(axes[1,0],"request_routing_decision_mean_ms","Routing attempt mean (ms)",policies=new_focus)
    interval(axes[1,1],"request_routing_decision_p95_ms","Routing attempt p95 (ms)",policies=new_focus)
    fig.suptitle("Instrumented computation overhead")
    save(fig,"08_joint_controller_overhead","Wall time; 95% CIs. Historical baseline snapshots were not timed. Routing includes diagnostic selection, excludes audit JSON.")
    def cell(policy,metric,factor=1,precision=2):
        r=indexed.loc[(policy,metric)]
        return f"{r['mean']*factor:.{precision}f} [{r.ci95_lower*factor:.{precision}f}, {r.ci95_upper*factor:.{precision}f}]"
    def table(metrics,policies=FOCUS):
        lines=["| Policy | "+" | ".join(label for metric,label,factor in metrics)+" |","|---|"+"---:|"*len(metrics)]
        for policy in policies:
            lines.append("| "+" | ".join([LABELS[policy],*[cell(policy,metric,factor,4 if "_ms" in metric and "decision" in metric else 2) for metric,label,factor in metrics]])+" |")
        return lines
    main_table=table((("sla_breach_rate","SLA failures (%)",100),("mean_request_latency_ms","Request mean (ms)",1),
                      ("p95_latency_ms","p95 (ms)",1),("p99_latency_ms","p99 (ms)",1)))
    (output/"main_results_table.md").write_text("\n".join(["Mean [95% CI of mean] across seeds.","",*main_table])+"\n",encoding="utf-8")
    primary=tests.loc[tests.policy_B=="sla_aware"]
    claims=[]
    for r in primary.itertuples():
        if r.supported_improvement:
            claims.append(dict(metric=r.metric,relative_improvement_percent=r.relative_improvement_percent,
                               p_value_holm=r.p_value_holm,sentence=f"JointSLA reduced {METRICS[r.metric].lower()} by {r.relative_improvement_percent:.2f}% relative to existing SLA-aware across 30 paired synthetic workloads (Holm p={r.p_value_holm:.3g})."))
    pd.DataFrame(claims,columns=["metric","relative_improvement_percent","p_value_holm","sentence"]).to_csv(output/"claim_ledger.csv",index=False)
    doc=(__import__('pathlib').Path(__file__).with_name("README.md")).read_text(encoding="utf-8")
    design=doc.split("## Observable routing estimates\n",1)[1].split("## Slow deployment and formal coupling",1)[0]
    formal=doc.split("## Slow deployment and formal coupling\n",1)[1].split("## Predeclared hypotheses",1)[0]
    lines=["# Research Question","",
           "Does coupling SLA-aware placement/scaling with queue-aware online routing add SLA/tail-latency benefit over the verified SLA-aware orchestrator at acceptable resource and reconfiguration cost?","",
           "# Existing SLA-aware Baseline","",
           "The verified baseline uses a common FIFO service queue with available replicas pulling requests. It already adapts assignment to availability; it is not arbitrary/static routing. Its deployment/scaling function, physical worker and all verified results remain unchanged.","",
           "# Joint Placement and Routing Design","",design,
           "# Formal Problem Formulation","",formal,
           "# Experimental Setup","",
           f"The same five-node, 20-service, 100×0.1-s verified scenario uses seeds 1–30. There are {len(raw)} comparative runs: 120 verified baseline runs reused read-only and 150 newly simulated runs across five routing policies. "
           "Each policy has exactly 30 common traffic tapes. Static/Reactive/Periodic are retained for context; no capacity sweep or new workload is run.","",
           "All admitted requests drain after arrivals end. All-offered failures retain the existing denominator; no new admission control is introduced. Request quantiles use completed end-to-end request latencies. The slot mean remains a separate preserved metric. "
           "Policy means and 95% percentile bootstrap CIs use seeds as units with 10,000 reproducible resamples. Main Holm family=12, ablation family=8. No parameters were tuned after main outcomes.","",
           "# SLA Results","",*main_table,"",
           "# Mean and Tail Latency","",
           "Latency includes service waiting, node-resource waiting, network, CPU→GPU→CPU execution and lifecycle penalties. Per-run p95/p99 are request-level quantiles, then averaged across seeds; no quantiles of slot means or pooled cross-seed requests are reported.","",
           "| Metric vs SLA-aware | Relative improvement (%) [95% CI] | Absolute reduction [95% CI] |",
           "|---|---:|---:|"]
    for r in primary.itertuples():
        f=100 if r.metric=="sla_breach_rate" else 1
        lines.append(f"| {METRICS[r.metric]} | {r.relative_improvement_percent:.2f} [{r.relative_ci95_lower:.2f}, {r.relative_ci95_upper:.2f}] | {r.absolute_difference*f:.2f} [{r.difference_ci95_lower*f:.2f}, {r.difference_ci95_upper*f:.2f}] |")
    lines += ["","SLA absolute reductions are percentage points; latency reductions are ms. Positive means JointSLA is better.","",
              "# Per-Tier Results","",*table(tuple((f"{t}_breach_rate",f"{t} failure (%)",100) for t in ("Gold","Silver","Bronze"))),"",
              "# Routing Behavior","",
              "Only eligible active replicas receive assignments. When none exists, requests wait; cold or migrating instances do not receive new work. Waiting requests can be reassigned on readiness/migration, but in-flight requests remain on their original worker. Every successful choice records observable candidates and scores.","",
              *table((("routed_away_from_lowest_network_fraction","Away from min network (%)",100),
                      ("queue_changed_choice_fraction","Differs from no-queue score (%)",100),
                      ("multi_eligible_fraction","Multi-eligible (%)",100)),policies=FOCUS[1:]),"",
              "These fractions use the first successful assignment per request. The no-queue alternative is a same-state score counterfactual, not a simulated alternate outcome. For RR/SQ it does not establish that queue awareness caused the difference. "
              "Replica request-count CV includes idle allocated instances; replica lifetimes differ and the distribution is descriptive. Full counts are in replica_request_distribution.csv.","",
              "# Resource Cost","",*table((("average_replicas","Avg replicas",1),("mean_gpu_vram_reserved_pct","VRAM residency (%)",1),
                    ("cold_starts","Cold starts",1),("migrations","Migrations",1),("total_actions","Actions",1))),"",
              *table((("scale_outs","Scale-outs",1),("scale_ins","Scale-ins",1),("peak_replicas","Sampled peak replicas",1),
                    ("average_cpu_utilization","CPU busy (%)",100),("average_gpu_utilization","GPU busy (%)",100))),"",
              "Resource-normalized ratios are exploratory ratios of mean improvement to additional resources/actions. A nonpositive denominator yields an explicitly undefined ratio; it is not replaced with infinity or an invented efficiency value. "
              "Comparable measured resources alone cannot prove resource-independent causality. See resource_normalized_analysis.csv.","",
              f"JointSLA versus SLA-aware: replica increase 95% CI {hypotheses['replica_increase_percent_ci95'][0]:.2f}% to {hypotheses['replica_increase_percent_ci95'][1]:.2f}%; "
              f"VRAM residency increase CI {hypotheses['vram_increase_pp_ci95'][0]:.2f} to {hypotheses['vram_increase_pp_ci95'][1]:.2f} percentage points.","",
              "# Controller Overhead","",
              "Legacy decision time measures policy computation and action application, excluding snapshots. The new instrumented total also includes control-start snapshot construction. Historical baseline snapshot time is unavailable; zero new-router fields in baseline rows denote no explicit added routing mechanism, not a timing measurement of shared-FIFO dispatch.","",
              *table((("controller_decision_mean_ms","Legacy decision mean (ms)",1),)),"",
              *table((("controller_total_instrumented_mean_ms","Total incl. snapshot (ms)",1),
                     ("request_routing_decision_mean_ms","Routing mean (ms)",1),("request_routing_decision_p95_ms","Routing p95 (ms)",1)),policies=FOCUS[1:]),"",
              "Routing times include failed eligibility attempts and observational counterfactual selection but exclude audit JSON serialization. Reassignment can make multiple decisions per request. The overhead is measured wall time, not added to simulated request delay. H5 uses mean full controller time and the mean of per-seed routing-attempt p95 values. These are local instrumented measurements, not hardware profiling.","",
              "# Statistical Significance","",
              "Two-sided paired Wilcoxon tests assess signed differences around zero, subject to independent seed pairs and symmetry/location assumptions. Mean difference bootstrap CIs provide complementary estimates. Significant benefit requires Holm p<0.05, positive mean reduction and a positive lower mean-difference CI.","",
              "| Comparator | Metric | Raw p | Holm p | Rank-biserial | Supported improvement |","|---|---|---:|---:|---:|---|"]
    for r in tests.itertuples():
        lines.append(f"| {LABELS[r.policy_B]} | {METRICS[r.metric]} | {r.p_value:.3g} | {r.p_value_holm:.3g} | {r.rank_biserial_correlation:.4f} | {'yes' if r.supported_improvement else 'no'} |")
    lines += ["","Exploratory fast-routing ablations (separate Holm family):","",
              "| Ablation comparator | Metric | Relative improvement (%) | Holm p |","|---|---|---:|---:|"]
    for r in ablations.itertuples():
        lines.append(f"| {LABELS[r.policy_B]} | {METRICS[r.metric]} | {r.relative_improvement_percent:.2f} | {r.p_value_holm:.3g} |")
    no_queue=ablations.loc[ablations.policy_B=="joint_no_queue"]
    no_slack=ablations.loc[ablations.policy_B=="joint_no_slack"]
    lines += ["",f"Full JointSLA shows supported benefit on {int(no_queue.supported_improvement.sum())}/4 metrics versus the no-queue ablation, "
              f"and {int(no_slack.supported_improvement.sum())}/4 versus the no-slack ablation. "
              "The latter provides no evidence that the added variance/slack risk ranking improves on queue-aware predicted completion in this experiment. "
              "Feedback-dependent deployments prevent pure fixed-placement attribution."]
    lines += ["","# Wins / Ties / Losses","","| Comparator | Metric | Wins | Ties | Losses |","|---|---|---:|---:|---:|"]
    for r in tests.itertuples():
        lines.append(f"| {LABELS[r.policy_B]} | {METRICS[r.metric]} | {r.wins} | {r.ties} | {r.losses} |")
    nonwins=differences.loc[(differences.family=="main") & (differences.outcome!="win")]
    lines += ["","# Negative Results","","Every non-winning main comparison is retained:","",
              "| Seed | Comparator | Metric | Outcome | Baseline value | JointSLA value |","|---:|---|---|---|---:|---:|"]
    for r in nonwins.itertuples():
        lines.append(f"| {r.seed} | {LABELS[r.baseline_policy]} | {METRICS[r.metric]} | {r.outcome} | {r.baseline_value:.6f} | {r.joint_value:.6f} |")
    if nonwins.empty:lines.append("No ties/losses in these main comparisons.")
    lines += ["","# Interpretation","",f"Predeclared overall decision: **{hypotheses['decision']}**.","",
              "| Hypothesis | Supported under its predeclared rule |","|---|---|"]
    for name in ("H1","H2","H3","H4","H5"):
        lines.append(f"| {name} | {'yes' if hypotheses[name] else 'no'} |")
    gold_base=raw.loc[raw.policy=="sla_aware","Gold_breach_rate"].mean()*100
    gold_joint=raw.loc[raw.policy=="joint_sla","Gold_breach_rate"].mean()*100
    lines += ["",f"The overall SLA mean is {raw.loc[raw.policy=='joint_sla','sla_breach_rate'].mean()*100:.2f}%; "
              "this experiment does not achieve the earlier <15% aspiration. "
              f"Gold failures remain {gold_base:.2f}% versus {gold_joint:.2f}% for JointSLA; aggregate benefit must not be presented as an established Gold-tier benefit. "
              "Per-tier rows are descriptive and are not covered by the primary significance family.","",
              "This strengthens the empirical case for a coupled deployment/routing contribution within this synthetic model. "
              "It does not by itself establish publication readiness or first-in-literature novelty, and it does not establish additional benefit from the SLA/slack risk term."]
    lines += ["","H1/H2 require statistically supported improvements over SLA-aware. H3 uses supported improvement or its predeclared descriptive 5% noninferiority margin. "
              "H4 also requires comparable-resource bounds (replicas <=5% increase, VRAM <=2pp). H5 screens 10-ms control and 1-ms routing budgets. Failing any rule does not trigger retuning.","",
              "Possible mechanisms must be treated as hypotheses: per-replica pinned queues can add head-of-line waiting relative to the already work-conserving central FIFO; network cost, scarce replica residency and conservative lifecycle/uncertainty proxies may limit routing gain. "
              "Routing baselines and ablations constrain interpretation, but do not isolate every mechanism. Negative outcomes are retained.","",
              "# Threats to Validity","",
              "- Synthetic uncalibrated workloads and service timings; one verified configuration, no scalability or real-hardware study.",
              "- Baseline is shared-FIFO pull scheduling; new policies introduce explicit queues. Routing-only baselines use the same deployment function but feedback-dependent actions can differ.",
              "- Variance/slack and node waiting estimates are uncalibrated proxies; no global optimization or probabilistic deadline guarantee is established.",
              "- Queue/slack ablations affect subsequent feedback and deployment; they are exploratory and not pure replay with fixed placements.",
              "- Requests awaiting eligibility are retained. Mean/tail latency uses completed requests; all-offered SLA failures preserve accounting. Replica peaks remain slot-sampled.",
              "- Observed memory/resources and diagnostic ratios do not isolate a causal resource effect or universal efficiency metric.",
              "- Seed-level CIs are pointwise and finite-sample; model uncertainty and Wilcoxon assumptions remain. Previously inspected baseline seeds are not independent external validation.",
              "- Old/new wall-clock timing scopes differ for snapshots; new instrumentation includes counterfactual ranking and excludes audit serialization. Computational overhead is not injected into simulated request latency.","",
              "# Safe Paper Claims","",
              "- The experiment preserves identical traffic tapes and the verified physical model while evaluating explicit online routing and coupled deployment."]
    for r in claims:lines.append("- "+r["sentence"])
    if not claims:
        lines.append("- The predeclared tests do not support an additional JointSLA improvement over the existing SLA-aware policy in this configuration.")
    lines += ["","# Claims We Cannot Make","",
              "- Globally optimal, first-ever coupled edge orchestrator, or production-ready telco controller.",
              "- A calibrated SLA-risk probability, general superiority, or benefits isolated exclusively to queue awareness.",
              "- Free improvement at identical resource cost, significance where Holm p>=0.05, or success when H1–H5 criteria fail.","",
              "Reproduce with `python run_joint_routing.py --seeds 1:30 --reuse-results`; use `--force` to rerun only the new policies. Baseline artifacts are protected by before/after hashes."]
    (output/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
