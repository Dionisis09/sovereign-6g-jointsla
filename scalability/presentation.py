"""Figures and conditional claims bound to the exported scale-level statistics."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from .configuration import SCALES,POLICIES

LABELS={"sla_aware":"SLA-aware","joint_sla":"JointSLA","sla_shortest_queue":"SLA-aware+ShortestQueue"}
COLORS={"sla_aware":"#475569","joint_sla":"#059669","sla_shortest_queue":"#d97706"}
NAMES={"sla_breach_rate":"SLA failure","mean_request_latency_ms":"Mean request latency","p95_latency_ms":"p95 latency","p99_latency_ms":"p99 latency"}


def create(output):
    raw=pd.read_csv(output/"raw_results.csv");summary=pd.read_csv(output/"summary_statistics.csv")
    tests=pd.read_csv(output/"paired_tests.csv");secondary=pd.read_csv(output/"secondary_paired_tests.csv")
    negative=pd.read_csv(output/"negative_seed_cases.csv");resources=pd.read_csv(output/"resource_scaling.csv")
    config=pd.read_csv(output/"scale_configuration_summary.csv");h=json.loads((output/"hypotheses.json").read_text())
    indexed=summary.set_index(["scale","policy","metric"])
    scales=list(SCALES);x=np.arange(3)
    folder=output/"figures";folder.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"svg.fonttype":"none","pdf.fonttype":42})
    def chart(ax,metric,label,factor=1,policies=POLICIES):
        for i,policy in enumerate(policies):
            rows=[indexed.loc[(s,policy,metric)] for s in scales]
            mean=np.array([r["mean"] for r in rows])*factor
            lo=np.array([r.ci95_lower for r in rows])*factor;hi=np.array([r.ci95_upper for r in rows])*factor
            ax.errorbar(x+(i-(len(policies)-1)/2)*.045,mean,yerr=np.array([np.maximum(0,mean-lo),np.maximum(0,hi-mean)]),
                        marker=("o","s","^")[i],color=COLORS[policy],label=LABELS[policy],capsize=4,linewidth=1.6)
        ax.set(xticks=x,xticklabels=["SMALL\n5 nodes / 20 services","MEDIUM\n10 / 40","LARGE\n20 / 80"],ylabel=label)
        ax.set_ylim(bottom=0);ax.grid(axis="y",alpha=.2);ax.spines[["top","right"]].set_visible(False)
    def save(fig,name,caption="30 paired seeds per scale; bars: 95% bootstrap CIs of seed-level means."):
        fig.text(.5,.015,caption,ha="center",fontsize=9)
        fig.tight_layout(rect=(0,.08,1,1))
        for ext in ("png","svg","pdf"):fig.savefig(folder/f"{name}.{ext}",dpi=300,facecolor="white")
        plt.close(fig)
    for number,metric,label,factor in (("01_sla_breaches_vs_scale","sla_breach_rate","SLA failure (% of offered requests)",100),
          ("02_mean_latency_vs_scale","mean_request_latency_ms","Mean request latency (ms)",1),
          ("03_p95_vs_scale","p95_latency_ms","Request-level p95 latency (ms)",1),
          ("04_p99_vs_scale","p99_latency_ms","Request-level p99 latency (ms)",1)):
        fig,ax=plt.subplots(figsize=(9,5.4));chart(ax,metric,label,factor);ax.legend(loc="best");ax.set_title(label.split(" (")[0]+" across proportional scales");save(fig,number)
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    for ax,metric in zip(axes.flat,NAMES):
        f=tests.loc[tests.metric==metric].set_index("scale").loc[scales]
        mean=f.relative_improvement_percent.to_numpy();lo=f.relative_ci95_lower.to_numpy();hi=f.relative_ci95_upper.to_numpy()
        ax.errorbar(x,mean,yerr=np.array([np.maximum(0,mean-lo),np.maximum(0,hi-mean)]),fmt="o-",capsize=4,color=COLORS["joint_sla"])
        ax.axhline(0,color="#475569",ls="--",lw=1);ax.set(xticks=x,xticklabels=scales,ylabel="Relative improvement (%)",title=NAMES[metric]);ax.grid(axis="y",alpha=.2)
    fig.suptitle("JointSLA gain relative to SLA-aware")
    save(fig,"05_relative_gain_vs_scale","Ratio of paired seed means; 95% paired bootstrap CIs. Positive = JointSLA benefit; connecting lines are descriptive.")
    for number,pairs in (("06_replicas_vs_scale",(("average_replicas","Average allocated replicas",1),("replicas_per_service","Replicas / service",1))),
                         ("07_vram_vs_scale",(("mean_gpu_vram_reserved_pct","VRAM residency (%)",1),("vram_reserved_gib_per_node","Reserved VRAM / node (GiB)",1))),
                         ("08_actions_vs_scale",(("total_actions","Actions / run",1),("actions_per_1000_requests","Actions / 1000 requests",1)))):
        fig,axes=plt.subplots(1,2,figsize=(13,5.3))
        for ax,(metric,label,factor) in zip(axes,pairs):chart(ax,metric,label,factor)
        axes[0].legend(loc="best");fig.suptitle("Measured resource and lifecycle scaling");save(fig,number)
    fig,axes=plt.subplots(2,2,figsize=(13,9))
    for ax,(metric,label,policies) in zip(axes.flat,(("controller_decision_mean_ms","Policy + apply mean (ms)",POLICIES),
        ("controller_total_instrumented_mean_ms","Controller incl. snapshot mean (ms)",POLICIES),
        ("request_routing_decision_p95_ms","Mean per-seed routing-attempt p95 (ms)",POLICIES[1:]),
        ("controller_cpu_ms_per_request","Controller CPU / offered request (ms)",POLICIES))):
        chart(ax,metric,label,policies=policies)
    axes[0,0].legend(loc="best");fig.suptitle("Instrumented computation overhead")
    save(fig,"09_controller_overhead_vs_scale","All three policies freshly timed. Wall timer scopes differ from total CPU; routing diagnostics exclude JSON. No real-hardware profiling.")
    fig,ax=plt.subplots(figsize=(9,5.4));chart(ax,"wall_seconds_per_100k_requests","Audited simulation wall time / 100k requests (s)")
    ax.legend(loc="best");ax.set_title("Normalized audited simulation runtime")
    save(fig,"10_normalized_runtime_vs_scale","Simulation includes online audit creation; excludes workload generation, result export and validation. 30-seed means and 95% CIs.")

    def cell(scale,policy,metric,factor=1,precision=2):
        r=indexed.loc[(scale,policy,metric)]
        return f"{r['mean']*factor:.{precision}f} [{r.ci95_lower*factor:.{precision}f}, {r.ci95_upper*factor:.{precision}f}]"
    def table(scale,columns,policies=POLICIES):
        lines=["| Policy | "+" | ".join(label for metric,label,factor in columns)+" |","|---|"+"---:|"*len(columns)]
        for policy in policies:lines.append("| "+" | ".join([LABELS[policy],*[cell(scale,policy,m,f,4 if "decision" in m else 2) for m,l,f in columns]])+" |")
        return lines
    primary_columns=(("sla_breach_rate","SLA failure (%)",100),("mean_request_latency_ms","Mean (ms)",1),
                     ("median_latency_ms","Median (ms)",1),("p95_latency_ms","p95 (ms)",1),("p99_latency_ms","p99 (ms)",1))
    claims=[]
    for r in tests.itertuples():
        if r.supported_improvement:
            claims.append(dict(scale=r.scale,metric=r.metric,relative_improvement_percent=r.relative_improvement_percent,p_value_holm=r.p_value_holm,
              sentence=f"At {r.scale}, JointSLA reduced {NAMES[r.metric].lower()} by {r.relative_improvement_percent:.2f}% relative to SLA-aware across 30 paired synthetic workloads (Holm p={r.p_value_holm:.3g})."))
    pd.DataFrame(claims,columns=["scale","metric","relative_improvement_percent","p_value_holm","sentence"]).to_csv(output/"claim_ledger.csv",index=False)
    lines=["# Research Question","","Does the verified JointSLA preserve its advantage over SLA-aware as edge nodes, services, requests and routing decisions increase proportionally?","",
      "# Verified JointSLA Baseline","","The verified five-node/20-service experiment found SLA failures 56.87% versus 50.91%, mean latency 296.37 versus 209.54 ms, p95 1315.17 versus 877.26 ms and p99 2198.83 versus 1634.22 ms. "
      "This study imports its policy and score unchanged, protects both verified output trees and reruns SMALL to establish timing-only instrumentation identity. All SMALL performance/resource metrics agree with the verified values.","",
      "# Scalability Methodology","","Three policies (SLA-aware, JointSLA, SLA-aware+ShortestQueue) × three scales × seeds 1–30 give 270 freshly simulated main runs. A separate 27-run pilot preceded them. "
      "Every scale/seed uses one common hashed traffic tape. No tuning, future traffic, new pipeline, capacity distribution, traffic regime or thresholds are introduced. No optional stress or Static experiment was run.","",
      "The fixed generator distributions and algorithm parameters scale only node/service counts. Policy parameters include the SAME two-action budget per 100-ms slot, three-replica limit and cooldown; "
      "therefore control opportunities per service decrease with system size. This is an algorithmic bottleneck to investigate, not an increase in exogenous offered pressure. CPU→GPU→CPU stages remain colocated.","",
      "All offered requests are counted, including unplaced/drop failures; admitted requests drain after the ten-second arrival horizon. Request means and within-run p95/p99 use completed requests. "
      "requests_processed_per_slot denotes completed arrival-cohort volume/T including drain; requests_completed_within_horizon_per_slot separately measures actual completions within T. "
      "CIs use 10,000 seed-level bootstrap resamples. Main Holm family=12 across all scales/four metrics; SQ uses a separate 12-test family. Relative improvements are ratios of paired scale-level means.","",
      "# Scale-Preserving Configuration","","Per-seed evidence is in scale_configuration_summary.csv and the fixed consistency screens in scale_consistency_checks.csv. These screen 30-seed distributional means within 15%, tier fractions within 4pp; "
      "they do not establish exact per-seed difficulty equivalence. GPU compute demand is one execution unit for 10 ms; VRAM residency is a distinct resource.","",
      "| Scale | Services/node | Requests/service | CPU offered pressure | GPU offered pressure | Initial VRAM pressure | Gold/Silver/Bronze (%) | Burst slots (%) | Mean deadline (ms) |",
      "|---|---:|---:|---:|---:|---:|---|---:|---:|"]
    for scale in SCALES:
        m=config.loc[config.scale==scale].mean(numeric_only=True)
        lines.append(f"| {scale} | {m.services_per_node:.0f} | {m.requests_per_service:.2f} | {m.expected_cpu_pressure:.4f} | {m.expected_gpu_pressure:.4f} | {m.initial_vram_pressure:.4f} | {m.Gold_proportion*100:.2f}/{m.Silver_proportion*100:.2f}/{m.Bronze_proportion*100:.2f} | {m.burst_slots_fraction*100:.2f} | {m.mean_deadline_ms:.2f} |")
    for scale in SCALES:lines += ["",f"# {scale.title()} Results","","Means [95% CI of seed-level mean]:","",*table(scale,primary_columns)]
    lines += ["","# SLA Generalization","","| Scale | SLA relative gain (%) [95% CI] | Absolute reduction (pp) [95% CI] | Holm p | Wins/ties/losses |","|---|---:|---:|---:|---|"]
    for r in tests.loc[tests.metric=="sla_breach_rate"].itertuples():
        lines.append(f"| {r.scale} | {r.relative_improvement_percent:.2f} [{r.relative_ci95_lower:.2f}, {r.relative_ci95_upper:.2f}] | {r.absolute_difference*100:.2f} [{r.difference_ci95_lower*100:.2f}, {r.difference_ci95_upper*100:.2f}] | {r.p_value_holm:.3g} | {r.wins}/{r.ties}/{r.losses} |")
    lines += ["","# Mean and Tail Latency","","All p95/p99 are computed from raw end-to-end request outcomes within runs, then summarized across seeds. No quantiles of slot averages or pooled cross-seed requests are used.","",
              "| Scale | Metric | Relative gain (%) [95% CI] | Absolute reduction (ms) [95% CI] |","|---|---|---:|---:|"]
    for r in tests.loc[tests.metric!="sla_breach_rate"].itertuples():
        lines.append(f"| {r.scale} | {NAMES[r.metric]} | {r.relative_improvement_percent:.2f} [{r.relative_ci95_lower:.2f}, {r.relative_ci95_upper:.2f}] | {r.absolute_difference:.2f} [{r.difference_ci95_lower:.2f}, {r.difference_ci95_upper:.2f}] |")
    lines += ["","# Per-Tier Generalization","","Tier means are descriptive; no per-tier significance claim is drawn from the primary test family."]
    for scale in SCALES:lines += ["",f"{scale}:","",*table(scale,tuple((f"{t}_breach_rate",f"{t} failures (%)",100) for t in ("Gold","Silver","Bronze")))]
    lines += ["","# Resource Scaling","","Means [95% CI]; GPU busy time and VRAM residency are distinct. Allocated replicas include cold/retiring instances; eligible counts are slot-end sampled. "
              "The controller cannot exceed 200 accepted actions during the 100-slot horizon. Normalized actions can decrease mechanically as request counts grow; this alone is not evidence of efficiency."]
    lines += ["","Routing diagnostics:"]
    for scale in SCALES:
        lines += ["",f"{scale}:","",*table(scale,(("routing_decisions","Successful assignments",1),("queue_changed_choice_fraction","Differs from no-queue score (%)",100),
            ("multi_eligible_fraction","Multi-eligible requests (%)",100)),POLICIES[1:]),"",
            *table(scale,(("replica_load_imbalance_cv","All-allocated replica request CV",1),("average_eligible_replicas","Sampled eligible replicas",1),
                         ("completed_requests_per_average_eligible_replica","Requests / avg eligible replica",1)))]
    lines += ["","The observed imbalance includes all allocated/retired IDs and unused replicas for every policy, reconstructed from initial creation order and scale-out actions. "
              "Unequal lifetimes make it descriptive. Queue-change fractions describe first assignments under a same-state score counterfactual, not a causal effect. "
              "The preserved legacy baseline router-only CV sentinel is separate from the newly observed replica_load_imbalance_cv field."]
    for scale in SCALES:
        lines += ["",f"{scale}:","",*table(scale,(("average_replicas","Avg replicas",1),("peak_replicas","Sampled peak",1),("replicas_per_service","Replicas/service",1),
          ("mean_gpu_vram_reserved_pct","VRAM (%)",1),("cold_starts","Cold starts",1),("migrations","Migrations",1),("total_actions","Actions",1))),"",
          *table(scale,(("scale_outs","Scale-outs",1),("scale_ins","Scale-ins",1),("average_cpu_utilization","CPU busy (%)",100),("average_gpu_utilization","GPU busy (%)",100),("actions_per_1000_requests","Actions/1000 requests",1)))]
    lines += ["","Paired resource differences (JointSLA minus SLA-aware; positive = additional cost):","",
              "| Scale | Metric | Difference [95% CI] |","|---|---|---:|"]
    lines += []
    for r in resources.loc[resources.metric.isin(("average_replicas","mean_gpu_vram_reserved_pct","cold_starts","total_actions","migrations"))].itertuples():
        lines.append(f"| {r.scale} | {r.metric} | {r.joint_minus_baseline:.2f} [{r.CI_low:.2f}, {r.CI_high:.2f}] |")
    lines += ["","Relative counter/resource intervals are explicitly undefined when any bootstrap baseline mean is zero (notably rare migrations). All absolute differences/CIs remain available; no resamples are dropped."]
    lines += ["","# Controller Overhead Scaling","","All policies were freshly instrumented, including baseline snapshot time. Process CPU time is the sum of control-start snapshot, policy, action application and explicit routing dispatch CPU; "
              "nested routing inside migration application is subtracted from control-only CPU to avoid double counting. Dispatch CPU includes audit creation; the verified routing wall timer excludes JSON. "
              "Windows process CPU timers can be quantized, and sampled RSS covers the entire process. Timing is not injected into simulated latency. It does not establish a production hardware budget."]
    for scale in SCALES:
        lines += ["",f"{scale}:","",*table(scale,(("controller_decision_mean_ms","Policy/apply mean ms",1),("controller_decision_p95_ms","Policy/apply p95 ms",1),
            ("controller_total_instrumented_mean_ms","Full control mean ms",1),("controller_total_instrumented_p95_ms","Full control p95 ms",1))),"",
            *table(scale,(("request_routing_decision_mean_ms","Routing mean ms",1),("request_routing_decision_p95_ms","Routing p95 ms",1)),POLICIES[1:]),"",
            *table(scale,(("wall_clock_seconds","Wall seconds/run",1),("wall_seconds_per_100k_requests","Seconds/100k requests",1),
            ("total_controller_cpu_ms","Controller CPU ms/run",1),("controller_cpu_ms_per_request","Controller CPU ms/request",1)))]
    lines += ["","controller_overhead_scaling.csv contains nodes, services, mean eligible replicas, requests and routing decisions. Baseline has no explicit routing timer; its zero router fields denote absence of the added mechanism, not measured cost of its shared-FIFO scheduler. "
              "Controller CPU/explicit routing-decision is explicitly undefined for baseline. Fits are descriptive: nodes/services are perfectly collinear and per-service candidate count is capped at three, so no asymptotic complexity proof follows.","",
              "# Negative Seeds","","No outlier or loss seed was removed. Positive difference below means JointSLA is worse (the negative-case export retains comparator-minus-JointSLA sign).","",
              "| Scale | Seed | Metric | SLA-aware | JointSLA | Joint minus baseline |","|---|---:|---|---:|---:|---:|"]
    for r in negative.itertuples():lines.append(f"| {r.scale} | {r.seed} | {NAMES[r.metric]} | {r.sla_aware_value:.6f} | {r.joint_value:.6f} | {-r.difference:.6f} |")
    lines += ["","# Statistical Significance","","Two-sided paired Wilcoxon assumes independent seed pairs and a suitable signed-difference distribution; bootstrap mean CIs complement the location test. Supported benefit requires positive mean, positive lower paired CI and Holm p<0.05.","",
              "| Scale | Metric | Raw p | Holm p | Rank-biserial | Wins/ties/losses | Supported |","|---|---|---:|---:|---:|---|---|"]
    for r in tests.itertuples():lines.append(f"| {r.scale} | {NAMES[r.metric]} | {r.p_value:.3g} | {r.p_value_holm:.3g} | {r.rank_biserial_correlation:.4f} | {r.wins}/{r.ties}/{r.losses} | {'yes' if r.supported_improvement else 'no'} |")
    lines += ["","Secondary ShortestQueue comparisons (separate 12-test Holm family):","","| Scale | Metric | Relative gain (%) | Holm p | Supported |","|---|---|---:|---:|---|"]
    for r in secondary.itertuples():lines.append(f"| {r.scale} | {NAMES[r.metric]} | {r.relative_improvement_percent:.2f} | {r.p_value_holm:.3g} | {'yes' if r.supported_improvement else 'no'} |")
    lines += ["","# Does the JointSLA Advantage Persist?","","| Hypothesis | Predeclared rule supported |","|---|---|"]
    for k in ("H1","H2","H3","H4","H5"):lines.append(f"| {k} | {'yes' if h[k] else 'no'} |")
    lines += ["","H1/H2 require SLA/p95 benefit at all scales. H3 requires both at >=2 scales plus nonnegative LARGE means and <=15 loss seeds. H4 requires mean full control <=10ms, mean per-seed control p95 <=100ms and routing p95 <=1ms at every scale. "
              "H5 requires upper paired bounds for replicas <=5%, VRAM <=2pp and normalized actions <=5%. These separate performance persistence from computational feasibility and comparable resources.","",
              "| Scale | Full controller mean (ms) | Mean seed control p95 (ms) | Mean seed routing p95 (ms) | H4 scale screen |","|---|---:|---:|---:|---|"]
    for r in h["overhead_by_scale"]:lines.append(f"| {r['scale']} | {r['controller_mean_ms']:.3f} | {r['controller_p95_ms']:.3f} | {r['routing_p95_ms']:.3f} | {'pass' if r['passed'] else 'fail'} |")
    lines += ["","Relative gain is compared directly across scales in joint_relative_gain_by_scale.csv. A positive statistically supported LARGE result does not imply unchanged magnitude or linear scaling. "
              "If gain diminishes or budgets fail, fixed action budget, full node/service snapshot construction, queue-estimation error, scarce VRAM and lifecycle bottlenecks are plausible mechanisms, not identified causal explanations.","",
              "Observed mean-gain movement (descriptive; no additional trend significance test):","",
              "| Metric | SMALL relative gain (%) | MEDIUM relative gain (%) | LARGE relative gain (%) | LARGE minus SMALL (pp) |","|---|---:|---:|---:|---:|"]
    for metric in NAMES:
        g=tests.loc[tests.metric==metric].set_index("scale").relative_improvement_percent
        lines.append(f"| {NAMES[metric]} | {g.SMALL:.2f} | {g.MEDIUM:.2f} | {g.LARGE:.2f} | {g.LARGE-g.SMALL:.2f} |")
    lines += ["",
              "# Threats to Validity","",
              "- One synthetic model and horizon; no real workloads, hardware profiling, carrier-scale network or external-validation seeds.",
              "- Independent size-dependent topology/service draws preserve distributions, not identical per-seed instances or exact offered pressure. Tier rounding changes fractions slightly.",
              "- Two actions/slot is global and fixed; resource residency/action bottlenecks may intensify as service count rises.",
              "- Original SLA-aware uses a work-conserving shared FIFO; explicit queues and feedback-dependent deployments differ. Benefit cannot be attributed solely to one routing term.",
              "- The prior no-slack ablation did not establish an additional variance/slack benefit. This study does not change or rehabilitate that claim.",
              "- Latency includes after-horizon drain, while utilization/residency measure the arrival horizon. Eligible and peak replicas are sampled; allocated replica-seconds are exact.",
              "- Wall time includes online audit creation; exports/validation are excluded. Process CPU quantization, monitoring, filesystem and shared-machine activity limit timing interpretation.",
              "- Per-scale confidence intervals are pointwise; the fixed main Holm family controls 12 primary tests. Trends/fits/resources are diagnostic, not causal/asymptotic proofs.","",
              "# Safe Paper Claims","",
              "- The unchanged verified mechanisms were evaluated on common hashed tapes at three proportional scales, with protected baseline artifacts and no post-outcome tuning."]
    for claim in claims:lines.append("- "+claim["sentence"])
    if tests.supported_improvement.all():lines.append("- JointSLA preserved statistically supported reductions in all four primary metrics over SLA-aware across all tested synthetic system scales.")
    lines += ["","# Claims We Cannot Make","","- Production scalable, carrier-grade, globally optimal, real-world validated or linearly scalable.",
              "- Constant gain magnitude, universal resource efficiency, calibrated SLA-risk probability, or additional slack-term benefit without supporting evidence.",
              "- Acceptable computational overhead at a scale that fails the predeclared H4 budget.","",
              "# Implications for B-Level Publication","",
              f"Performance generalization screen H3 is {'supported' if h['H3'] else 'not supported'}; operational overhead screen H4 is {'supported' if h['H4'] else 'not supported'}; "
              f"resource fairness H5 is {'supported' if h['H5'] else 'not supported'}. "
              "Positive persistence strengthens empirical evidence for the coupled mechanism in this model. Failed budgets, loss seeds or shrinking gains qualify that evidence; they are not hidden or repaired by tuning. "
              "Publication readiness and first-in-literature novelty still require broader evaluation and independently verified literature positioning.","",
              "Reproduce: `python run_scalability_experiments.py --seeds 1:30 --reuse-results`; rerun with `--force`. Pilot uses `--pilot`. All detailed exports are local to the new scalability directory."]
    (output/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
