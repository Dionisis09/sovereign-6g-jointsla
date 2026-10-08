"""Frozen seed-level analysis, declared families, plots and candid final report."""
import json
import numpy as np
import pandas as pd
from paper_evaluation.statistics import summarize,bootstrap_mean_ci,signed_rank,holm_adjust,rng_for
from hardware_grounded.environment import write_json
from hardware_pressure.analysis import RESOURCE,QUEUE,PRESSURE,table,burst_summary
from .protocol import POLICIES,read,verify_freeze
from .validation import verify_study

LABELS={'sla_aware':'SLA-aware','joint_sla_v1':'JointSLA-v1','joint_sla_v2':'JointSLA-v2'}
PRIMARY=('sla_breach_rate','Gold_breach_rate','p95_latency_ms')
SECONDARY=('mean_request_latency_ms','p99_latency_ms','Silver_breach_rate','Bronze_breach_rate','average_replicas','average_vram_residency_gib','total_actions')
FIGURES=('01_sla_1x','02_gold_1x','03_p95_1x','04_sla_2x','05_p95_2x','06_p99_2x','07_replicas','08_vram','09_actions','10_sla_vs_replicas','11_gold_vs_replicas','12_p95_vs_vram','13_ready_replicas_before_burst','14_recovery_breaches','15_controller_overhead')

def paired(raw):
    rows=[];differences=[]
    for comparator in ('joint_sla_v1','sla_aware'):
        for load,g in raw.groupby('load_multiplier'):
            for metric in PRIMARY+SECONDARY:
                p=g.pivot(index='seed',columns='policy',values=metric).sort_index()
                a=p.joint_sla_v2.to_numpy();b=p[comparator].to_numpy();d=a-b;sign=np.round(d,12)
                key=f'jointsla-v2:{comparator}:{load}:{metric}'
                lo,hi=bootstrap_mean_ci(d,key=key)
                rows.append(dict(load_multiplier=load,comparator=comparator,metric=metric,n=len(d),mean_v2=float(a.mean()),mean_comparator=float(b.mean()),
                    delta_v2_minus_comparator=float(d.mean()),delta_ci95_lower=lo,delta_ci95_upper=hi,bootstrap_key=key,
                    **signed_rank(-d),wins=int((sign<0).sum()),ties=int((sign==0).sum()),losses=int((sign>0).sum()),
                    family='primary' if metric in PRIMARY else 'secondary',difference_direction='v2 minus comparator; negative favors v2',effect_direction='positive RBC favors v2'))
                differences.extend(dict(load_multiplier=load,comparator=comparator,metric=metric,seed=int(seed),v2=float(av),comparator_value=float(bv),delta=float(dv),outcome='win' if round(dv,12)<0 else 'loss' if round(dv,12)>0 else 'tie') for seed,av,bv,dv in zip(p.index,a,b,d))
    tests=pd.DataFrame(rows)
    for _,g in tests.groupby(['comparator','family']):
        tests.loc[g.index,'p_value_holm']=holm_adjust(g.p_value);tests.loc[g.index,'family_size']=len(g)
    tests['supported_improvement']=(tests.p_value_holm<.05)&tests.delta_ci95_upper.lt(0)
    return tests,pd.DataFrame(differences)

def ratio_table(raw):
    rows=[]
    for load,g in raw.groupby('load_multiplier'):
        for comparator in ('joint_sla_v1','sla_aware'):
            for metric in ('mean_request_latency_ms','p95_latency_ms','p99_latency_ms','average_replicas','average_vram_residency_gib'):
                p=g.pivot(index='seed',columns='policy',values=metric).sort_index()
                a=p.joint_sla_v2.to_numpy();b=p[comparator].to_numpy()
                idx=rng_for(f'v2-ratio:{load}:{comparator}:{metric}').integers(0,len(a),(10000,len(a)))
                boot=a[idx].mean(axis=1)/b[idx].mean(axis=1);lo,hi=np.quantile(boot,[.025,.975])
                rows.append(dict(load_multiplier=load,comparator=comparator,metric=metric,ratio=float(a.mean()/b.mean()),ci95_lower=float(lo),ci95_upper=float(hi),method='paired bootstrap ratio of seed means',resamples=10000))
    return pd.DataFrame(rows)

