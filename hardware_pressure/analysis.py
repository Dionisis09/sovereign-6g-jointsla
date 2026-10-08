"""Seed-level comparisons, operating envelope and transparent factorial effects."""
import json
import numpy as np
import pandas as pd
from paper_evaluation.statistics import summarize,bootstrap_mean_ci,signed_rank,holm_adjust
from hardware_grounded.environment import ROOT,write_json
from .design import LOADS,REGIMES,POLICIES
from .experiment import SWEEP,CAUSAL

METRICS=('sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms')
RESOURCE=('average_replicas','peak_replicas','average_vram_residency_gib','peak_pool_vram_gib','average_cpu_utilization','average_gpu_utilization','cold_starts','scale_outs','scale_ins','migrations','total_actions')
QUEUE=('mean_queue_delay_ms','p95_queue_delay_ms','average_queue_length','peak_queue_length')
PRESSURE=('offered_requests_per_slot','completed_requests_per_slot_within_horizon','arrival_cohort_completed_per_slot',
    'average_active_replicas_per_service','mean_queue_per_service','resource_saturation_frequency',
    'fraction_slots_no_feasible_scaleout','fraction_slots_no_capacity_feasible_scaleout',
    'realized_request_wait_fraction','realized_node_contention_fraction','routing_under_contention_fraction',
    'action_budget_exhausted_fraction','mean_free_cpu_cores','mean_free_gpu_units','mean_free_vram_gib')
LABELS={'sla_aware':'SLA-aware','joint_sla':'JointSLA'}

def paired_tables(raw,index='load_multiplier',metrics=METRICS,subgroup=None):
    rows=[];differences=[]
    groups=[index]+([subgroup] if subgroup else [])
    for key,g in raw.groupby(groups,sort=True):
        key=key if isinstance(key,tuple) else (key,);metadata=dict(zip(groups,key))
        for metric in metrics:
            p=g.pivot(index='seed',columns='policy',values=metric).sort_index()
            a,b=p.sla_aware.to_numpy(),p.joint_sla.to_numpy();d=b-a;signs=np.round(d,12)
            lo,hi=bootstrap_mean_ci(d,key=f'pressure:{key}:{metric}')
            family=('tier' if subgroup=='tier' else 'model_class' if subgroup else 'primary' if metric in ('sla_breach_rate','p95_latency_ms') else 'secondary')
            rows.append(dict(**metadata,metric=metric,n=len(d),mean_sla_aware=float(a.mean()),mean_joint_sla=float(b.mean()),
                delta_joint_minus_sla=float(d.mean()),delta_ci95_lower=lo,delta_ci95_upper=hi,
                **signed_rank(-d),wins=int((signs<0).sum()),ties=int((signs==0).sum()),losses=int((signs>0).sum()),family=family))
            differences.extend(dict(**metadata,metric=metric,seed=int(seed),sla_aware=float(av),joint_sla=float(bv),delta_joint_minus_sla=float(dv),outcome='win' if round(dv,12)<0 else 'loss' if round(dv,12)>0 else 'tie') for seed,av,bv,dv in zip(p.index,a,b,d))
    tests=pd.DataFrame(rows)
    for _,g in tests.groupby('family'):
        tests.loc[g.index,'p_value_holm']=holm_adjust(g.p_value)
        tests.loc[g.index,'family_size']=len(g)
    tests['supported_direction']=np.where((tests.p_value_holm<.05)&(tests.delta_ci95_upper<0),'JointSLA',np.where((tests.p_value_holm<.05)&(tests.delta_ci95_lower>0),'SLA-aware','unresolved'))
    return tests,pd.DataFrame(differences)

def table(frame,digits=4):
    f=frame.copy()
    for c in f:
        if pd.api.types.is_numeric_dtype(f[c]):f[c]=f[c].map(lambda x:f'{x:.{digits}g}' if pd.notna(x) else 'NA')
    return '| '+' | '.join(map(str,f.columns))+' |\n| '+' | '.join(['---']*len(f.columns))+' |\n'+'\n'.join('| '+' | '.join(str(v).replace('|','/') for v in row)+' |' for row in f.itertuples(index=False,name=None))

def mean_table(raw,index,metrics):return raw.groupby([index,'policy'])[list(metrics)].mean().reset_index()

def burst_summary(bursts,index):
    rows=[]
    for key,g in bursts.groupby([index,'seed','policy']):
        rows.append(dict(**dict(zip([index,'seed','policy'],key)),bursts=len(g),
            preburst_active_replicas=float(g.preburst_active_replicas.mean()),queue_growth=float(g.queue_growth.mean()),
            mean_first_scaleout_delay_slots=float(g.first_scaleout_delay_slots.mean()),scaleout_censored_fraction=float(g.scaleout_censored.mean()),
            mean_cold_delay_ms=float(g.mean_cold_delay_ms.mean()),mean_recovery_after_burst_slots=float(g.recovery_after_burst_slots.mean()),
            recovery_censored_fraction=float(g.recovery_censored.mean()),
            recovery_window_requests=int(g.recovery_window_requests.sum()),recovery_window_breaches=int(g.recovery_window_breaches.sum()),
            recovery_window_breach_rate=float(g.recovery_window_breaches.sum()/g.recovery_window_requests.sum())))
    return pd.DataFrame(rows)

def envelope(tests,metric='sla_breach_rate'):
    primary=tests[tests.metric==metric].sort_values('load_multiplier')
    result=[]
    for r in primary.itertuples():
        result.append(dict(load_multiplier=r.load_multiplier,category=r.supported_direction+'-favored' if r.supported_direction!='unresolved' else 'approximately competitive / statistically unresolved',delta_sla=r.delta_joint_minus_sla,ci_lower=r.delta_ci95_lower,ci_upper=r.delta_ci95_upper,p_holm=r.p_value_holm))
    sign_cross=[];supported=[]
    for a,b in zip(primary.itertuples(),list(primary.itertuples())[1:]):
        if a.delta_joint_minus_sla*b.delta_joint_minus_sla<0:
            pair=[a.load_multiplier,b.load_multiplier];sign_cross.append(pair)
    # Unresolved intervening points widen the bracket; they do not erase an
    # eventual opposite supported direction at an observed grid point.
    resolved=list(primary[primary.supported_direction!='unresolved'].itertuples())
    for a,b in zip(resolved,resolved[1:]):
        if a.delta_joint_minus_sla*b.delta_joint_minus_sla<0 and a.supported_direction!=b.supported_direction:
            supported.append([a.load_multiplier,b.load_multiplier])
    return pd.DataFrame(result),dict(observed_mean_sign_crossing_intervals=sign_cross,supported_crossing_intervals=supported,
        supported_crossover=bool(supported),equivalence_claim=False,threshold='exploratory observed grid bracket; no interpolated threshold')

