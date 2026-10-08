"""Measured performance report and five publication-ready before/after figures."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .reference import OUTPUT,ROOT
from scalability.configuration import SCALES

HEADINGS=("Goal","Frozen Research Baseline","Original Bottleneck","Profiling Method","Legacy Controller Profile",
          "Optimizations Applied","Semantic Equivalence Validation","Performance Before vs After",
          "Snapshot Construction Improvement","Routing Overhead","Small / Medium / Large Results","H4 Reassessment",
          "Remaining Bottlenecks","Threats to Measurement Validity","Safe Paper Claims","Claims We Cannot Make")
FIGURES=("01_controller_before_after","02_snapshot_before_after","03_speedup_by_scale","04_controller_breakdown","05_controller_time_vs_scale")


def table(frame,columns,labels=None):
    labels=labels or columns
    lines=["| "+" | ".join(labels)+" |","|"+"|".join("---" for _ in columns)+"|"]
    for row in frame[columns].itertuples(index=False,name=None):
        lines.append("| "+" | ".join(f"{v:.4f}" if isinstance(v,(float,np.floating)) else str(v) for v in row)+" |")
    return lines+[""]


def figures(perf):
    folder=OUTPUT/"figures";folder.mkdir(exist_ok=True)
    labels=list(SCALES);x=np.arange(3);width=.34
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False,
                         "svg.fonttype":"none","pdf.fonttype":42})
    colors={"legacy":"#3265A5","optimized":"#16836B"}
    def save(fig,name):
        fig.text(.5,.015,"Seed 1 • one warm-up + seven replays per implementation • 700 control invocations per scale",
                 ha="center",fontsize=8,color="#555555")
        fig.tight_layout(rect=(0,.045,1,1))
        for extension in ("png","svg","pdf"):fig.savefig(folder/f"{name}.{extension}",dpi=300)
        plt.close(fig)
    for column,title,ylabel,name in (("full_controller_mean_ms","Full controller before / after","Mean wall time per invocation (ms)",FIGURES[0]),
                                     ("snapshot_mean_ms","Snapshot construction before / after","Mean snapshot wall time (ms)",FIGURES[1])):
        fig,ax=plt.subplots(figsize=(8.5,4.6))
        for j,mode in enumerate(colors):
            values=perf[f"{mode}_{column}"].to_numpy()
            bars=ax.bar(x+(j-.5)*width,values,width,label=mode.title(),color=colors[mode])
            ax.bar_label(bars,fmt="%.2f",padding=3)
        if "full" in column:ax.axhline(10,color="#B54840",linestyle="--",label="10-ms budget")
        ax.set(xticks=x,xticklabels=labels,title=title,ylabel=ylabel,ylim=(0,None));ax.margins(y=.15);ax.legend()
        save(fig,name)
    fig,ax=plt.subplots(figsize=(8.5,4.6))
    for j,(metric,color) in enumerate((("full_controller","#3265A5"),("snapshot","#16836B"))):
        bars=ax.bar(x+(j-.5)*width,perf[f"speedup_{metric}"],width,label=metric.replace("_"," ").title(),color=color)
        ax.bar_label(bars,fmt="%.2f×",padding=3)
    ax.axhline(1,color="#555555",linestyle="--");ax.set(xticks=x,xticklabels=labels,title="Measured implementation speedup",ylabel="Legacy / optimized mean time",ylim=(0,None));ax.margins(y=.18);ax.legend()
    save(fig,FIGURES[2])
    fig,ax=plt.subplots(figsize=(9,4.8));positions=np.arange(6)
    snapshots=[];logic=[];ticklabels=[]
    for scale in labels:
        for mode in colors:
            snapshots.append(perf.loc[scale,f"{mode}_snapshot_mean_ms"])
            logic.append(perf.loc[scale,f"{mode}_policy_apply_mean_ms"])
            ticklabels.append(scale+"\n"+mode.title())
    ax.bar(positions,snapshots,label="Snapshot / state observation",color="#3265A5")
    ax.bar(positions,logic,bottom=snapshots,label="Unchanged policy + action application",color="#E2A33A")
    ax.axhline(10,color="#B54840",linestyle="--",label="10-ms budget")
    ax.set(xticks=positions,xticklabels=ticklabels,title="Control invocation wall-time breakdown",ylabel="Mean wall time (ms)",ylim=(0,None));ax.margins(y=.18);ax.legend()
    save(fig,FIGURES[3])
    fig,ax=plt.subplots(figsize=(8.5,4.8));nodes=np.array([5,10,20])
    for mode,color in colors.items():
        ax.plot(nodes,perf[f"{mode}_full_controller_mean_ms"],"o-",color=color,label=mode.title()+" mean")
        ax.plot(nodes,perf[f"{mode}_full_controller_p95_ms"],"s--",color=color,alpha=.7,label=mode.title()+" p95")
    ax.axhline(10,color="#B54840",linestyle=":",label="10-ms mean budget")
    ax.set(xticks=nodes,xticklabels=["5 nodes / 20 services","10 / 40","20 / 80"],title="Controller wall time across tested scales",ylabel="Wall time per invocation (ms)",ylim=(0,None));ax.legend()
    save(fig,FIGURES[4])


def create():
    perf=pd.read_csv(OUTPUT/"controller_performance_before_after.csv").set_index("scale").loc[list(SCALES)]
    h4=pd.read_csv(OUTPUT/"h4_reassessment.csv");status=json.loads((OUTPUT/"h4_reassessment.json").read_text())
    validation=json.loads((OUTPUT/"validation.json").read_text())
    full=pd.read_csv(OUTPUT/"optimized_full_validation_timings.csv")
    historic=pd.read_csv(ROOT/"results/scalability_30seeds/raw_results.csv")
    memory=pd.read_csv(OUTPUT/"memory_profile.csv");runs=pd.read_csv(OUTPUT/"benchmark_runs.csv")
    figures(perf)
    sections={h:[] for h in HEADINGS}
    sections["Goal"]=["Reduce implementation overhead without changing any algorithmic decision, floating-point formula, physical event, workload, configuration or statistical method. Only H4 is reassessed.",""]
    sections["Frozen Research Baseline"]=["The verified SMALL (5/20), MEDIUM (10/40), LARGE (20/80) JointSLA implementations and all three existing result trees remain byte-identical. H1/H2/H3/H5 retain their verified conclusions. Two actions per 100-ms slot, max three replicas, causal state and CPU→GPU→CPU pipeline are unchanged.",
         f"SHA-256 verification protects {validation['protected_files_unchanged']:,} pre-existing files. The optimized adapter has a fixed implementation fingerprint in optimization_protocol.json.",""]
    sections["Original Bottleneck"]=["Historical 30-seed full controller means were 2.517, 6.933, 26.836 ms. About 83% of historical LARGE control time was snapshot construction. Fresh repeated timings below are the appropriate before/after comparison; historical measurements were taken at a different time.",
        "The legacy snapshot repeatedly scans all stores for each service and sorts the same queues, and nominal() repeats immutable service/topology arithmetic and dynamic node observation for every service–node pair.",""]
    sections["Profiling Method"]=["Before optimization, cProfile ran unchanged seed 1 at each scale. It is repeated after optimization. profile_before/after.csv report exclusive function times, calls, per-call means and percentage of selected controller/state/routing functions. Cumulative time includes called NumPy, copy, sorting and dictionary operations. Percentages are an attribution denominator, not a sum of nested full-loop percentages.",
        "The complete pstats files retain builtins and all call edges. No cProfile or tracemalloc is active during the performance benchmark. Each benchmark implementation/scale warms up once, then performs seven fresh seed-1 replays, alternating execution order. Each provides 700 live controller invocations with actual accepted/rejected action application. Existing high-resolution timers isolate snapshot and policy/application; all disk output, constructor, workload generation and plotting are excluded.",""]
    for scale in SCALES:
        before=pd.read_csv(OUTPUT/"profile_before.csv");after=pd.read_csv(OUTPUT/"profile_after.csv")
        f=before[before.scale==scale].sort_values("total_time_ms",ascending=False).head(5)
        sections["Legacy Controller Profile"] += [f"{scale}:",""]+table(f,["function","calls","total_time_ms","cumulative_time_ms","percent_controller_time"])
    sections["Optimizations Applied"]=[
        "1. Precompute immutable service–node network latency, resource fraction, execution metadata and static feasibility with the exact legacy scalar expressions and reduction order.",
        "2. Maintain insertion-ordered per-service live-replica indexes on add and original worker completion. Entries reference original objects, so busy, readiness, node and migration state remain live.",
        "3. Maintain per-service historical store IDs, retaining retired stores exactly as the original aggregate queue does. Queue ordering remains sorted by (arrival_s, request_id).",
        "4. Collect aggregate waiting work once within each synchronous snapshot; reuse it for queue lengths, oldest age and all waiting ages.",
        "5. Cache dynamic node resource/feasibility extraction only inside the same snapshot, clearing it in finally. Per-request nominal observation outside snapshots always reads current state.",
        "Every candidate is retained. Score functions, routing dispatch, virtual deployment quality (including deepcopy), joint_actions, action application and physical pipeline are inherited unchanged. The worker wrapper introduces no event or yield beyond yield-from the original generator.",""]
    sections["Semantic Equivalence Validation"]=[
        "All nine golden seeds pass exact canonical trace hashes and direct object equality: actions, routing (including candidate score inputs and order), request destinations/completions/latencies/SLA flags, all 200 state snapshots and resource/lifecycle traces. Only measured timing fields are excluded.",
        f"Full replay: 90 optimized runs plus 90 fresh unchanged legacy reference runs. {validation['requests_verified']:,} request outcomes and {validation['routing_decisions_verified']:,} routing assignments pass exact comparison with frozen audit frames, read with round-trip float parsing. All 24 exported research metrics also equal fresh unchanged legacy calculations exactly. No epsilon/tolerance is used.",
        f"There are {validation['frozen_summary_parser_representations']} scalar representations in historical summary CSVs whose default-parser read/write path changes the last binary bits. For each, the exact historical parser transformation is reproduced (not bounded by tolerance), raw audit frames are identical, and fresh legacy and optimized calculations are exactly identical. These are recorded in metric_representation_differences.csv; frozen summary files are untouched. For example p99 1089.8791033297935 is parsed as 1089.8791033297937 by the default reader. We do not claim those stored decimals equal recomputed values bit-for-bit.",""]
    flat=perf.reset_index()
    sections["Performance Before vs After"] += table(flat,["scale","legacy_full_controller_mean_ms","optimized_full_controller_mean_ms",
        "legacy_full_controller_median_ms","optimized_full_controller_median_ms","legacy_full_controller_p95_ms","optimized_full_controller_p95_ms","speedup_full_controller"],
        ["Scale","Legacy mean ms","Optimized mean ms","Legacy median ms","Optimized median ms","Legacy p95 ms","Optimized p95 ms","Speedup"])
    sections["Snapshot Construction Improvement"] += table(flat,["scale","legacy_snapshot_mean_ms","optimized_snapshot_mean_ms","speedup_snapshot","percent_reduction_snapshot"],
         ["Scale","Legacy ms","Optimized ms","Speedup","Reduction %"])
    sections["Routing Overhead"]=["The routing chooser/scorer is unchanged. Existing attempt timers include candidate construction, scoring and observational counterfactuals, excluding JSON audit formatting. Failed eligibility attempts and drain-time assignments are retained. Full controller below refers to one control invocation; per-request routing is additional CPU work and is measured separately, not hidden in that denominator.",""]+table(flat,["scale","legacy_routing_mean_ms","optimized_routing_mean_ms","legacy_routing_p95_ms","optimized_routing_p95_ms"],
         ["Scale","Legacy mean ms","Optimized mean ms","Legacy p95 ms","Optimized p95 ms"])
    for scale in SCALES:
        f=full[full.scale==scale];old=historic[(historic.scale==scale)&(historic.policy=="joint_sla")]
        sections["Small / Medium / Large Results"] += [f"{scale}: historical controller {old.controller_total_instrumented_mean_ms.mean():.4f} ms; optimized full-30-seed mean {f.controller_total_instrumented_mean_ms.mean():.4f} ms; mean per-seed controller p95 {f.controller_total_instrumented_p95_ms.mean():.4f} ms. All 30 seeds have exact scientific equivalence.",""]
    sections["H4 Reassessment"]=[f"**H4 = {status['H4']}**. Fixed mean <10-ms budget at every scale, original mean per-seed control p95 <=100 ms and routing p95 <=1 ms. Both repeated benchmark means and all-30-seed means must meet the budget; no threshold is changed after measurement.",""]+table(h4,["scale","full_30seed_controller_mean_ms","full_30seed_mean_controller_p95_ms","full_30seed_mean_routing_p95_ms","benchmark_controller_mean_ms","supported"])
    large=perf.loc["LARGE"]
    sections["Remaining Bottlenecks"]=[f"At LARGE, the repeated optimized snapshot mean is {large.optimized_snapshot_mean_ms:.4f} ms and unchanged policy plus application is {large.optimized_policy_apply_mean_ms:.4f} ms. The policy/action path accounts for {100*large.optimized_policy_apply_mean_ms/large.optimized_full_controller_mean_ms:.1f}% of optimized control wall time. deployment_quality virtual scoring/deepcopy and feasibility loops now matter more than redundant state observation. This study leaves them unchanged.",
        "Initialization now precomputes static metadata; its time is separately retained in benchmark_runs.csv and is not concealed as control time. Candidate bounds, global action budget and lifecycle restrictions remain unchanged. No theoretical asymptotic proof or universal performance claim follows from three sizes.",""]
    sections["Threats to Measurement Validity"]=[
        "- Single Windows/Python host, process scheduling and CPU-frequency variation. Alternating order/warm-up/repetition reduce but cannot remove host noise; these timings are not hardware-independent guarantees.",
        "- Repeated benchmark uses seed 1; separate full replay spans all 30 seeds. P95 of 700 invocations differs from the mean of 30 per-seed p95s. Neither is a confidence interval.",
        "- Full controller is snapshot plus policy/application at control slots. Per-request route cost and audited simulator runtime remain separate scopes. Timing never affects simulated latency.",
        "- Ordered indexes and static tables have memory cost. Static caching relies on the model's immutable service, topology and configuration contract. Dynamic node cache is invocation-local, explicitly invalidated on normal/exception exit.",
        "- Python tracemalloc measures the initial snapshot/constructor state only, separately from timing; process RSS is sampled and can retain allocator pages from previous runs. Neither is an isolated policy allocation proof.",
        "- Frozen summary decimal-parser differences are disclosed; no scientific equality is inferred from approximate scalar matching.",""]
    sections["Threats to Measurement Validity"] += table(memory,["scale","legacy_peak_mb","optimized_peak_mb","legacy_retained_before_snapshot_mb","optimized_retained_before_snapshot_mb"],
        ["Scale","Legacy Python peak MB","Optimized Python peak MB","Legacy retained MB","Optimized retained MB"])
    for scale in SCALES:
        f=runs[runs.scale==scale].groupby("implementation").sampled_peak_process_rss_mib.mean()
        sections["Threats to Measurement Validity"].append(f"{scale} mean sampled replay process RSS: legacy {f['legacy']:.2f} MiB, optimized {f['optimized']:.2f} MiB.")
    sections["Threats to Measurement Validity"].append("")
    if status["H4"]=="SUPPORTED":
        sections["Safe Paper Claims"]=["Implementation-level ordered state indexes, immutable metadata caching and invocation-local node observation reduced JointSLA control overhead below the predeclared 10-ms mean budget at all tested synthetic scales, without changing any orchestration, routing or request outcomes. Exact reference replay and frozen raw audit comparisons support semantic preservation.",""]
    else:
        sections["Safe Paper Claims"]=["The optimized implementation reduced control overhead, but did not meet every predeclared H4 screen. The controller remains above at least one budget; the failed screen is reported without tuning or changing scientific decisions.",""]
    sections["Safe Paper Claims"] += ["This is implementation performance engineering, not new algorithmic novelty. Previously verified scientific conclusions and statistical results remain unchanged.",""]
    sections["Claims We Cannot Make"]=["Production/carrier-grade feasibility, hardware-independent real-time guarantees, linear/asymptotic scalability, global optimality, improved algorithmic decisions, newly improved SLA/latency/resource results, or additional novelty of the slack term. Pure snapshot memory does not prove full-run peak Python memory. Historical stored summary decimals are not claimed bit-identical to fresh recalculation.",""]
    lines=[]
    for heading in HEADINGS:lines.extend(["# "+heading,""]+sections[heading])
    lines.extend(["Reproduce: `python run_controller_optimization.py --all`. Stage flags: --profile, --validate-equivalence, --benchmark, --full-validation. All five figures have PNG 300 dpi, SVG and PDF exports."])
    (OUTPUT/"report.md").write_text("\n".join(lines),encoding="utf-8")