def hypotheses(raw,tests,ratios):
    def supported(load,comp,metric):return bool(tests[(tests.load_multiplier==load)&tests.comparator.eq(comp)&tests.metric.eq(metric)].supported_improvement.iloc[0])
    means=raw.groupby(['load_multiplier','policy']).mean(numeric_only=True)
    base=means.loc[1.,'sla_aware'];v1=means.loc[1.,'joint_sla_v1'];v2=means.loc[1.,'joint_sla_v2']
    gap=v1.sla_breach_rate-base.sla_breach_rate;newgap=v2.sla_breach_rate-base.sla_breach_rate
    reduction=1-newgap/gap if gap>0 else None
    h3=bool(gap>0 and reduction>=.5 and v2.average_replicas<=.95*base.average_replicas and v2.average_vram_residency_gib<=.95*base.average_vram_residency_gib)
    keep=ratios[(ratios.load_multiplier==2)&ratios.comparator.eq('joint_sla_v1')&ratios.metric.isin(('mean_request_latency_ms','p95_latency_ms','p99_latency_ms'))]
    h4=bool(keep.ci95_upper.le(1.05).all() and all(supported(2,'sla_aware',m) for m in ('mean_request_latency_ms','p95_latency_ms','p99_latency_ms')))
    v2raw=raw[raw.policy=='joint_sla_v2']
    result={'V2-H1':supported(1,'joint_sla_v1','sla_breach_rate'),'V2-H2':supported(1,'joint_sla_v1','Gold_breach_rate'),
        'V2-H3':h3,'V2-H4':h4,'V2-H5':bool(v2raw.controller_decision_mean_ms.lt(10).all()),'V2-H6':True}
    resource_approx=bool(v2.average_replicas/base.average_replicas>=.95 or v2.average_vram_residency_gib/base.average_vram_residency_gib>=.95)
    residual=bool(newgap>.05)
    failure=bool((not result['V2-H1'] and not result['V2-H2']) or (residual and not h4) or (result['V2-H1'] and resource_approx))
    return dict(hypotheses=result,overall_success=all(result.values()),partial_success=bool((result['V2-H1'] or result['V2-H2']) and not all(result.values())),
        failure_criterion_triggered=failure,baseline_sla_gap_reduction_fraction=reduction,residual_sla_gap_pp=float(100*newgap),
        materially_worse_than_baseline=residual,approximately_baseline_resource_cost=resource_approx,
        direct_replica_ratio=float(v2.average_replicas/base.average_replicas),direct_vram_ratio=float(v2.average_vram_residency_gib/base.average_vram_residency_gib),
        latency_guardrail='95% paired ratio upper <=1.05 plus supported baseline benefit; diagnostic, not formal powered noninferiority',stop=True,no_v3=True)

def save(fig,out,name):
    import matplotlib.pyplot as plt
    out.mkdir(parents=True,exist_ok=True);fig.tight_layout()
    for ext in ('png','svg','pdf'):fig.savefig(out/f'{name}.{ext}',dpi=300,bbox_inches='tight')
    plt.close(fig)