def sweep_analysis(raw):
    assert len(raw)==420 and set(raw.load_multiplier)==set(LOADS) and set(raw.seed)==set(range(1,31))
    keep=raw.drop(columns=['routing_under_contention_fraction'])
    summary=summarize(keep,('load_multiplier','policy'));summary.to_csv(SWEEP/'summary_statistics.csv',index=False)
    tests,delta=paired_tables(raw);tests.to_csv(SWEEP/'paired_tests.csv',index=False);tests.to_csv(SWEEP/'crossover_analysis.csv',index=False)
    delta.to_csv(SWEEP/'paired_seed_differences.csv',index=False);delta[delta.outcome=='loss'].to_csv(SWEEP/'negative_seed_cases.csv',index=False)
    for subgroup in ('tier','model_class'):
        f=pd.read_csv(SWEEP/f'{subgroup}_results.csv')
        summarize(f,('load_multiplier','policy',subgroup)).to_csv(SWEEP/f'{subgroup}_summary_statistics.csv',index=False)
        t,_=paired_tables(f,metrics=('sla_breach_rate',),subgroup=subgroup);t.to_csv(SWEEP/f'{subgroup}_paired_tests.csv',index=False)
    meta=['load_multiplier','seed','policy']
    raw[meta+list(RESOURCE)].to_csv(SWEEP/'resource_results.csv',index=False)
    raw[meta+list(QUEUE)].to_csv(SWEEP/'queue_results.csv',index=False)
    raw[meta+list(PRESSURE)+['average_cpu_utilization','average_gpu_utilization','average_vram_residency_gib','mean_gpu_vram_reserved_pct']].to_csv(SWEEP/'pressure_characterization.csv',index=False)
    # Per-node measured utilization and simultaneous free headroom remain available.
    node_rows=[];offered=[]
    for r in raw.itertuples():
        folder=SWEEP/'runs'/f'load_{r.load_multiplier:.2f}'/f'seed_{r.seed:03d}'/r.policy
        nodes=pd.read_csv(folder/'node_trajectories.csv.gz');head=pd.read_csv(folder/'pressure_nodes.csv.gz')
        f=nodes.groupby('node')[['cpu_utilization','gpu_utilization','gpu_vram_reserved_fraction']].mean().join(head.groupby('node')[['free_cpu_cores','free_gpu_units','free_vram_gib']].mean()).reset_index()
        for k,v in zip(meta,[r.load_multiplier,r.seed,r.policy]):f[k]=v
        node_rows.append(f)
        if r.policy=='sla_aware':
            import gzip
            inp=SWEEP/'inputs'/f'load_{r.load_multiplier:.2f}'
            with gzip.open(inp/f'seed_{r.seed:03d}.json.gz','rt',encoding='utf-8') as stream:w=json.load(stream)
            config=json.loads((inp/f'seed_{r.seed:03d}_config.json').read_text())
            rates=pd.DataFrame(w['traffic']).groupby('service_id').expected_rate_rps.mean()
            cpu=sum(rates[s['service_id']]*s['cpu_cores']*(config['service_configs'][str(s['service_id'])]['preprocess_ms']+config['service_configs'][str(s['service_id'])]['postprocess_ms']+config['config']['gpu_stage_cpu_fraction']*config['service_configs'][str(s['service_id'])]['inference_ms'])/1000 for s in w['services'])
            gpu=sum(rates[s['service_id']]*config['service_configs'][str(s['service_id'])]['inference_ms']/1000 for s in w['services'])
            offered.append(dict(load_multiplier=r.load_multiplier,seed=r.seed,
                expected_gpu_offered_pressure=gpu/sum(w['gpu_units']),
                expected_cpu_offered_pressure=cpu/sum(n['cpu_capacity'] for n in w['scenario']['nodes']),
                total_vram_capacity_gib=sum(n['gpu_capacity'] for n in w['scenario']['nodes'])))
    pd.concat(node_rows).to_csv(SWEEP/'node_pressure_characterization.csv',index=False)
    pressure=pd.read_csv(SWEEP/'pressure_characterization.csv').merge(pd.DataFrame(offered),on=['load_multiplier','seed'],validate='many_to_one')
    pressure['pool_vram_occupancy_fraction']=pressure.average_vram_residency_gib/pressure.total_vram_capacity_gib
    pressure.to_csv(SWEEP/'pressure_characterization.csv',index=False)
    br=burst_summary(pd.read_csv(SWEEP/'burst_recovery.csv'),'load_multiplier');br.to_csv(SWEEP/'burst_summary.csv',index=False)
    env,status=envelope(tests);env.to_csv(SWEEP/'operating_envelope.csv',index=False)
    per_metric={metric:envelope(tests,metric)[1] for metric in METRICS}
    status['metric_specific_crossovers']=per_metric
    write_json(SWEEP/'metric_crossovers.json',per_metric)
    p=delta[delta.metric=='sla_breach_rate'].pivot(index='seed',columns='load_multiplier',values='delta_joint_minus_sla')
    x=np.array(p.columns);slopes=(p.to_numpy()@(x-x.mean()))/np.sum((x-x.mean())**2)
    ci=bootstrap_mean_ci(slopes,key='pressure:trend')
    status['delta_sla_trend_slope_per_load_unit']=float(slopes.mean());status['trend_ci95']=ci
    status['PS1_low_load_SLA_aware_supported']=bool(tests[(tests.metric=='sla_breach_rate')&tests.load_multiplier.isin([.5,.75])].supported_direction.eq('SLA-aware').all())
    counts={}
    for metric in ('average_replicas','average_vram_residency_gib','total_actions'):
        q=raw.groupby(['load_multiplier','policy'])[metric].mean().unstack();counts[metric]=int((q.joint_sla<q.sla_aware).sum())
    status['PS4_lower_resource_regime_counts']=counts;status['PS4_descriptive_supported']=all(x>=4 for x in counts.values())
    status['PS5_equal_tapes_and_profiles']=True
    direct=delta[(delta.metric=='sla_breach_rate')&(delta.load_multiplier==1)].sort_values(['delta_joint_minus_sla','seed'])
    status['representative_seeds']={'best':int(direct.iloc[0].seed),'median':int(direct.iloc[(len(direct)-1)//2].seed),'worst':int(direct.iloc[-1].seed)}
    write_json(SWEEP/'hypotheses.json',status)
    verify_statistics(tests,raw)
    figures_sweep(raw,summary,tests,br,status);report_sweep(raw,tests,summary,br,status)
    return status

def verify_statistics(tests,raw):
    """Independent bootstrap quantile, rank DP and Holm reconstruction."""
    from paper_evaluation.validation import reference_ci,reference_signed_rank
    for r in tests.itertuples():
        g=raw[raw.load_multiplier==r.load_multiplier].pivot(index='seed',columns='policy',values=r.metric).sort_index()
        d=g.joint_sla.to_numpy()-g.sla_aware.to_numpy()
        key=(r.load_multiplier,)
        lo,hi=reference_ci(d,f'pressure:{key}:{r.metric}')
        assert np.allclose([lo,hi],[r.delta_ci95_lower,r.delta_ci95_upper],atol=1e-12)
        w,p,rbc=reference_signed_rank(-d)
        assert np.allclose([w,p,rbc],[r.test_statistic,r.p_value,r.rank_biserial_correlation],atol=1e-10)
    for _,g in tests.groupby('family'):
        ordered=sorted(zip(g.p_value,g.index));running=0.;adjusted={}
        for i,(p,idx) in enumerate(ordered):running=max(running,p*(len(g)-i));adjusted[idx]=min(1.,running)
        assert all(abs(tests.loc[idx,'p_value_holm']-v)<1e-12 for idx,v in adjusted.items())
    write_json(SWEEP/'statistical_validation.json',dict(paired_rows_verified=len(tests),independent_bootstrap=True,independent_signed_rank=True,independent_holm=True))

def plot_setup(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.constrained_layout.use':True})
    (out/'figures').mkdir(exist_ok=True)
    return plt

def save(fig,out,name):
    import matplotlib.pyplot as plt
    for ext in ('png','svg','pdf'):fig.savefig(out/'figures'/f'{name}.{ext}',dpi=300)
    plt.close(fig)

def line_metric(ax,summary,metric,factor=1):
    for p in POLICIES:
        g=summary[(summary.policy==p)&(summary.metric==metric)].sort_values('load_multiplier')
        ax.plot(g.load_multiplier,g['mean']*factor,'o-',label=LABELS[p]);ax.fill_between(g.load_multiplier,g.ci95_lower*factor,g.ci95_upper*factor,alpha=.15)
    ax.set_xlabel('Offered traffic multiplier (1× = frozen DIRECT)');ax.grid(alpha=.2);ax.legend()

def figures_sweep(raw,summary,tests,br,status):
    plt=plot_setup(SWEEP)
    specs=[('01_sla_vs_load','sla_breach_rate','SLA breaches (%)',100),('02_mean_latency_vs_load','mean_request_latency_ms','Mean latency (ms)',1),
        ('03_p95_vs_load','p95_latency_ms','p95 latency (ms)',1),('04_p99_vs_load','p99_latency_ms','p99 latency (ms)',1),
        ('07_replicas_vs_load','average_replicas','Average allocated replicas',1),('08_vram_vs_load','average_vram_residency_gib','Average allocated pool VRAM (GiB)',1),
        ('09_actions_vs_load','total_actions','Actions per run',1),('10_queue_delay_vs_load','mean_queue_delay_ms','Mean queue delay (ms)',1),
        ('14_controller_overhead_vs_load','controller_total_instrumented_mean_ms','Mean controller decision step (ms)',1)]
    for name,metric,label,factor in specs:
        fig,ax=plt.subplots(figsize=(7,4.3));line_metric(ax,summary,metric,factor);ax.set_ylabel(label);ax.set_title(label+' · seed mean and 95% bootstrap CI');save(fig,SWEEP,name)
    for name,metric,factor,label in [('05_delta_sla_vs_load','sla_breach_rate',100,'Δ SLA breaches (percentage points)'),('06_delta_p95_vs_load','p95_latency_ms',1,'Δ p95 (ms)')]:
        g=tests[tests.metric==metric];fig,ax=plt.subplots(figsize=(7,4.3))
        ax.errorbar(g.load_multiplier,g.delta_joint_minus_sla*factor,yerr=np.array([g.delta_joint_minus_sla-g.delta_ci95_lower,g.delta_ci95_upper-g.delta_joint_minus_sla])*factor,fmt='o-',capsize=4)
        ax.axhline(0,color='black',ls='--');ax.set(xlabel='Offered traffic multiplier',ylabel=label,title='JointSLA − SLA-aware · paired 95% CI');ax.grid(alpha=.2);save(fig,SWEEP,name)
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    mean=raw.groupby(['load_multiplier','policy']).mean(numeric_only=True).reset_index()
    for ax,x,y,factor in zip(axes,['average_replicas','average_vram_residency_gib','total_actions'],['sla_breach_rate','p95_latency_ms','sla_breach_rate'],[100,1,100]):
        for p in POLICIES:
            g=mean[mean.policy==p];ax.plot(g[x],g[y]*factor,'o-',label=LABELS[p])
            for r in g.itertuples():ax.annotate(f'{r.load_multiplier:g}×',(getattr(r,x),getattr(r,y)*factor),xytext=(3,3),textcoords='offset points',fontsize=8)
        ax.set_xlabel({'average_replicas':'Average allocated replicas','average_vram_residency_gib':'Average VRAM (GiB)','total_actions':'Actions/run'}[x]);ax.set_ylabel('p95 (ms)' if y=='p95_latency_ms' else 'SLA breaches (%)');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Observed performance-resource traces · labels denote offered load');save(fig,SWEEP,'11_performance_resource_frontier')
    for subgroup,name in [('tier','12_gold_silver_bronze_vs_load'),('model_class','13_model_class_vs_load')]:
        f=pd.read_csv(SWEEP/f'{subgroup}_summary_statistics.csv');labels=('Gold','Silver','Bronze') if subgroup=='tier' else ('LIGHT','MEDIUM','HEAVY')
        fig,axes=plt.subplots(1,3,figsize=(14,4))
        for label,ax in zip(labels,axes):line_metric(ax,f[f[subgroup]==label],'sla_breach_rate',100);ax.set_title(label);ax.set_ylabel('SLA breaches (%)')
        fig.suptitle('Exploratory subgroup means · 95% seed bootstrap CI');save(fig,SWEEP,name)
    representative_figures(SWEEP,status['representative_seeds'],'load_1.00','15_burst_recovery_examples','16_replica_action_examples')

def representative_figures(out,seeds,label,burst_name,replica_name):
    plt=plot_setup(out)
    fig1,ax1=plt.subplots(3,3,figsize=(15,10),sharex=True)
    fig2,ax2=plt.subplots(3,2,figsize=(14,10),sharex=True)
    for row,(role,seed) in enumerate(seeds.items()):
        for policy,color in zip(POLICIES,['tab:blue','tab:orange']):
            folder=out/'runs'/label/f'seed_{seed:03d}'/policy
            slots=pd.read_csv(folder/'slot_trajectories.csv.gz');sv=pd.read_csv(folder/'pressure_services.csv.gz');actions=pd.read_csv(folder/'actions.csv.gz')
            lc=pd.read_csv(folder/'lifecycle_events.csv.gz')
            active=sv.groupby('slot').active.sum()
            for ax,y in zip(ax1[row],[slots.requests,slots.waiting_requests,slots.sla_breach_pct]):ax.plot(slots.slot,y,label=LABELS[policy],color=color)
            ax2[row,0].plot(active.index,active,label=LABELS[policy]+' ready',color=color)
            ax2[row,0].plot(slots.slot,slots.replicas,label=LABELS[policy]+' allocated',ls=':',color=color)
            for kind,style in [('scale_up','-'),('scale_down','--')]:
                g=actions[actions.kind==kind];counts=(g.time_s/.1+1e-7).astype(int).value_counts().reindex(range(100),fill_value=0)
                ax2[row,1].plot(counts.index,counts,label=LABELS[policy]+' '+kind,ls=style,color=color,alpha=.85)
            cold=lc[lc.kind=='cold_start'];counts=(cold.start_s/.1+1e-7).astype(int).value_counts().reindex(range(100),fill_value=0)
            ax2[row,1].scatter(counts.index[counts>0],counts[counts>0],marker='x',label=LABELS[policy]+' cold starts',color=color)
        for j,ax in enumerate(ax1[row]):ax.set_title(f'{role} DIRECT ΔSLA seed {seed}');ax.set_ylabel(['Offered requests/slot','Waiting requests','Arrival-cohort breaches (%)'][j]);ax.grid(alpha=.2)
        for ax in ax2[row]:ax.set_title(f'{role} DIRECT ΔSLA seed {seed}');ax.grid(alpha=.2)
        ax2[row,0].set_ylabel('Replicas');ax2[row,1].set_ylabel('Actions / cold starts per slot')
    for axes in (ax1,ax2):
        for ax in axes[-1]:ax.set_xlabel('Slot (0.1 s)')
        for ax in axes[0]:ax.legend(fontsize=7)
    fig1.suptitle('Best / lower-median / worst seed by paired DIRECT SLA difference');fig2.suptitle('Ready versus allocated replicas and lifecycle actions · deterministic seed selection')
    save(fig1,out,burst_name);save(fig2,out,replica_name)

def report_sweep(raw,tests,summary,br,status):
    means=mean_table(raw,'load_multiplier',METRICS+RESOURCE+QUEUE)
    tier=pd.read_csv(SWEEP/'tier_paired_tests.csv');classes=pd.read_csv(SWEEP/'model_class_paired_tests.csv')
    stats=tests[['load_multiplier','metric','delta_joint_minus_sla','delta_ci95_lower','delta_ci95_upper','p_value','p_value_holm','rank_biserial_correlation','wins','ties','losses','supported_direction']]
    narrative='A statistically supported SLA-breach crossover was observed within '+str(status['supported_crossing_intervals'])+'.' if status['supported_crossover'] else 'No statistically supported SLA-breach crossover was observed on the predefined 0.50×–2.00× grid.'
    methods='30 paired seeds at every load; seed arithmetic means ± sample SD and percentile bootstrap 95% CI, 10,000 resamples, RNG seed 73001. Wilcoxon two-sided; 12-decimal tie rule, positive rank-biserial effect favors JointSLA. Δ=Joint−SLA, positive worse. Holm: SLA+p95 across seven loads (14 primary), mean+p99 (14 secondary), tier SLA (21 exploratory), class SLA (21 exploratory). No equivalence margin or post-hoc threshold. `summary_statistics.csv` contains means, SD and CIs for all numeric metrics. All arrival-cohort requests including drain are counted; no drops/unplaced requests.'
    sections=[
        ('Research Question','How does JointSLA relative performance change with increasing hardware-grounded offered load? '+narrative),
        ('Frozen Hardware Baseline','The DIRECT result and all old profiles/controllers remain frozen. 1× reproduces DIRECT seeds 1/2/3: 54 exported physical/event trace tables, exact traffic/workload hashes; only nondeterministic timings excluded. No hardware was profiled again. One laptop GPU grounds isolated model stages, not ten physical deployed GPUs.'),
        ('Load Scaling Method','Conditional intensity λ_m=mλ_original. Thin whole existing compound-Poisson batches with independent shared uniform marks for m<1; superpose independent compound-Poisson batches at (m−1)λ for m>1. Keep original seeded noise and burst masks exactly. 1× returns the exact original tape. Separate keyed adapter RNG streams; original streams untouched. Service base rates, reservations and initial controller rates remain frozen. Thus changed offered arrivals, rather than updated initial priors, drive adaptation. Expected service/tier/model traffic proportions preserved, observed proportions retain sampling noise.'),
        ('Fairness and Hash Validation','All 210 multiplier/seed pairs use identical request tapes across policies. Per-pair traffic/workload hashes and full generated inputs retained. Every exported outcome re-read and independently checked against request, work, deadline, network and pipeline sums; every routing score/choice audited by the frozen independent reference. Protected baseline hashes verified before and after. See `validation.json`, `direct_reproduction.json`, `statistical_validation.json`.'),
        ('Pressure Characterization',table(pd.read_csv(SWEEP/'pressure_characterization.csv').groupby(['load_multiplier','policy'])[list(PRESSURE)+['average_cpu_utilization','average_gpu_utilization','pool_vram_occupancy_fraction','expected_gpu_offered_pressure','expected_cpu_offered_pressure']].mean().reset_index())+'\n\nExpected offered pressure uses exact class times and conditional rates, with mean work factor1; it is not a queueing prediction. Utilization measured by actual finite-resource integrals, not global-estimator offered diagnostic ratios. Slot-end waiting queues; decision-start active replicas/headroom. Queue occupancy is an absolute count because queues are unbounded. Pure capacity and cooldown/max-replica feasible scale-out flags are separate. Missing baseline routing-contention fraction is NA because it uses FIFO service dispatch, not explicit candidate routing. Shared realized node/service wait measures remain comparable. Per-node profiles in `node_pressure_characterization.csv`; full per-slot CPU/GPU/VRAM in each run.'),
        ('SLA Results Across Load',table(means[['load_multiplier','policy','sla_breach_rate']])+'\n\nSLA fractions over all offered requests; multiply by 100 for percent. '+narrative),
        ('Mean Latency',table(means[['load_multiplier','policy','mean_request_latency_ms']])+'\n\nRequest-weighted within seed, seed-weighted across Monte Carlo trials.'),
        ('p95 / p99',table(means[['load_multiplier','policy','p95_latency_ms','p99_latency_ms']])+'\n\nLinear request quantiles, averaged across seeds; tail improvements may disagree with mean/SLA. Metric-specific supported crossover brackets: '+json.dumps(status['metric_specific_crossovers'])+'. Brackets span opposite supported grid points, allowing statistically unresolved intermediate points; no exact continuous threshold is estimated.'),
        ('Crossover Analysis',narrative+'\n\n'+json.dumps(status,indent=2)+'\n\nA narrower gap is not a crossover. Observed sign-only transitions, if any, are exploratory without both supported directions.'),
        ('Tier-Specific Behavior',table(tier[['load_multiplier','tier','delta_joint_minus_sla','delta_ci95_lower','delta_ci95_upper','p_value_holm','supported_direction']])+'\n\nExploratory family of 21 tests. All Gold/Silver/Bronze retained; different signs are disclosed without claiming a continuous threshold.'),
        ('Model-Class Behavior',table(classes[['load_multiplier','model_class','delta_joint_minus_sla','delta_ci95_lower','delta_ci95_upper','p_value_holm','supported_direction']])+'\n\nLIGHT/MEDIUM/HEAVY mapping remains 16/16/8. These describe architecture/memory classes; actual measured GPU execution ordering need not increase with class.'),
        ('Replica Scaling',table(means[['load_multiplier','policy','average_replicas','peak_replicas','cold_starts','scale_outs','scale_ins']])+'\n\nAverage allocated count is exact integral, including cold/retiring replicas; ready replicas separately observed. Peak allocated count sampled at slot ends, unchanged definition.'),
        ('VRAM and Resource Use',table(means[['load_multiplier','policy','average_vram_residency_gib','peak_pool_vram_gib','average_cpu_utilization','average_gpu_utilization','total_actions','migrations']])+'\n\nVRAM integral and simultaneous peak include double reservation during migration. Compute/free-token headroom is different from reserved-capacity headroom.'),
        ('Queue Behavior',table(means[['load_multiplier','policy',*QUEUE]])+'\n\nService and node queue delay summed per request. Unlimited queues fully drained; recovery/queues at the observation horizon remain separately disclosed.'),
        ('Burst Recovery',table(br.groupby(['load_multiplier','policy']).mean(numeric_only=True).drop(columns='seed').reset_index())+'\n\nEach service burst is a diagnostic event. Threshold=max(preburst queue,1); recovery searched after burst end before next burst/horizon. Delay means are conditional on observed recovery/scale-out; censoring fractions are mandatory and not imputed. SLA window start→recovery/next burst; overlapping service windows do not duplicate requests across services. Best/median/worst examples selected by sorted DIRECT paired SLA differences, seed as tie-breaker; representative seeds '+str(status['representative_seeds'])+'.'),
        ('Performance-Resource Frontier','Three observed traces: SLA vs replicas, p95 vs VRAM, SLA vs actions. Each marker is a distinct load, not an optimized point at equal QoS. Lower cost alongside worse SLA demonstrates a trade-off, not dominance. No convex optimal frontier or budget-matched controller superiority is established.'),
        ('Statistical Results',methods+'\n\n'+table(stats,6)),
        ('Operating Envelope',table(pd.read_csv(SWEEP/'operating_envelope.csv'))+'\n\nUnresolved points are approximately competitive only as a descriptive label; failed rejection does not prove equivalence. Primary SLA label may differ from p95/p99; inspect all four paired rows.'),
        ('Negative Results',narrative+' Every seed and loss retained in `negative_seed_cases.csv`; no tuning, deleting unfavorable points or moving deadlines. Original DIRECT aggregate disadvantage remains valid.'),
        ('Threats to Validity','Seven finite load points, one GPU profile set, synthetic nodes/network/concurrency and workload. Controller global timing/cold priors approximate class physics. Extra traffic adapter preserves conditional intensity/cluster law, not identical realized tier fractions or perfect across-load nesting. Shared tapes induce dependence across loads; Holm does not require independence. Unlimited queues, short horizon, slot-quantized cold times, observational burst diagnostics and conditional censoring can limit deployment transfer. Instrumentation timing varies with host load; observational work excluded from the inherited snapshot timers but included in total simulation wall time.'),
        ('Safe Paper Claims',narrative+' This study characterizes a frozen controller’s operating envelope and performance-resource trade-off under hardware-grounded model profiles, with paired seeds and preserved negative results. Metric-specific crossover is essential: the JointSLA mean latency and p95/p99 advantage at 1.75×–2× is supported, while its aggregate breach advantage at 2× is not. Gold remains significantly worse under JointSLA at every tested load; Bronze becomes better at 1.75×–2×. No class-specific JointSLA breach advantage is supported. JointSLA uses fewer replicas/VRAM at all seven loads, but fewer actions at only five loads; its action count exceeds SLA-aware at 1.75×–2×. Mechanism attribution is addressed separately by the factorial diagnostic experiment.'),
        ('Claims We Cannot Make','Universal superiority, a crossover beyond the tested grid, formal equivalence at unresolved loads, a real 6G deployment, true optimal frontier, carrier-grade validation, or isolated causal explanation from pressure trends alone. No algorithm improvements were made. Statistical support for p99 does not imply support for breach or p95.')]
    (SWEEP/'report.md').write_text('\n\n'.join('# '+h+'\n\n'+b for h,b in sections)+'\n',encoding='utf-8')

def decomposition_analysis(raw):
    assert len(raw)==160 and set(raw.regime)==set(REGIMES) and set(raw.seed)==set(range(1,11))
    metrics=METRICS+RESOURCE+QUEUE+('action_budget_exhausted_fraction','queue_changed_choice_fraction','average_active_replicas_per_service')
    rows=[];perseed=[]
    for regime,g in raw.groupby('regime'):
        for metric in metrics:
            p=g.pivot(index='seed',columns='policy',values=metric).sort_index();d=p.joint_sla-p.sla_aware
            rows.append(dict(regime=regime,metric=metric,n=len(d),mean_sla_aware=float(p.sla_aware.mean()),mean_joint_sla=float(p.joint_sla.mean()),delta_joint_minus_sla=float(d.mean()),delta_std=float(d.std()),wins=int((np.round(d,12)<0).sum()),ties=int((np.round(d,12)==0).sum()),losses=int((np.round(d,12)>0).sum())))
            perseed.extend(dict(regime=regime,metric=metric,seed=int(s),delta_joint_minus_sla=float(v)) for s,v in d.items())
    summary=pd.DataFrame(rows);deltas=pd.DataFrame(perseed)
    # Exogenous regime pressures separate physical supply changes from policy use.
    from .design import regime_inputs
    from hardware_grounded.experiment import input_summary
    characterization=[]
    for regime in REGIMES:
        for seed in range(1,11):
            c,w,cs=regime_inputs(regime,seed)
            characterization.append(dict(regime=regime,**input_summary(c,w,cs)))
    pd.DataFrame(characterization).to_csv(CAUSAL/'regime_pressure_characterization.csv',index=False)
    # No confirmatory p-values or low-N significance claims.
    descriptions=[]
    for (regime,policy),g in raw.groupby(['regime','policy']):
        for metric in metrics:descriptions.append(dict(regime=regime,policy=policy,metric=metric,n=10,mean=float(g[metric].mean()),std=float(g[metric].std())))
    pd.DataFrame(descriptions).to_csv(CAUSAL/'regime_summary.csv',index=False)
    summary.to_csv(CAUSAL/'paired_differences.csv',index=False);deltas.to_csv(CAUSAL/'paired_seed_differences.csv',index=False)
    summary[summary.metric.isin(RESOURCE)].to_csv(CAUSAL/'resource_differences.csv',index=False)
    summary[summary.metric.isin(QUEUE)].to_csv(CAUSAL/'queue_differences.csv',index=False)
    br=burst_summary(pd.read_csv(CAUSAL/'burst_recovery.csv'),'regime');br.to_csv(CAUSAL/'burst_summary.csv',index=False)
    burst_delta=[]
    for regime,g in br.groupby('regime'):
        for metric in ('preburst_active_replicas','queue_growth','recovery_censored_fraction','recovery_window_breach_rate'):
            p=g.pivot(index='seed',columns='policy',values=metric);d=p.joint_sla-p.sla_aware
            burst_delta.append(dict(regime=regime,metric=metric,mean_delta=float(d.mean()),delta_std=float(d.std()),n=10))
    pd.DataFrame(burst_delta).to_csv(CAUSAL/'burst_differences.csv',index=False)
    effects=[];interactions=[]
    mapping={bits:name for name,bits in REGIMES.items()}
    for metric,g in deltas.groupby('metric'):
        pivot=g.pivot(index='seed',columns='regime',values='delta_joint_minus_sla')
        contrasts={}
        for mask in range(1,8):
            bits=tuple((mask>>j)&1 for j in range(3));value=np.zeros(10)
            for sub in range(8):
                if sub&mask==sub:
                    sb=tuple((sub>>j)&1 for j in range(3));sgn=(-1)**(sum(bits)-sum(sb));value+=sgn*pivot[mapping[sb]].to_numpy()
            contrasts[mask]=value
            interactions.append(dict(metric=metric,term='×'.join(('execution','vram','cold')[j] for j in range(3) if mask>>j&1),mean_contrast=float(value.mean()),contrast_std=float(value.std(ddof=1)),n=10))
        for j,factor in enumerate(('execution','vram','cold')):
            # Symmetric Shapley allocation of anchored factorial interactions.
            attribution=sum(v/int(mask.bit_count()) for mask,v in contrasts.items() if mask>>j&1)
            marginals=[]
            for bits,regime in mapping.items():
                if not bits[j]:changed=list(bits);changed[j]=1;marginals.append(pivot[mapping[tuple(changed)]].to_numpy()-pivot[regime].to_numpy())
            avg=np.mean(marginals,axis=0)
            effects.append(dict(metric=metric,factor=factor,mean_factorial_marginal=float(avg.mean()),marginal_std=float(avg.std(ddof=1)),shapley_reversal_contribution=float(attribution.mean()),shapley_std=float(attribution.std(ddof=1)),n=10))
        total=sum(sum(v/int(mask.bit_count()) for mask,v in contrasts.items() if mask>>j&1) for j in range(3))
        assert np.allclose(total,pivot.D7-pivot.D0,atol=1e-10)
    effect=pd.DataFrame(effects);interaction=pd.DataFrame(interactions)
    effect.to_csv(CAUSAL/'factor_effects.csv',index=False);interaction.to_csv(CAUSAL/'interaction_effects.csv',index=False)
    sla=effect[effect.metric=='sla_breach_rate'];dominant=sla.loc[sla.shapley_reversal_contribution.abs().idxmax()].factor
    status=dict(exploratory_n=10,dominant_sla_factor_by_absolute_shapley=dominant,
        exact_factorial_decomposition=True,shapley_identity_verified=True,
        extension_to_30_seeds=False,extension_reason='Full paired factorial isolates E/V/C combinations; existing DIRECT 30-seed endpoint plus full pressure sweep supply confirmatory endpoint evidence. No additional 30-seed factor run selected from outcomes; factorial magnitudes remain exploratory.',
        caveat='Component interventions include frozen global controller estimator inputs as well as worker physics; attribution within this simulator is not proof of an isolated real-world causal mechanism.')
    write_json(CAUSAL/'mechanism_analysis.json',status)
    figures_causal(summary,raw);report_causal(raw,summary,effect,interaction,br,status)
    return status

def figures_causal(summary,raw):
    plt=plot_setup(CAUSAL)
    specs=[('01_sla_difference_by_regime','sla_breach_rate',100,'Δ SLA (percentage points)'),('02_p95_difference_by_regime','p95_latency_ms',1,'Δ p95 (ms)'),
        ('03_replica_difference_by_regime','average_replicas',1,'Δ average allocated replicas'),('04_cold_start_difference_by_regime','cold_starts',1,'Δ cold starts/run'),('05_queue_difference_by_regime','mean_queue_delay_ms',1,'Δ mean queue delay (ms)')]
    for name,metric,factor,label in specs:
        f=summary[summary.metric==metric].sort_values('regime');fig,ax=plt.subplots(figsize=(8,4.5))
        ax.bar(f.regime,f.delta_joint_minus_sla*factor,yerr=f.delta_std*factor,capsize=3,color=['tab:blue' if v<0 else 'tab:orange' for v in f.delta_joint_minus_sla]);ax.axhline(0,color='black',lw=1)
        ax.set(ylabel=label,title='Exploratory 10 paired seeds · mean difference ± sample SD',xlabel='E/V/C factorial regime (definitions in report)');ax.grid(axis='y',alpha=.2);save(fig,CAUSAL,name)
    selections=json.loads((SWEEP/'hypotheses.json').read_text())['representative_seeds']
    # D7 contains seeds 1–10. Select independently by the same predeclared rule.
    f=raw[raw.regime=='D7'].pivot(index='seed',columns='policy',values='sla_breach_rate');f['delta']=f.joint_sla-f.sla_aware;f=f.sort_values(['delta','seed'])
    seeds={'best':int(f.index[0]),'median':int(f.index[(len(f)-1)//2]),'worst':int(f.index[-1])}
    write_json(CAUSAL/'representative_seeds.json',dict(selection='D7 N=10 sorted paired ΔSLA then seed; lower median',seeds=seeds))
    representative_figures(CAUSAL,seeds,'D7','06_burst_recovery_example','07_replica_time_series_example')

def report_causal(raw,summary,effect,interaction,br,status):
    performance=summary[summary.metric.isin(METRICS)]
    resource=summary[summary.metric.isin(('average_replicas','average_vram_residency_gib','cold_starts','scale_outs','scale_ins','total_actions'))]
    mechanisms=mean_table(raw,'regime',('mean_queue_delay_ms','average_queue_length','average_replicas','average_active_replicas_per_service','scale_outs','scale_ins','cold_starts','action_budget_exhausted_fraction','queue_changed_choice_fraction'))
    methods='Exploratory full 2³ factorial, seeds 1–10 paired within and across D0–D7; every regime identical traffic/deadlines/network/resources except selected E/V/C intervention. Δ=Joint−SLA. Report means ± sample SD and paired descriptive differences; no confirmatory significance claim at N=10. Shapley allocation symmetrically divides anchored interaction contrasts across constituent factors and sums exactly to the observed D7−D0 reversal. Factorial averaged marginals and all pair/triple interactions retained. Not strict external causality.'
    sla=summary[summary.metric=='sla_breach_rate'].set_index('regime')
    contributions=effect[effect.metric=='sla_breach_rate'].set_index('factor').shapley_reversal_contribution
    delta_shift=float(sla.loc['D7','delta_joint_minus_sla']-sla.loc['D0','delta_joint_minus_sla'])
    main=interaction[(interaction.metric=='sla_breach_rate')&(~interaction.term.str.contains('×'))].mean_contrast.sum()
    explanation=f"Across the same ten seeds, the Joint−SLA breach gap moves from {100*sla.loc['D0','delta_joint_minus_sla']:.3f}pp (D0) to {100*sla.loc['D7','delta_joint_minus_sla']:.3f}pp (D7): a {100*delta_shift:.3f}pp reversal. Symmetric Shapley contributions: memory {100*contributions['vram']:.3f}pp, cold {100*contributions['cold']:.3f}pp, execution {100*contributions['execution']:.3f}pp. These include allocated interaction effects; they are not isolated one-factor effects. Anchored single-factor contrasts sum to {100*main:.3f}pp; combined interactions account for the remaining {100*(delta_shift-main):.3f}pp."
    checks="Mechanistic checks A–G: (A) E alone reduces mean queue delay substantially for both policies (see D0→D1), yet improves the relative JointSLA SLA gap; short execution alone does not explain the reversal. (B) queue-changed routing choices decrease with E, but this is a diagnostic, not proof that queue-aware routing loses value. (C) low DIRECT replica count is associated with fewer scale-outs and a smaller standing ready pool; JointSLA does not trigger more scale-ins than SLA-aware in D7, so 'more aggressive scale-in' is not established by action counts. (D) preburst ready replicas are larger under SLA-aware and observed burst queues smaller at DIRECT. (E) class readiness is 100/200/500ms versus roughly 5.5–7.6ms isolated pipelines; C compounds E/V effects. (F) observed first postburst scale-out is faster for JointSLA conditional on a scale-out occurring; it occurs less often and starts with fewer ready replicas. This does not support a blanket 'late reaction' claim. (G) budget exhaustion is lower under JointSLA at DIRECT; no budget intervention was run, so scarcity is not established as the primary cause. Global estimator mismatch, consolidation and slow recovery remain interacting mechanism explanations rather than isolated proven mediators."
    sections=[
        ('Motivation','Diagnose the preserved DIRECT reversal without modifying either controller. '+methods),
        ('Frozen Reference Configurations','D0 uses original MEDIUM synthetic config and uniform workers; D7 matches frozen hardware DIRECT on class execution, memory and readiness. Full sweep 1× seeds1/2/3 reproduced frozen traces. D7 decomposition seeds1–10 also checked against the frozen endpoint; D0 checked against original synthetic results. Controllers and estimator formulas unchanged.'),
        ('Decomposition Design',methods+' The execution/cold component includes hardware values in the unchanged global estimator interface and per-class worker physics. Cannot separate estimator mismatch from physical workload effect without another separately designed experiment.'),
        ('D0-D7 Definitions',table(pd.DataFrame([dict(regime=k,execution=bool(e),vram=bool(v),cold=bool(c)) for k,(e,v,c) in REGIMES.items()]))+'\n\nE=real preprocess+upload / inference / postprocess. V=real peak allocated VRAM. C=real class cold readiness rounded upward to slots. Cold first-request 5ms penalty and 100ms/10ms migration model remain synthetic everywhere. Initial services/tapes stay unchanged.'),
        ('Execution-Time Effect',table(effect[effect.factor=='execution'])+'\n\nThe E toggle substitutes hardware stage times and the fixed population mean controller stage prior. Shorter inference does not guarantee less total queueing when policy-induced replica counts change.'),
        ('VRAM Effect',table(effect[effect.factor=='vram'])+'\n\nOnly reservation footprint changes. Actual concurrency remains finite and unchanged; VRAM alone is not throughput.'),
        ('Cold-Start Effect',table(effect[effect.factor=='cold'])+'\n\nSynthetic readiness 1 slot; measured classes 1/2/5 slots. Slow relative recovery is physically grounded but slot-quantized; extra first-request penalty unchanged. Each effect depends on other components.'),
        ('Combined Effects',table(performance)+'\n\nOriginal and fully calibrated endpoint gaps are compared on the same ten seeds, not cross-population seed averages.'),
        ('Queue Pressure',table(pd.read_csv(CAUSAL/'regime_pressure_characterization.csv').groupby('regime')[['hardware_gpu_pressure','hardware_cpu_pressure','initial_vram_pressure']].mean().reset_index())+'\n\n'+table(mechanisms)+'\n\nOffered ratios use per-class physical times. `queue_changed_choice_fraction` is a retrospective candidate-choice diagnostic, not a causal no-queue ablation. Lower value does not establish lower benefit of queue-aware routing. Action-budget exhaustion is a descriptive frequency, not proof that a larger budget would fix SLA.'),
        ('Replica Dynamics',table(resource)+'\n\nDo not infer aggressive scale-in solely from lower replica counts: fewer scale-outs, readiness and retiring lifetime can all produce consolidation. Three representative D7 seeds selected by sorted paired ΔSLA, explicitly labeled best/lower-median/worst. Ready and allocated replicas distinguished.'),
        ('Burst Recovery',table(br.groupby(['regime','policy']).mean(numeric_only=True).drop(columns='seed').reset_index())+'\n\nPreburst replicas, queue growth, first scale-out latency, cold readiness, recovery latency and recovery-window SLA exported per burst. Conditional recovery means require censoring fractions beside them; no failed recovery removed.'),
        ('Dominant Contributors',json.dumps(status,indent=2)+'\n\n'+table(effect[effect.metric=='sla_breach_rate'])+'\n\nDominant means largest absolute symmetric contribution to the change in controller SLA gap, not universally dominant physical cause.'),
        ('Interaction Effects',table(interaction[interaction.metric.isin(('sla_breach_rate','p95_latency_ms'))])+'\n\nNon-additivity means one-factor-at-a-time descriptions cannot explain the total endpoint reversal without interactions. All contrasts have paired seed SD; no claim of independently significant interaction at N=10.'),
        ('What Explains the DIRECT Reversal?',explanation+'\n\n'+checks+'\n\nA dedicated scaling/routing/budget intervention would be needed to prove that any individual algorithmic mechanism caused the loss.'),
        ('Threats to Validity','Ten seeds, synthetic continuum, single GPU isolated model profiles, model class and SLA correlations from fixed IDs, global estimator/class physics mismatch, short horizon, memory workspace assumptions and slot quantization. Full factorial isolates defined simulator interventions but not real-world exogenous hardware effects. Mechanism time series are observational mediators; an action-budget causal ablation was deliberately not run. No 30-seed factor validation added after inspecting which factor looked favorable.'),
        ('Safe Interpretation','A. No statistically supported aggregate SLA-breach crossover; 2× has a favorable mean sign but CI crosses zero. Supported direction changes do occur for mean/p95/p99. B. Observed sign changes: SLA 1.75×→2×; mean1.50×→1.75×; p95 1.00×→1.25×; p99 0.50×→0.75×. Support brackets are broader and reported in `metric_crossovers.json`; no exact continuous threshold is established. C. Memory has the largest symmetric SLA-gap contribution, with large execution/memory/cold interactions. D. Frame contribution as pressure-dependent operating-envelope characterization and performance-resource trade-off. E. This strengthens a transparent mechanism/operating-envelope research case while weakening universal-superiority or SLA-robustness claims; it does not guarantee a B-level venue acceptance. F. A new model-aware/consolidation-aware version is scientifically motivated as a separate preregistered hypothesis, validated on held-out seeds rather than tuned to these results. No algorithm changes were made here. All factor evidence remains exploratory at N=10; no 30-seed factor extension claimed.')]
    (CAUSAL/'report.md').write_text('\n\n'.join('# '+h+'\n\n'+b for h,b in sections)+'\n',encoding='utf-8')
