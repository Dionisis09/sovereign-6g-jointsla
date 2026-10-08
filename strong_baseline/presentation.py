"""Twelve exportable research figures and a source-backed publication report."""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scalability.configuration import SCALES
from .protocol import OUTPUT

LABELS={"sla_aware":"SLA-aware", "joint_sla":"JointSLA", "mjo":"MJO"}
COLORS={"sla_aware":"#7B8794", "joint_sla":"#1565C0", "mjo":"#D55E00"}
ORDER=("sla_aware","mjo","joint_sla")
HEADINGS=("Research Question","Frozen Verified Baseline","Strong Baseline Motivation","Optimization Formulation",
 "Information Available to the Controller","Objective","Constraints","Fixed Hyperparameters / Weights","Solver","Pilot",
 "Correctness Validation","Small Results","Medium Results","Large Results","SLA Comparison","Mean / p95 / p99",
 "Gold / Silver / Bronze","Resource Cost","Reconfiguration Cost","Controller and Solver Overhead","Performance-Complexity Trade-Off",
 "Statistical Tests","Negative Seeds","Solver Failures / Timeouts","B1-B5 Results","Threats to Validity","Safe Paper Claims",
 "Claims We Cannot Make","Implications for B-Level Publication")


def table(headers,rows):
    return "| "+" | ".join(headers)+" |\n| "+" | ".join("---" for _ in headers)+" |\n"+"\n".join("| "+" | ".join(str(v) for v in r)+" |" for r in rows)