def figures(raw,burst,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    colors=['#536878','#d27d2d','#247ba0']
    figs=out/'figures'
    def bars(data,load,metric,name,label,mult=1):
        fig,ax=plt.subplots(figsize=(6.7,4.2));g=data[data.load_multiplier==load]
        for i,policy in enumerate(POLICIES):
            x=g[g.policy==policy].sort_values('seed')[metric].to_numpy()*mult
            lo,hi=bootstrap_mean_ci(x,key=f'figure:{name}:{policy}')
            ax.bar(i,x.mean(),color=colors[i],width=.65,yerr=[[x.mean()-lo],[hi-x.mean()]],capsize=4)
        ax.set_xticks(range(3),[LABELS[p] for p in POLICIES]);ax.set_ylabel(label)
        ax.set_title(f'Hardware-grounded {load:.1f}x load; 30 paired held-out seeds')
        ax.text(.01,-.18,'Error bars: 95% bootstrap CI of seed means',transform=ax.transAxes,fontsize=9)
        save(fig,figs,name)
    for load,metric,name,label,mult in [(1,'sla_breach_rate',FIGURES[0],'SLA breaches (%)',100),(1,'Gold_breach_rate',FIGURES[1],'Gold breaches (%)',100),(1,'p95_latency_ms',FIGURES[2],'Request p95 latency (ms)',1),(2,'sla_breach_rate',FIGURES[3],'SLA breaches (%)',100),(2,'p95_latency_ms',FIGURES[4],'Request p95 latency (ms)',1),(2,'p99_latency_ms',FIGURES[5],'Request p99 latency (ms)',1)]:bars(raw,load,metric,name,label,mult)
    def loads_plot(data,metric,name,label,mult=1):
        fig,ax=plt.subplots(figsize=(7,4.3))
        for i,policy in enumerate(POLICIES):
            x=[];y=[];lo=[];hi=[]
            for load,g in data[data.policy==policy].groupby('load_multiplier'):
                vals=g.sort_values('seed')[metric].to_numpy()*mult;ci=bootstrap_mean_ci(vals,key=f'figure:{name}:{policy}:{load}')
                x.append(load);y.append(vals.mean());lo.append(vals.mean()-ci[0]);hi.append(ci[1]-vals.mean())
            ax.errorbar(x,y,yerr=[lo,hi],label=LABELS[policy],marker='o',color=colors[i],capsize=4)
        ax.set_xticks([1,2],['1.0x','2.0x']);ax.set_xlabel('Offered load multiplier');ax.set_ylabel(label);ax.legend()
        ax.set_title('Held-out seed means with 95% bootstrap CIs');save(fig,figs,name)
    for metric,name,label in [('average_replicas',FIGURES[6],'Average replicas'),('average_vram_residency_gib',FIGURES[7],'Average VRAM residency (GiB)'),('total_actions',FIGURES[8],'Accepted actions / 100 slots')]:loads_plot(raw,metric,name,label)
    for xmetric,ymetric,name,xlabel,ylabel,mult in [('average_replicas','sla_breach_rate',FIGURES[9],'Average replicas','SLA breaches (%)',100),('average_replicas','Gold_breach_rate',FIGURES[10],'Average replicas','Gold breaches (%)',100),('average_vram_residency_gib','p95_latency_ms',FIGURES[11],'Average VRAM residency (GiB)','p95 latency (ms)',1)]:
        fig,axes=plt.subplots(1,2,figsize=(11,4.5))
        for ax,load in zip(axes,[1,2]):
            for i,policy in enumerate(POLICIES):
                g=raw[(raw.load_multiplier==load)&raw.policy.eq(policy)]
                x=g[xmetric].to_numpy();y=g[ymetric].to_numpy()*mult
                xc=bootstrap_mean_ci(x,key=f'frontier:{name}:{load}:{policy}:x');yc=bootstrap_mean_ci(y,key=f'frontier:{name}:{load}:{policy}:y')
                ax.scatter(x,y,s=9,alpha=.18,color=colors[i])
                ax.errorbar(x.mean(),y.mean(),xerr=[[x.mean()-xc[0]],[xc[1]-x.mean()]],yerr=[[y.mean()-yc[0]],[yc[1]-y.mean()]],fmt='o',capsize=3,color=colors[i],label=LABELS[policy])
            ax.set_title(f'{load:.1f}x load');ax.set_xlabel(xlabel);ax.set_ylabel(ylabel)
        axes[1].legend(fontsize=9);save(fig,figs,name)
    loads_plot(burst,'preburst_active_replicas',FIGURES[12],'Ready replicas / service before burst')
    loads_plot(burst,'recovery_window_breach_rate',FIGURES[13],'Recovery-window breaches (%)',100)
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.5))
    for i,policy in enumerate(POLICIES):
        g=raw[raw.policy==policy].groupby('load_multiplier')
        for ax,metric,title in zip(axes,['controller_decision_mean_ms','controller_decision_p95_ms'],['Mean decision step','p95 decision step']):
            ax.plot([1,2],g[metric].mean(),marker='o',color=colors[i],label=LABELS[policy]);ax.set_title(title);ax.set_xlabel('Load multiplier');ax.set_ylabel('Wall time (ms)');ax.set_xticks([1,2])
    axes[0].axhline(10,ls='--',color='black',label='10 ms mean limit');axes[1].legend(fontsize=9);save(fig,figs,FIGURES[14])

def report(raw,tests,ratios,burst,h,out,receipt):
    means=raw.groupby(['load_multiplier','policy']).mean(numeric_only=True).reset_index()
    def mt(metrics,data=means):return table(data[['load_multiplier','policy',*metrics]],5)
    def st(metrics):return table(tests[tests.metric.isin(metrics)][['load_multiplier','comparator','metric','delta_v2_minus_comparator','delta_ci95_lower','delta_ci95_upper','p_value','p_value_holm','rank_biserial_correlation','wins','ties','losses']],5)
    manifest=verify_freeze()
    headers={}
    headers['Motivation']='Test whether cold recovery headroom and finite Gold retention can repair the previously observed hardware-grounded QoS/resource trade-off. This is the final algorithmic experiment; no v3.'
    headers['Why v2 Was Introduced']='Previous seeds1–30 showed DIRECT v1 SLA25.48% vs baseline15.43%, Gold35.97% vs22.63%, and fewer ready replicas before bursts. These historical results motivate design only; all tables below use unseen seeds31–60.'
    headers['Prior Failure Mechanism']='The earlier exploratory factorial indicated VRAM and cold costs interacting with consolidation. It did not prove a unique cause. Prior preburst readiness was1.03 vs1.66 and recovery breaches36.94% vs21.60%; scale-in counts alone did not explain the reversal.'
    headers['Frozen Design']='Call v1 controller once; block selected scale-ins below causal warm requirement. Retain v1 dispatch/routing and other decisions. Establish a finite Gold floor through Gold-only repair if nonretiring ready+pending count is below requirement. Preserve cooldown, feasibility, max3 replicas and budget2. Repair precedes retained actions, at most one/service. No independent Silver/Bronze repair.\n\nParameters: H=1, Gold multiplier1.5, Silver=sqrt(1.5), Bronze1; Gold floor2, other floors1; W=5 derived from class cold readiness.'
    headers['Recovery-Aware Headroom']='For backlog q, observed λ requests/s, class readiness R seconds, causal estimated serial cycle L seconds, deadline D seconds and slack h=max(D−L,0): required=min(3,max(tier_floor,ceil(tier_factor*max(qL/h,(q+λR)L/(R+h))))). Empty history λ=0; impossible slack with demand or no finite feasible cycle requires3. Cycle includes current nominal or past completion CPU/GPU/network/resource delay, excluding service FIFO wait. It is a fluid retention estimate, not a guarantee, forecast or admission decision.'
    headers['Gold Protection']='The Gold floor cannot be created by rejecting scale-ins from an initial one-ready placement, so a bounded Gold-only repair is needed. Pending cold replicas count toward planned capacity, while ready capacity is logged separately. Infeasible deficits remain visible; no unlimited resources or altered cold delay.'
    headers['Causality / No-Future Information']='Recover completed-slot per-service observed counts by algebraically inverting unchanged EWMA telemetry. W contains only prior completed slots. No controller reads arrivals tape, future work factors, expected rates or burst masks. Physical source/worker/dispatch/decisions are inherited; burst identification is exclusively retrospective. Unit tests compare observed history with exports, block future-tape access, verify deterministic routing and same budget.\n\nIndependent receipt: '+json.dumps(receipt,ensure_ascii=False)
    headers['Development Seeds']='101–105 only,0.5/1/2×,45 simulations. Exactly ONE candidate. Acceptance checked accounting/capacity/Gold guard/stability, wall≤600s,RSS≤4096MiB,drain≤120s,v2 mean step<10ms. No SLA-driven selection, grid search or development statistics promoted as paper evidence. See separate development outputs.'
    headers['Freeze Procedure']=f"Freeze UTC {manifest['timestamp']}; config SHA256 `{manifest['config_sha256']}`. Source hashes, exact parameters, git state and protected historical manifest are archived. Configuration and source hashes are checked before held-out generation and again after analysis. All generation-ledger timestamps follow freeze. No post-hoc policy/config changes. Implementation commit: {manifest['implementation_commit']}; file hashes identify uncommitted code."
    headers['Held-Out Seeds']=f"31–60 paired across SLA-aware/v1/v2,1× and2×:180 simulations;{receipt['requests_verified']:,} exported outcomes independently verified. Shared workload/traffic hashes within every seed/load; no lost,duplicate,unplaced or dropped requests. Nodes10,services40,slots100,Δ100ms. These are the frozen existing hardware-grounded scenario, not the original exploratory5-node/20-service setting. No optional1.5×."
    headers['1.0x Hardware-Grounded Results']=mt(['sla_breach_rate','Gold_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms'],means[means.load_multiplier==1])
    headers['2.0x High-Pressure Results']=mt(['sla_breach_rate','Gold_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms'],means[means.load_multiplier==2])
    headers['Aggregate SLA']='Rates in tables are fractions; multiply by100 for percent. Differences are v2−comparator (negative favors v2).\n\n'+st(['sla_breach_rate'])
    headers['Gold / Silver / Bronze']=mt(['Gold_breach_rate','Silver_breach_rate','Bronze_breach_rate'])+'\n\n'+st(['Gold_breach_rate','Silver_breach_rate','Bronze_breach_rate'])+'\n\nClass results LIGHT/MEDIUM/HEAVY and their summaries are descriptive, not an additional confirmatory testing family. Tier protection can redistribute queue/resource pressure, so aggregate improvement alone cannot establish fairness.'
    headers['Mean / p95 / p99']=mt(['mean_request_latency_ms','median_latency_ms','p95_latency_ms','p99_latency_ms'])+'\n\n'+st(['mean_request_latency_ms','p95_latency_ms','p99_latency_ms'])+'\n\nQuantiles are first computed per run over all arrivals after drain; then averaged across seeds. They are not pooled request quantiles.\n\n'+table(ratios[ratios.metric.isin(('mean_request_latency_ms','p95_latency_ms','p99_latency_ms'))],5)
    headers['Resource Cost']=mt(list(RESOURCE))+'\n\n'+st(['average_replicas','average_vram_residency_gib','total_actions'])+'\n\nVRAM is time-integrated residency divided by10s; replica occupancy is integrated over the same horizon, including correct migration accounting. Peak VRAM includes simultaneous migration reservations. CPU/GPU utilization describes the finite physical simulated resources; no claim of overbooking improvement.'
    headers['Warm Replica Behavior']=mt(['mean_required_warm_replicas','mean_actual_ready_replicas','prevented_scale_ins_due_to_headroom','prevented_scale_ins_Gold','headroom_deficit_frequency','service_seconds_below_required','scaleouts_during_cold_exposure','gold_repair_scaleouts_proposed','gold_repair_scaleouts_accepted'],means[means.policy=='joint_sla_v2'])+'\n\nMetrics apply to v2 only. Prevented scale-ins count selected v1 proposals blocked by the guard, not all hypothetical actions. Accepted repair and proposed repair are distinguished. Deficit frequency denominator4000 service×control slots/run; service seconds=deficit slots×.1. Class cold exposure remains1/2/5 slots; it is never reduced by the policy.'
    bm=burst.groupby(['load_multiplier','policy']).mean(numeric_only=True).reset_index()
    headers['Burst Recovery']=mt(['preburst_active_replicas','queue_growth','recovery_window_breach_rate','mean_recovery_after_burst_slots','recovery_censored_fraction','scaleout_censored_fraction','scaleout_count','cold_exposure_service_seconds'],bm)+'\n\nReady-before-burst is the previous control snapshot. Recovery cohort includes arrivals during burst until queue returns to max(preburst backlog,1) or next burst/horizon. Each seed aggregates its recovery cohorts, then seed means are compared. Conditional recovery/first-scaleout times exclude censored cases; censoring fractions are shown, not imputed as zero. Exposure uses allocated−active at control snapshots (cold/pending/retiring unavailability proxy), not a precise request-level cold penalty. Burst action/exposure windows extend until next burst or horizon.'
    headers['Controller Overhead']=mt(['controller_decision_mean_ms','controller_decision_median_ms','controller_decision_p95_ms','controller_total_instrumented_mean_ms','controller_total_instrumented_p95_ms','wall_clock_seconds'])+'\n\nDecision time includes policy+action application. Instrumented total adds snapshot time. Routing cost is exported separately; H5 is the preregistered per-run mean decision-step gate. Means/medians/p95 here average each run statistic, not pooled timing samples. Timing is machine-dependent; exact semantic traces are deterministic.'
    headers['Statistical Tests']='30 independent paired seeds.10000 paired bootstrap percentile resamples,95% CI,seed73001,keyed streams. Wilcoxon two-sided with original rounding/tie/zero rules. Positive rank-biserial effect favors v2; wins/ties/losses use12-decimal rounded differences. Primary Holm families each comparator:SLA,Gold,p95×2loads=6. Secondary each comparator:mean,p99,Silver,Bronze,replicas,VRAM,actions×2loads=14. No request-level pseudoreplication. Independent DP/tie-adjusted Wilcoxon, bootstrap and Holm reconstructions verify all40 tests. See paired_tests.csv and summary_statistics.csv (mean,SD,CI).'
    headers['Performance-Resource Frontier']=mt(['sla_breach_rate','Gold_breach_rate','p95_latency_ms','average_replicas','average_vram_residency_gib','total_actions'])+'\n\nPareto figures show per-seed clouds, policy means and marginal95% bootstrap CIs for both loads; no continuous frontier fit or global optimality claim. Direct replica ratio(v2/baseline)='+str(h['direct_replica_ratio'])+',VRAM ratio='+str(h['direct_vram_ratio'])+'. QoS gap reduction='+str(h['baseline_sla_gap_reduction_fraction'])+'.'
    headers['V2-H1 to V2-H6']=table(pd.DataFrame([{'hypothesis':k,'passed':v} for k,v in h['hypotheses'].items()]))+'\n\n'+json.dumps(h,indent=2)+'\n\nH3 requires≥50% gap reduction and both resources≤95% baseline. H4 requires ratio upper≤1.05 for mean/p95/p99 relative to v1 plus supported advantage vs baseline; this is a declared diagnostic guardrail, not formal powered noninferiority.'
    headers['Negative Results']='All worse-seed outcomes against both comparators are exported in negative_seed_cases.csv. Unsupported comparisons remain unsupported even when sample means improve. Retention spends more resources, Gold repair may consume action opportunities otherwise used by other tiers, and infeasible headroom is disclosed. No failed hypothesis is removed. Failure flags and partial-success flags can coexist under the preregistered criteria. Approximately-baseline resource cost is flagged if either replica or VRAM ratio reaches0.95; material resource saving requires both below the declared bound.\n\n'+st(['sla_breach_rate','Gold_breach_rate'])
    headers['Threats to Validity']='One laptop GPU calibration, three measured vision model classes mapped to40 synthetic services; not a real distributed telco deployment. Fixed10-node topology,100-slot horizon,synthetic traffic/work variance/network/migration costs, class-average hardware times. Global v1 nominal estimator remains inherited. Cold readiness can exceed strict deadlines. Fluid headroom uses serial cycle estimates and retrospective latency telemetry, not a queue stability theorem. Five engineering seeds and one candidate do not prove universality. Held-out seeds control tuning leakage, not external validity. Multiple testing families are explicit; secondary/class/mechanism interpretations remain limited. Controller clocks/RSS are host-dependent.'
    supported=tests[tests.supported_improvement][['load_multiplier','comparator','metric']]
    headers['Safe Paper Claims']='Only the following held-out supported lower-is-better comparisons may be claimed with their declared family/CI: \n\n'+table(supported)+'\n\nThe fixed causal extension and its measured resource trade-offs are reproducible; historical negative results remain part of the contribution. No external literature percentages were used.'
    headers['Claims We Cannot Make']='No forecasting/oracle claim; no universally best scheduler, guaranteed deadlines, global Pareto optimum, real5G/6G deployment validation, universal Gold fairness or proven general noninferiority. No undisclosed dropped traffic. Do not claim novelty from implementation alone; final literature/novelty review is a separate next stage.'
    verdict='All declared H1–H6 pass' if h['overall_success'] else 'The full declared success criterion is not met'
    headers['Final B-Level Assessment']=verdict+'. This study can inform a B-level systems paper as a bounded performance/resource contribution with hardware-grounded negative validation; venue suitability is conditional on literature differentiation, contribution framing and review. A positive aggregate result cannot hide tier/resource/tail failures. STOP algorithmic experiments now regardless of result. No v3, no retuning. Next stages:final literature/novelty check,contribution framing,SOVEREIGN mapping,paper writing,venue selection.\n\nReproduce:\n\n```powershell\n.venv\\Scripts\\python.exe -m pytest -q\n.venv\\Scripts\\python.exe run_jointsla_v2.py --development --reuse-results\n.venv\\Scripts\\python.exe run_jointsla_v2.py --freeze\n.venv\\Scripts\\python.exe run_jointsla_v2.py --held-out --reuse-results\n```\n\nTo regenerate the same frozen simulations use --development --force and --held-out --force sequentially; --force does not bypass source/config/seed guards or erase previous validation history. Fresh checkout:complete development first,then freeze,then held-out. Development after existing freeze is replication only; no redesign.\n'
    assert len(headers)==27
    text='\n\n'.join('# '+title+'\n\n'+body for title,body in headers.items())
    (out/'report.md').write_text(text,encoding='utf-8')