def create():
    raw=pd.read_csv(OUTPUT/"raw_results.csv",float_precision="round_trip")
    summary=pd.read_csv(OUTPUT/"summary_statistics.csv",float_precision="round_trip").set_index(["scale","policy","metric"])
    tests=pd.read_csv(OUTPUT/"paired_tests.csv",float_precision="round_trip")
    secondary=pd.read_csv(OUTPUT/"secondary_paired_tests.csv",float_precision="round_trip")
    overhead=pd.read_csv(OUTPUT/"overhead_paired_tests.csv",float_precision="round_trip")
    hypotheses=json.loads((OUTPUT/"hypotheses.json").read_text())
    pilot=json.loads((OUTPUT/"pilot_validation.json").read_text());execution=json.loads((OUTPUT/"execution.json").read_text())
    figure_dir=OUTPUT/"figures";figure_dir.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"white"})
    def save(fig,name):
        fig.tight_layout()
        for suffix in ("png","svg","pdf"):fig.savefig(figure_dir/f"{name}.{suffix}",dpi=300,bbox_inches="tight")
        plt.close(fig)
    def bars(ax,metric,label,policies=ORDER,factor=1):
        x=np.arange(3);width=.24 if len(policies)==3 else .34
        for i,policy in enumerate(policies):
            rows=[summary.loc[(s,policy,metric)] for s in SCALES];means=np.array([r["mean"] for r in rows])*factor
            ci=np.array([[max(0.,r["mean"]-r.ci95_lower) for r in rows],[max(0.,r.ci95_upper-r["mean"]) for r in rows]])*factor
            ax.bar(x+(i-(len(policies)-1)/2)*width,means,width,label=LABELS[policy],color=COLORS[policy],yerr=ci,capsize=3)
        ax.set_xticks(x,SCALES);ax.set_ylabel(label);ax.grid(axis="y",alpha=.18);ax.set_axisbelow(True)
    specs=(("01_sla_joint_vs_mjo","sla_breach_rate","SLA breaches (% offered)",100),
           ("02_mean_latency_joint_vs_mjo","mean_request_latency_ms","Mean request latency (ms)",1),
           ("03_p95_joint_vs_mjo","p95_latency_ms","Per-run p95 latency (ms)",1),
           ("04_p99_joint_vs_mjo","p99_latency_ms","Per-run p99 latency (ms)",1),
           ("06_replicas_comparison","average_replicas","Mean allocated replicas",1),
           ("07_vram_comparison","mean_gpu_vram_reserved_pct","Mean reserved VRAM (%)",1),
           ("08_actions_comparison","actions_per_1000_requests","Actions / 1,000 offered requests",1))
    for name,metric,label,factor in specs:
        fig,ax=plt.subplots(figsize=(8,4.2));bars(ax,metric,label,factor=factor);ax.legend(ncol=3)
        ax.set_title("30 paired seeds per scale · bars: seed means · intervals: 95% bootstrap CI")
        save(fig,name)
    fig,axes=plt.subplots(1,3,figsize=(13,4),sharey=True)
    for ax,tier in zip(axes,("Gold","Silver","Bronze")):
        bars(ax,tier+"_breach_rate","SLA breaches (%)",factor=100);ax.set_title(tier)
    axes[-1].legend(fontsize=8);fig.suptitle("Per-tier SLA breaches · seed means and 95% bootstrap intervals")
    save(fig,"05_gold_silver_bronze")
    fig,axes=plt.subplots(1,2,figsize=(11,4.2))
    bars(axes[0],"controller_total_instrumented_mean_ms","Full controller mean (ms)",("joint_sla","mjo"))
    bars(axes[1],"controller_cpu_ms_per_request","Total controller CPU (ms / offered request)",("joint_sla","mjo"))
    axes[0].legend();fig.suptitle("Fresh primary-policy timings · snapshot + policy + apply; total CPU also includes routing")
    save(fig,"09_controller_overhead")
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,metric,factor,label in zip(axes,("sla_breach_rate","p95_latency_ms"),(100,1),("SLA breaches (%)","Per-run p95 latency (ms)")):
        for policy in ("joint_sla","mjo"):
            for scale,marker in zip(SCALES,("o","s","^")):
                x=summary.loc[(scale,policy,"controller_total_instrumented_mean_ms"),"mean"]
                y=summary.loc[(scale,policy,metric),"mean"]*factor
                ax.scatter(x,y,color=COLORS[policy],marker=marker,s=70)
                offset=(4,5)
                if metric=="p95_latency_ms" and policy=="joint_sla":
                    offset=(4,18) if scale=="SMALL" else (4,-18) if scale=="MEDIUM" else offset
                ax.annotate(f"{LABELS[policy]} {scale}",(x,y),xytext=offset,textcoords="offset points",fontsize=8)
        ax.set_xlabel("Full controller mean (ms)");ax.set_ylabel(label);ax.margins(.3);ax.set_xlim(left=0);ax.grid(alpha=.18)
    fig.suptitle("Observed performance–computation trade-off; descriptive, not an efficiency law")
    save(fig,"10_performance_vs_controller_cost")
    fig,ax=plt.subplots(figsize=(8,4.2))
    for metric,label,marker in (("solver_mean_ms","Mean solve time","o"),("solver_p95_ms","Mean of per-run p95 solve times","s")):
        rs=[summary.loc[(s,"mjo",metric)] for s in SCALES];v=np.array([r["mean"] for r in rs])
        ci=np.array([[max(0,r["mean"]-r.ci95_lower) for r in rs],[max(0,r.ci95_upper-r["mean"]) for r in rs]])
        ax.errorbar(np.arange(3),v,yerr=ci,marker=marker,capsize=3,label=label)
    ax.set_xticks(np.arange(3),SCALES);ax.set_ylabel("Solver time per invocation (ms)");ax.legend()
    ax.set_title("MJO matching and deployment invocations · 95% seed bootstrap CI");ax.grid(alpha=.18)
    save(fig,"11_solver_time_vs_scale")
    fig,axes=plt.subplots(1,3,figsize=(13,4),sharey=True)
    for ax,scale in zip(axes,SCALES):
        f=tests[tests.scale==scale];x=np.arange(4);base=np.zeros(4)
        for col,label,color in (("wins","JointSLA win","#1565C0"),("ties","Tie","#AAAAAA"),("losses","MJO win","#D55E00")):
            ax.bar(x,f[col],bottom=base,label=label,color=color);base+=f[col].to_numpy()
        ax.set_xticks(x,("SLA","Mean","p95","p99"));ax.set_title(scale);ax.set_ylim(0,33)
    axes[0].set_ylabel("Paired seeds");axes[-1].legend(fontsize=8)
    fig.suptitle("All 30 seeds retained · lower metric wins · 12-decimal sign convention")
    save(fig,"12_wins_losses_by_scale")

    def cell(scale,policy,metric,factor=1):
        r=summary.loc[(scale,policy,metric)]
        return f"{r['mean']*factor:.2f} ± {r.standard_deviation*factor:.2f} [{r.ci95_lower*factor:.2f}, {r.ci95_upper*factor:.2f}]"
    def comparison(metrics,policies=ORDER):
        return table(["Scale","Policy",*[m[1] for m in metrics]],
            [[s,LABELS[p],*[cell(s,p,m[0],m[2]) for m in metrics]] for s in SCALES for p in policies])
    def stats(frame):
        return table(["Scale","Metric","B−A [95% CI]","Relative gain % [95% CI]","Wilcoxon W","p","Holm p","RBC","W/T/L"],
            [[r.scale,r.metric,f"{r.absolute_difference:.6g} [{r.difference_ci95_lower:.6g}, {r.difference_ci95_upper:.6g}]",
              f"{r.relative_improvement_percent:.2f} [{r.relative_ci95_lower:.2f}, {r.relative_ci95_upper:.2f}]",
              f"{r.test_statistic:g}",f"{r.p_value:.6g}",f"{r.p_value_holm:.6g}",f"{r.rank_biserial_correlation:.3f}",f"{r.wins}/{r.ties}/{r.losses}"] for r in frame.itertuples()])
    sections={}
    sections["Research Question"]="Does JointSLA retain a meaningful advantage against a substantially stronger optimization-based joint placement/routing comparator, under the same causal information and physical constraints? The primary comparison is JointSLA–MJO; MJO–SLA-aware is the baseline-strength sanity check. All outcome directions are retained."
    sections["Frozen Verified Baseline"]="All four previous result trees and verified simulator/controller sources are protected by `protected_hashes.json`. Every new JointSLA run is compared exactly against nine historical scientific CSV families, excluding timing columns only. The optimized JointSLA implementation is inherited unchanged. Scientific SLA-aware measurements are reused for 90 verified runs; its timing measurements remain historical and are not evidence for the fresh primary overhead comparison."
    sections["Strong Baseline Motivation"]="MJO is a literature-inspired constrained optimization comparator, not an exact reproduction of any published algorithm. It evaluates deployment options through the same current-backlog assignment cost and chooses resource-coupled actions. Its strength label is conditional on predeclared B1. No unsupported technical citations or empirical literature percentages are used. See `strong_baseline/LITERATURE_MAPPING.md`."
    sections["Optimization Formulation"]="For each service, binary y[q,r,k] assigns each already-arrived waiting request to one ordered capacity slot k of an eligible replica r. Each 64-request block solves a rectangular linear assignment. Blocks process oldest-arrival/request-ID order and accumulate assignments. In-flight work is preserved; within-replica FIFO and physical workers are unchanged.\n\nAt a control instant, enumerate no-op, feasible scale-out, idle scale-in and migration menus. Recompute matching under each virtual deployment with cold/downtime availability delays. Binary z[s,a] selects at most one option per service and at most two globally, minimizing additive incremental costs subject to simultaneous reservation headroom. This is exact over the finite additive menu when completed. It does not optimize cross-service interference nonlinearly or the complete stochastic horizon."
    sections["Information Available to the Controller"]="Current queues, already-arrived request ages, deadlines/priorities, replica lifecycle flags, reservations, CPU/GPU availability, network/bandwidth and completed-work empirical estimates. Identical lifecycle telemetry is added to the new wrappers of both primary policies and charged to observation time. No future arrivals, bursts, completions or hidden per-request work factor are read by optimization. Causality tests alter future traffic and future work without changing prefix decisions."
    sections["Objective"]="For candidate slot: Q=(existing modeled queue + assignments + k)×observed cycle + remaining busy time; C=request age + availability delay + Q + network + CPU→GPU→CPU execution + observable resource waiting + lifecycle penalty. Routing cost = priority × [max(0,C/deadline−1) + C/deadline] + 0.25 Q/deadline. The convex lateness term is a surrogate, not a calibrated SLA breach probability. Allocation cost adds 0.35 × sum((CPU fraction + VRAM fraction)/2); scale/cold and migration costs add 0.25 × lifecycle delay/deadline. Scale-in has a fixed nominal execution-cost term."
    sections["Constraints"]="Same finite CPU tokens, GPU compute scheduler, VRAM and bandwidth reservation limits; same max-three-replica/service limit, cooldown, two actions/slot and service compatibility. Cold, retiring and pending-migration replicas cannot receive committed routing. Positive instantaneous reservations are combined across chosen actions; no credit is borrowed from future removal/source release. GPU execution contention remains enforced by the unchanged physical scheduler. All offered requests have exactly one terminal outcome."
    sections["Fixed Hyperparameters / Weights"]="Before pilot outcomes: SLA=1, latency=1, congestion=0.25, resource=0.35, cold/scale=0.25, migration=0.25; block size=64; deployment pair-work limit=50,000. No coefficient was tuned on pilot or final seeds. Operational competitive screen: upper paired-bootstrap deterioration ≤5% for SLA/tails, predeclared uniformly from the previous p99 tolerance. B5 bounds: replicas/actions +5%, VRAM +2 percentage points. These screens do not prove statistical equivalence. Frozen details: `baseline_configuration.json`."
    sections["Solver"]="SciPy `linear_sum_assignment` (modified Jonker–Volgenant implementation) solves each matching block. A specialized deterministic budget-two integer enumeration with valid lower-bound pruning chooses deployment actions. 'Optimal' means exact for that finite subproblem, not globally optimal routing of all future requests. Pair-work limit exhaustion is recorded as timeout with deterministic no-op. Routing failure retains prior queued assignments and pending arrivals. There is no JointSLA fallback and no wall-clock decision cutoff."
    estimates="; ".join(f"{s}: {pilot['estimated_full_seconds'][s]/60:.2f} min" for s in SCALES)
    sections["Pilot"]=f"27 policy runs (three seeds × three scales × three policies) plus nine repeated MJO runs. Corrected export pilot elapsed {pilot['wall_seconds']/60:.2f} min; maximum sampled RSS {pilot['maximum_rss_mib']:.1f} MiB. All nine MJO semantic trace hashes repeated exactly. Printed estimates before main execution: {estimates}; total {pilot['estimated_total_seconds']/60:.2f} min. Initial pilot export validation rejected nonexistent-node NaNs in the combined table; node profiles now remain in their actual-scale trajectories. Model/objective weights were unchanged."
    sections["Correctness Validation"]=f"171 tests passed: the original 160 plus 11 new MJO tests. Full experiment: 180 fresh primary runs + 90 verified SLA-aware runs = 270 paired observations. Main replay/export wall time {execution['full_wall_seconds']/60:.2f} min. Fresh runs account for {execution['requests_verified']:,} request outcomes. `validation.json` independently reconstructs all 270 request exports, components, reservations, lifecycle, tier metrics, batch costs, causal request ages, final routing and inference. Numeric reconstruction tolerances apply to derived sums/quantiles; frozen JointSLA scientific-frame comparison is exact. Causal timestamp comparisons allow 1e-12 seconds for cumulative SimPy floating arithmetic: an initial main attempt detected a 6.94e-18-second discrepancy already present in frozen SMALL seed 15. The guard was corrected and the pilot/main replay restarted; decisions, event timestamps and weights were unchanged. Tests do not prove safety for all possible workloads."
    for scale,title in zip(SCALES,("Small Results","Medium Results","Large Results")):
        sections[title]=table(["Policy","SLA %","Mean ms","p95 ms","p99 ms"],[[LABELS[p],cell(scale,p,"sla_breach_rate",100),cell(scale,p,"mean_request_latency_ms"),cell(scale,p,"p95_latency_ms"),cell(scale,p,"p99_latency_ms")] for p in ORDER])+"\n\nCells: seed mean ± sample SD [95% bootstrap CI of mean]."
    sections["SLA Comparison"]=comparison((("sla_breach_rate","SLA breach %",100),))+"\n\nEvery offered request is in the SLA denominator; failed placement/admission counts as breach. No policy admission/drop advantage is introduced."
    sections["Mean / p95 / p99"]=comparison((("mean_request_latency_ms","Mean ms",1),("median_latency_ms","Median ms",1),("p95_latency_ms","p95 ms",1),("p99_latency_ms","p99 ms",1)))+"\n\nLatencies include network, service and node queues, execution, lifecycle penalties and completions after the arrival horizon. Quantiles are calculated within each run; table intervals describe the mean of these seed-level quantiles."
    sections["Gold / Silver / Bronze"]=comparison(tuple((t+"_breach_rate",t+" SLA %",100) for t in ("Gold","Silver","Bronze")))+"\n\n"+comparison(tuple((t+"_mean_latency_ms",t+" mean ms",1) for t in ("Gold","Silver","Bronze")))+"\n\n"+comparison(tuple((t+"_p95_latency_ms",t+" p95 ms",1) for t in ("Gold","Silver","Bronze")))+"\n\nTier differences are descriptive; the primary Holm family does not establish tier-specific significance. Gold disadvantages remain visible."
    sections["Resource Cost"]=comparison((("average_replicas","Allocated replicas",1),("peak_replicas","Peak replicas",1),("mean_gpu_vram_reserved_pct","Reserved VRAM %",1)))+"\n\n"+comparison((("average_cpu_utilization","CPU %",100),("average_gpu_utilization","GPU %",100),("replicas_per_service","Replicas/service",1)))+"\n\nAllocated integral includes cold/retiring replicas. Utilization averages equally weight node-slots; capacity-weighted pool utilization is also exported. Resource diagnostic inference is explicitly exploratory."
    sections["Reconfiguration Cost"]=comparison((("total_actions","Total actions",1),("cold_starts","Cold starts",1),("migrations","Migrations",1),("actions_per_1000_requests","Actions/1,000",1)))
    sections["Controller and Solver Overhead"]=comparison((("controller_total_instrumented_mean_ms","Full controller mean ms",1),("controller_full_median_ms","Median ms",1),("controller_total_instrumented_p95_ms","p95 ms",1)),("joint_sla","mjo"))+"\n\n"+comparison((("controller_cpu_ms_per_request","Total CPU ms/request",1),("controller_ms_per_1000_requests","Total CPU ms/1,000",1),("solver_mean_ms","Solver mean ms",1),("solver_p95_ms","Solver p95 ms",1)),("joint_sla","mjo"))+"\n\nFull controller wall time is snapshot + policy + apply at each control instant; total controller CPU also includes event-time routing and audit instrumentation. MJO routing callbacks optimize batches/reassign backlog; JointSLA callbacks assign individual requests. Native routing callback mean/p95 have different units of work and must not be directly interpreted as per-request speed. The common offered-request CPU denominator is exported. Historical SLA-aware host timings are excluded from fresh overhead claims."
    trade=pd.read_csv(OUTPUT/"performance_complexity.csv")
    sections["Performance-Complexity Trade-Off"]=table(["Scale","Policy","SLA %","p95 ms","Full controller ms","CPU ms/request","SLA gain pp/controller ms"],[[r.scale,LABELS[r.policy],f"{100*r.sla_breach_rate:.2f}",f"{r.p95_ms:.2f}",f"{r.full_controller_mean_ms:.3f}",f"{r.controller_cpu_ms_per_request:.4f}",f"{r.sla_improvement_pp_per_controller_ms:.3f}"] for r in trade.itertuples()])+"\n\nThe last column is descriptive against historical SLA-aware outcomes. Audit-heavy batch processing and Python overhead are included; it is not a universal efficiency law or a scalability bound."
    sections["Statistical Tests"]="30 paired seeds per scale; 10,000 seed-bootstrap percentile resamples; two-sided Wilcoxon with differences rounded to 12 decimals; exact p without ties/zeros, otherwise tie-adjusted asymptotic p; Holm families of 12 primary, 12 strength-sanity, three overhead tests. Positive B−A, relative gain and rank-biserial effect indicate policy A improvement. SLA absolute differences here use fractions; ×100 converts to percentage points.\n\nPrimary A=JointSLA, B=MJO:\n\n"+stats(tests)+"\n\nSecondary A=MJO, B=SLA-aware:\n\n"+stats(secondary)+"\n\nOverhead A=JointSLA, B=MJO:\n\n"+stats(overhead)
    negative=pd.read_csv(OUTPUT/"negative_seed_cases.csv")
    sections["Statistical Tests"]+="\n\nRank-test significance and a bootstrap CI for the mean difference need not agree: they summarize different aspects of these seed differences. The unchanged supported-improvement rule requires both Holm p<.05 and a positive paired mean lower bound. For LARGE p95 the mean favors MJO and Holm p<.05, but its paired mean CI includes zero; this remains mixed evidence. LARGE p99 has both a negative paired mean CI and Holm p<.05, supporting the MJO advantage in that metric."
    sections["Negative Seeds"]=f"{len(negative)} metric/seed losses for JointSLA across 360 primary paired metric observations; all are retained in `negative_seed_cases.csv`. Counts below refer to metric cases, not distinct seeds.\n\n"+table(["Scale","Metric","Joint W/T/L"],[[r.scale,r.metric,f"{r.wins}/{r.ties}/{r.losses}"] for r in tests.itertuples()])
    m=raw[raw.policy=="mjo"]
    sections["Solver Failures / Timeouts"]=table(["Scale","Calls","Optimal","Feasible","Timeout","Infeasible","Fallback"],[[s,*[int(m[m.scale==s][col].sum()) for col in ("solver_calls","solver_optimal_calls","solver_feasible_calls","solver_timeout_calls","solver_infeasible_calls","solver_fallback_calls")]] for s in SCALES])+"\n\nNo-eligible-replica matching is classified as infeasible and preserves queued/pending work. Every other failure is also recorded, not discarded. Consult per-run `solver.csv.gz` for context, reason, matrix/block sizes and deterministic work limits."
    sections["B1-B5 Results"]=table(["Hypothesis","Result"],[[b,"PASS" if hypotheses[b] else "NOT SUPPORTED"] for b in ("B1","B2","B3","B4","B5")])+"\n\n"+table(["Scale","Replica increase upper %","VRAM increase upper pp","Action increase upper %","B5 screen"],[[r["scale"],f"{r['average_replicas_relative_upper']:.2f}",f"{r['vram_pp_upper']:.2f}",f"{r['actions_per_1000_requests_relative_upper']:.2f}",r["passed"]] for r in hypotheses["resource_screens"]])+"\n\n"+("MJO satisfies the predeclared all-scale stronger-baseline gate." if hypotheses["B1"] else "MJO does not satisfy the predeclared all-scale stronger-baseline gate. This is a baseline-design limitation/failure, not evidence that JointSLA defeated a verified strong optimizer.")
    if not hypotheses["B1"]:
        failed=secondary[secondary.metric.isin(("sla_breach_rate","p95_latency_ms"))&~secondary.supported_improvement]
        sections["B1-B5 Results"]+="\n\nFailed strength-gate components (A=MJO, B=SLA-aware):\n\n"+stats(failed)
    sections["B1-B5 Results"]+="\n\nQueue-component diagnostics:\n\n"+comparison((("average_service_queue_ms","Service queue mean ms",1),("average_node_queue_ms","Node queue mean ms",1)))+"\n\nThese observed waiting components and tier/resource trade-offs describe where delays differ; they do not identify a causal mechanism. Candidate estimates hold observed shared-resource waiting fixed, action deltas are additive, and no future request demand is optimized. Consequently exact subproblem solutions can still be inferior under later nonlinear contention. The convex priority-weighted objective targets neither the unweighted breach indicator nor p95/p99 directly. Further improvements require a separately preregistered experiment, not retuning these results. Secondary metric/seed losses are retained in `baseline_strength_negative_cases.csv`."
    sections["Threats to Validity"]="Three synthetic scales and 30 seeds do not represent live telco infrastructure. A current-state convex lateness surrogate can misestimate stochastic contention; oldest-first matching decomposition and additive deployment deltas omit cross-service nonlinear interference. Current-backlog reoptimization does more routing work than JointSLA, preserving workers but changing destination choices. Weights are fixed, not empirically optimal. Pilot seeds overlap the final 30 but are used only for correctness/runtime, without tuning. Timing is sequential on one laptop with instrumentation and host variability; no cross-policy repeated timing crossover was performed. RSS is sampled, not an exact peak. Failure classification includes transient no-eligible states. B2/B3/B5 are predeclared operational bootstrap screens, not formal equivalence/causal mediation tests."
    claims=[]
    for r in tests.itertuples():
        if r.supported_improvement:claims.append(f"At {r.scale}, JointSLA improves {r.metric} over this MJO implementation by {r.relative_improvement_percent:.2f}% (Holm p={r.p_value_holm:.6g}, positive paired lower CI).")
        elif r.relative_improvement_percent<0 and r.p_value_holm<.05 and r.difference_ci95_upper<0:claims.append(f"At {r.scale}, MJO improves {r.metric}; JointSLA relative gain is {r.relative_improvement_percent:.2f}% (Holm p={r.p_value_holm:.6g}, negative paired upper CI).")
    if hypotheses["B4"]:claims.append("JointSLA has lower full-controller mean at all tested scales in the separate Holm-corrected overhead family.")
    if not hypotheses["B1"]:claims.append("The stronger-baseline sanity gate failed; comparisons characterize this implementation, not verified superiority over a strong optimization baseline.")
    sections["Safe Paper Claims"]="\n\n".join(claims)
    sections["Claims We Cannot Make"]="Global stochastic optimality, state-of-the-art performance, universal superiority, carrier-grade/production readiness, exact paper replication, formally proved equivalence, causal resource explanations or a guaranteed B-level acceptance. No post-results JointSLA or MJO tuning occurred. A failed B1 cannot be turned into a strong-baseline victory."
    sections["Implications for B-Level Publication"]=("The stronger-comparator evidence can support a bounded performance-computation argument, subject to the observed B2–B5 and tier results." if hypotheses["B1"] else "This experiment supplies reproducible adversarial evidence but does not establish the requested stronger-baseline comparison. The baseline design and surrogate need independent further study in a separately preregistered experiment; the present negative results must remain unchanged.")+" Acceptance depends on external review, novelty, model validity and broader evidence. Existing frozen results remain valid for their previous comparisons.\n\nReproduce:\n\n```powershell\n.venv\\Scripts\\python.exe -m pytest -q\n.venv\\Scripts\\python.exe run_strong_baseline.py --pilot --force\n.venv\\Scripts\\python.exe run_strong_baseline.py --seeds 1:30 --force\n.venv\\Scripts\\python.exe run_strong_baseline.py --seeds 1:30 --reuse-results\n```\n\nAll 12 figures are provided as 300-dpi PNG and vector SVG/PDF. All numeric tables have seed-level mean ± SD and bootstrap intervals; raw/request/audit data remain available."
    (OUTPUT/"report.md").write_text("\n\n".join("# "+h+"\n\n"+sections[h] for h in HEADINGS)+"\n",encoding="utf-8")