def analyze(raw,out,phase):
    summary=summarize(raw,('load_multiplier','policy'))
    summary.to_csv(out/'summary_statistics.csv',index=False)
    if phase=='development':
        verify_study(out,phase)
        (out/'report.md').write_text('# Development engineering checks\n\nOne preregistered candidate, seeds101–105 only at0.5/1/2×.45 simulations. Not final paper evidence.\n\n'+json.dumps(read(out/'engineering_acceptance.json'),indent=2),encoding='utf-8')
        return
    tests,differences=paired(raw);ratios=ratio_table(raw)
    tests.to_csv(out/'paired_tests.csv',index=False);differences.to_csv(out/'paired_seed_differences.csv',index=False)
    differences[differences.outcome=='loss'].to_csv(out/'negative_seed_cases.csv',index=False)
    ratios.to_csv(out/'paired_ratios.csv',index=False)
    keys=['load_multiplier','seed','policy']
    raw[keys+list(RESOURCE)+list(QUEUE)+list(PRESSURE)].to_csv(out/'resource_results.csv',index=False)
    ctrl=[k for k in raw if 'controller' in k or k in ('wall_clock_seconds','routing_cpu_ms')]
    raw[keys+ctrl].to_csv(out/'controller_results.csv',index=False)
    v2=raw[raw.policy=='joint_sla_v2'];cols=[k for k in raw if 'headroom' in k or 'required' in k or 'ready_replicas' in k or 'cold_exposure' in k or 'repair_scaleouts' in k or k=='service_seconds_below_required']
    v2[keys+cols].to_csv(out/'headroom_summary.csv',index=False)
    for file,col in [('tier_results.csv','tier'),('model_class_results.csv','model_class')]:
        summarize(pd.read_csv(out/file),('load_multiplier','policy',col)).to_csv(out/file.replace('_results','_summary'),index=False)
    events=pd.read_csv(out/'burst_results.csv');bs=burst_summary(events,'load_multiplier')
    extras=events.groupby(keys)[['scaleout_count','cold_exposure_service_seconds']].mean().reset_index()
    bs=bs.merge(extras,on=keys,validate='one_to_one');bs.to_csv(out/'burst_seed_summary.csv',index=False)
    h=hypotheses(raw,tests,ratios)
    receipt=verify_study(out,phase,tests);write_json(out/'hypothesis_assessment.json',h)
    figures(raw,bs,out);report(raw,tests,ratios,bs,h,out,receipt)
