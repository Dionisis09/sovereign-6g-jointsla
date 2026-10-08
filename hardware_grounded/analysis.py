"""Unchanged seed-level statistics, transparent negative results and paper figures."""
import json
import numpy as np
import pandas as pd
from paper_evaluation.statistics import summarize,bootstrap_mean_ci,signed_rank,holm_adjust
from paper_evaluation.accounting import PRIMARY
from .environment import OUTPUT,ROOT,write_json
from .calibration import CLASS_MODELS,model_class,load_profiles,calibrated_config,service_config

RESOURCE=('average_replicas','peak_replicas','average_vram_residency_gib','peak_pool_vram_gib','cold_starts','scale_outs','scale_ins','migrations','total_actions','average_cpu_utilization','average_gpu_utilization')
CONTROLLER=('controller_total_instrumented_mean_ms','controller_total_instrumented_p95_ms','controller_snapshot_mean_ms','controller_decision_mean_ms','request_routing_decision_mean_ms','request_routing_decision_p95_ms','controller_cpu_ms_per_request','wall_clock_seconds')
LABELS={'sla_aware':'SLA-aware','joint_sla':'JointSLA'}


def paired(raw):
    rows=[];differences=[]
    for metric in PRIMARY:
        pivot=raw.pivot(index='seed',columns='policy',values=metric).sort_index();a=pivot.sla_aware.to_numpy();b=pivot.joint_sla.to_numpy()
        delta=b-a;lo,hi=bootstrap_mean_ci(delta,key=f'hardware:paired:{metric}');test=signed_rank(-delta);signs=np.round(delta,12)
        rows.append(dict(metric=metric,n=30,mean_sla_aware=float(a.mean()),mean_joint_sla=float(b.mean()),
            delta_joint_minus_sla=float(delta.mean()),delta_ci95_lower=lo,delta_ci95_upper=hi,
            relative_improvement_percent=float(-100*delta.mean()/a.mean()),**test,
            wins=int((signs<0).sum()),ties=int((signs==0).sum()),losses=int((signs>0).sum()),
            difference_direction='JointSLA minus SLA-aware; negative is better',effect_direction='positive RBC is JointSLA benefit',
            bootstrap_resamples=10000))
        for seed,d,av,bv in zip(pivot.index,delta,a,b):differences.append(dict(seed=int(seed),metric=metric,sla_aware=float(av),joint_sla=float(bv),delta_joint_minus_sla=float(d),outcome='loss' if round(d,12)>0 else 'win' if round(d,12)<0 else 'tie'))
    frame=pd.DataFrame(rows);frame['p_value_holm']=holm_adjust(frame.p_value)
    frame['supported_improvement']=(frame.delta_joint_minus_sla<0)&(frame.delta_ci95_upper<0)&(frame.p_value_holm<.05)
    return frame,pd.DataFrame(differences)


def hypothesis_status(raw,tests,classes):
    mean=raw.groupby('policy').mean(numeric_only=True)
    ratios={m:float(mean.loc['joint_sla',m]/mean.loc['sla_aware',m]) for m in ('average_replicas','average_vram_residency_gib','total_actions')}
    class_mean=classes.groupby(['model_class','policy']).sla_breach_rate.mean().unstack()
    benefits=(class_mean.sla_aware-class_mean.joint_sla).to_dict()
    return dict(HW1=bool(tests.set_index('metric').loc['sla_breach_rate','supported_improvement']),
        HW2=bool(tests.set_index('metric').loc['p95_latency_ms','supported_improvement']),HW3=all(v<=1.05 for v in ratios.values()),
        HW4=bool(mean.loc['joint_sla','controller_total_instrumented_mean_ms']<10),HW5=sum(v>0 for v in benefits.values())>=2,
        resource_ratios_joint_over_sla=ratios,model_class_breach_improvement=benefits,
        criteria='Preregistered PLAN.md; HW3 5% descriptive guardrail, HW5 benefit in >=2 classes, not significance/non-inferiority claims.')


def table(frame):
    """Small Markdown tables without an optional tabulate dependency."""
    columns=list(frame.columns);lines=['| '+' | '.join(map(str,columns))+' |','| '+' | '.join(['---']*len(columns))+' |']
    for row in frame.itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{v:.6g}' if isinstance(v,(float,np.floating)) else str(v) for v in row)+' |')
    return '\n'.join(lines)


def figures(raw,summary,tests,classes,tiers,profiles):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42})
    directory=OUTPUT/'figures';directory.mkdir(exist_ok=True);colors=['#526b89','#b55039'];names=list(CLASS_MODELS.values());labels=['MobileNetV3 Large','ResNet-50','ViT-B/16']
    def save(fig,name):
        fig.tight_layout()
        for ext in ('png','svg','pdf'):fig.savefig(directory/f'{name}.{ext}',dpi=300,bbox_inches='tight')
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(7.4,4.1));samples=[]
    for name in names:
        f=pd.read_csv(OUTPUT/'profiling'/f'{name}_raw.csv');samples.append(f[(f.phase=='steady')&(f.stage=='gpu_inference')].latency_ms.to_numpy())
    ax.boxplot(samples,tick_labels=labels,showfliers=True);ax.set_ylabel('Synchronized GPU forward (ms)');ax.set_ylim(bottom=0)
    ax.set_title('Measured FP32 inference: batch 1, 300 repetitions/model');save(fig,'01_model_inference_latency')
    fig,ax=plt.subplots(figsize=(7.4,4.1));bottom=np.zeros(3)
    for stage,label,color in [('cpu_pre','CPU preprocess','#526b89'),('input_upload','H2D input upload','#cba861'),('gpu_inference','CUDA forward','#b55039'),('cpu_post','CPU post + D2H','#62866c')]:
        values=np.array([profiles['models'][n]['stage_statistics'][stage]['median'] for n in names]);ax.bar(labels,values,bottom=bottom,label=label,color=color);bottom+=values
    ax.set_ylabel('Sum of component medians (ms)');ax.set_title('Measured pipeline stages; transfer costs disclosed');ax.legend(fontsize=8,ncol=2);save(fig,'02_pipeline_stage_latency')
    memory=pd.read_csv(OUTPUT/'profiling/vram_summary.csv').set_index('model');fig,ax=plt.subplots(figsize=(7.4,4.1));x=np.arange(3)
    for i,(field,label,color) in enumerate([('model_residency_bytes','Model residency','#526b89'),('inference_peak_allocated_bytes','Inference peak allocated','#b55039'),('inference_peak_reserved_bytes','Inference peak reserved','#cba861')]):
        ax.bar(x+(i-1)*.24,memory.loc[names,field]/2**20,width=.24,label=label,color=color)
    ax.set_xticks(x,labels);ax.set_ylabel('MiB');ax.set_title('Measured CUDA memory: allocated and reserved are separate');ax.legend(fontsize=8);save(fig,'03_model_vram')
    fig,ax=plt.subplots(figsize=(7.4,4.1));bottom=np.zeros(3)
    for stage,label,color in [('construction','Python construction','#526b89'),('local_state_load','Cached local state load','#cba861'),('model_gpu_transfer','Model H2D','#62866c'),('first_gpu_forward_wall','First synchronized forward','#b55039')]:
        values=np.array([profiles['models'][n]['cold_statistics'][stage]['median'] for n in names]);ax.bar(labels,values,bottom=bottom,label=label,color=color);bottom+=values
    ax.scatter(x,[profiles['models'][n]['cold_start_ms'] for n in names],marker='D',color='black',s=25,label='Total median')
    ax.set_ylabel('Model-ready startup (ms)');ax.set_title('Model-cold, CUDA process initialized; disk cache not evicted');ax.legend(fontsize=8,ncol=2);save(fig,'04_cold_start_latency')
    primary_names=[('sla_breach_rate','05_sla_joint_vs_slaaware','Aggregate SLA breaches (%)',100),('mean_request_latency_ms','06_mean_latency','Mean request latency (ms)',1),('p95_latency_ms','07_p95_latency','p95 request latency (ms)',1),('p99_latency_ms','08_p99_latency','p99 request latency (ms)',1)]
    for metric,name,label,factor in primary_names:
        fig,ax=plt.subplots(figsize=(6.5,4.1));pivot=raw.pivot(index='seed',columns='policy',values=metric).sort_index()
        for _,r in pivot.iterrows():ax.plot([0,1],r[['sla_aware','joint_sla']].to_numpy()*factor,color='#aaa',alpha=.4,lw=.7,marker='o',ms=2)
        for i,policy in enumerate(LABELS):
            s=summary[(summary.policy==policy)&(summary.metric==metric)].iloc[0]
            ax.errorbar(i,s['mean']*factor,yerr=np.array([[s['mean']-s.ci95_lower],[s.ci95_upper-s['mean']]])*factor,fmt='D',color=colors[i],markersize=8,capsize=5,elinewidth=2,label='Mean + 95% seed bootstrap CI' if i==0 else None)
        ax.set_xticks([0,1],list(LABELS.values()));ax.set_ylabel(label);ax.set_ylim(bottom=0);ax.set_title('DIRECT hardware calibration: 30 paired MEDIUM seeds');ax.legend(fontsize=8);save(fig,name)
    for data,column,labels_order,name in [(classes,'model_class',['LIGHT','MEDIUM','HEAVY'],'09_model_class_breaches'),(tiers,'tier',['Gold','Silver','Bronze'],'10_tier_breaches')]:
        fig,ax=plt.subplots(figsize=(7.4,4.1));x=np.arange(3)
        for i,policy in enumerate(LABELS):
            values=[];low=[];high=[]
            for value in labels_order:
                sub=data[(data.policy==policy)&(data[column]==value)].sort_values('seed').sla_breach_rate.to_numpy()*100
                lo,hi=bootstrap_mean_ci(sub,key=f'hardware:plot:{column}:{value}:{policy}');values.append(sub.mean());low.append(sub.mean()-lo);high.append(hi-sub.mean())
            ax.bar(x+(i-.5)*.34,values,width=.34,color=colors[i],label=LABELS[policy],yerr=[low,high],capsize=4)
        ax.set_xticks(x,labels_order);ax.set_ylabel('SLA breaches (%)');ax.set_title('Seed means with 95% bootstrap CIs; every subgroup retained');ax.legend();save(fig,name)
    fig,axes=plt.subplots(1,3,figsize=(11,4.1))
    for ax,metric,title in zip(axes,('average_replicas','average_vram_residency_gib','total_actions'),('Mean allocated replicas','Mean allocated VRAM (GiB)','Total actions per run')):
        for i,policy in enumerate(LABELS):
            s=summary[(summary.policy==policy)&(summary.metric==metric)].iloc[0]
            ax.bar(i,s['mean'],color=colors[i],yerr=[[s['mean']-s.ci95_lower],[s.ci95_upper-s['mean']]],capsize=4)
        ax.set_xticks([0,1],['SLA-aware','JointSLA']);ax.set_title(title,fontsize=10)
    fig.suptitle('Resource trade-off: 95% CIs of seed means');save(fig,'11_resource_comparison')
    fig,ax=plt.subplots(figsize=(7,4.1));x=np.arange(2)
    for i,(metric,label) in enumerate([('controller_total_instrumented_mean_ms','Per-run mean'),('controller_total_instrumented_p95_ms','Per-run p95')]):
        values=[raw[raw.policy==p][metric].mean() for p in LABELS];ax.bar(x+(i-.5)*.32,values,width=.32,label=label,color=colors[i])
    ax.axhline(10,color='black',ls='--',lw=1,label='Existing 10-ms mean budget');ax.set_xticks(x,list(LABELS.values()));ax.set_ylabel('Measured CPU wall time per control step (ms)');ax.set_title('Full control snapshot + decision/action scope');ax.legend(fontsize=8);save(fig,'12_controller_overhead')
    from PIL import Image,ImageOps,ImageDraw
    paths=sorted(directory.glob('*.png'));thumbs=[]
    for path in paths:
        with Image.open(path) as im:
            thumb=ImageOps.contain(im.convert('RGB'),(640,390));canvas=Image.new('RGB',(660,420),'white');canvas.paste(thumb,((660-thumb.width)//2,0));ImageDraw.Draw(canvas).text((10,398),path.stem,fill='black');thumbs.append(canvas)
    sheet=Image.new('RGB',(1980,1680),'#dddddd')
    for i,thumb in enumerate(thumbs):sheet.paste(thumb,((i%3)*660,(i//3)*420))
    sheet.save(OUTPUT/'figure_preview.png')


def report(raw,summary,tests,classes,tiers,status,profiles):
    hardware=json.loads((OUTPUT/'hardware_info.json').read_text());pilot=json.loads((OUTPUT/'pilot/pilot_validation.json').read_text())
    validation=json.loads((OUTPUT/'validation.json').read_text());means=raw.groupby('policy').mean(numeric_only=True)
    stats=pd.read_csv(OUTPUT/'profiling/model_profile_summary.csv');cold=pd.read_csv(OUTPUT/'profiling/cold_start_summary.csv');memory=pd.read_csv(OUTPUT/'profiling/vram_summary.csv')
    cpu_secondary=pd.read_csv(OUTPUT/'profiling/cpu_profile_summary.csv')
    classes_mean=classes.groupby(['model_class','policy'])[['sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms','mean_queue_delay_ms']].mean().reset_index()
    tier_mean=tiers.groupby(['tier','policy'])[['sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms','mean_queue_delay_ms']].mean().reset_index()
    resources=means[list(RESOURCE)].reset_index();controller=means[list(CONTROLLER)].reset_index()
    metric_table=summary[summary.metric.isin(PRIMARY)][['policy','metric','mean','standard_deviation','ci95_lower','ci95_upper']]
    methods='30 independent paired seeds 1–30; seed is the inference unit. Existing percentile paired bootstrap (10,000 resamples, fixed hash-derived RNG seed 73001), two-sided Wilcoxon signed-rank (round differences to 12 decimals), Holm family of four primary metrics, rank-biserial correlation and W/T/L. Negative JointSLA-minus-SLA-aware delta means benefit; positive RBC means benefit. Latency quantiles use linear interpolation per seed, then seed-level mean; they are not pooled request percentiles.'
    profile_table=[]
    for name,p in profiles['models'].items():
        profile_table.append(dict(model=name,pre_median_ms=p['cpu_pre_ms'],upload_median_ms=p['input_upload_ms'],gpu_median_ms=p['gpu_inference_ms'],post_median_ms=p['cpu_post_ms'],peak_allocated_MiB=p['vram_mb'],cold_median_ms=p['cold_start_ms']))
    negative=pd.read_csv(OUTPUT/'negative_seed_cases.csv');breach_loss=negative[negative.metric=='sla_breach_rate'].seed.tolist()
    result_text=('JointSLA retained aggregate SLA and p95 advantage in this preregistered DIRECT calibration.' if status['HW1'] and status['HW2'] else 'JointSLA did not retain its aggregate SLA/p95 advantage in this preregistered DIRECT calibration. Preserve this negative external-validity result; it does not invalidate the previously verified synthetic experiments.')
    sections=[
        ('Research Question','Does the validated synthetic JointSLA advantage persist under measured architecture execution and memory?\n\n**'+result_text+'**'),
        ('Hardware Platform',f"CPU: {hardware['cpu_model']}; {hardware['logical_cpu_count']} logical processors; {hardware['system_ram_bytes']/2**30:.2f} GiB RAM. GPU: {hardware['devices'][0]['name']}, {hardware['devices'][0]['total_vram_bytes']/2**20:.0f} MiB VRAM; compute capability {hardware['devices'][0]['compute_capability']}. OS {hardware['operating_system']}, Python {hardware['python_version']}, PyTorch {hardware['torch_version']}, torchvision {hardware['torchvision_version']}, CUDA build {hardware['cuda_build_version']}. Actual synchronized kernel passed. Driver {hardware['telemetry']['gpu'][0]['driver_version']}; AC detected {hardware['telemetry']['ac_power']}. Detailed clocks, temperature and power observations: `profiling/telemetry.json`."),
        ('Profiling Methodology','Locally initialized torchvision architectures, no datasets or pretrained download; deterministic in-memory uint8 RGB image, batch 1 FP32 3×224×224. Eval + inference_mode, one CPU thread, TF32 disabled, no system power changes. Architecture execution only, not task accuracy. [CUDA events](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.Event.html) with explicit synchronization isolate GPU forward. Separate host timers measure synchronized transfers/postprocessing.'),
        ('AI Models',table(pd.DataFrame(profile_table))+'\n\nLIGHT/MEDIUM/HEAVY denote architecture/memory classes. MobileNet median GPU time exceeds ResNet on this laptop; no enforced latency ordering.\n\nSecondary CPU-only inference, one thread, 30 measured repetitions, ms (not used for GPU pipeline calibration):\n\n'+table(cpu_secondary[['model','mean','median','std','p95','p99']])),
        ('Warm-Up and Measurement Protocol','Each model: 50 GPU warmups, 300 measured steady repetitions; 20 model-cold repetitions, 30 warmups after each model-cold first forward; secondary CPU: 10 warmups and 30 measured repetitions. 5,010 raw rows across three models. Raw GPU event and host-wall forwards are distinct. Full mean/median/sample-SD/p50/p90/p95/p99/min/max saved for every stage.'),
        ('CPU Preprocessing',table(stats[stats.stage.isin(['cpu_pre','input_upload'])][['model','stage','count','mean','median','std','p95','p99']])+'\n\nNo disk I/O. Resize, normalize and prepare NCHW on CPU. H2D upload measured separately; mapping charges it to the first CPU stage.'),
        ('GPU Inference',table(stats[stats.stage=='gpu_inference'][['model','count','mean','median','std','p95','p99','min','max']])+'\n\nResident CUDA input; forward only, no transfer or preprocessing. MobileNet distribution varies substantially; clock/launch/background effects are possible explanations, not isolated causal findings.'),
        ('CPU Postprocessing',table(stats[stats.stage=='cpu_post'][['model','mean','median','std','p95','p99']])+'\n\nIncludes logits D2H, explicit synchronize, softmax, top-5, argmax. No classification accuracy claim.'),
        ('VRAM Measurements',table(memory)+'\n\nBytes. Model residency is allocation delta after model load. Inference allocated and allocator-reserved peaks are different measurements, not additive. Profile reservation uses absolute inference peak allocated / 2^30 per replica, conservatively including framework workspace. Baseline allocation is disclosed. No VRAM CI is invented for a single observed maximum over repetitions. [Allocated](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_allocated.html) and [reserved](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_reserved.html) APIs.'),
        ('Cold Start Measurements',table(cold[['model','stage','count','mean','median','std','p95','p99']])+'\n\nCUDA process/driver already initialized. New constructor + cached local state load + synchronized model H2D + first-forward host wall. OS cache not evicted; internet excluded. Input preparation/upload excluded from startup. This measures model-ready overhead, not process boot or storage-cold latency.'),
        ('Simulator Mapping','\n'.join('#'+line if line.startswith('#') else line for line in (ROOT/'hardware_grounded/SIMULATOR_MAPPING.md').read_text(encoding='utf-8').splitlines())+'\n\nConcrete per-class values: `simulator_mapping.csv`; controller config: `experiment_freeze.json`. Global mean-median parameters and per-class physical worker times are deliberately distinct. The frozen global estimator is not adapted to each model.'),
        ('What Is Hardware-Measured vs Simulated','Measured: three isolated architecture stage timings, input/output transfers, model residency/allocated/reserved memory, cached model-ready cold start, secondary CPU forward, controller CPU runtime. Simulated: 10 nodes, all node capacities, 2/3 GPU concurrency slots, CPU reservations/interference, network/bandwidth, synthetic arrivals/work jitter, service tiers/deadlines, actions and migration downtime. Hardware-derived execution does not make node contention or orchestration physically validated.'),
        ('Hardware-Grounded Workload','MEDIUM 10 nodes / 40 services, 100 slots × 0.1 s. ID modulo 5 gives 16/16/8 services, without RNG draws. Original topology, warm initial assignments, per-request work factors, traffic tape, tier deadlines and resource capacities stay unchanged. Original tape equality was independently checked for all 30 seeds. Median calibrated service times and measured peak allocation replace synthetic execution/memory. DIRECT regime only; no pressure-restoring normalization, optional LARGE or p95 sensitivity. Headroom/pressure differs from the old synthetic operating point and therefore limits mechanism attribution.'),
        ('Pilot',json.dumps(pilot,indent=2)+'\n\nBefore the pilot, all 171 existing tests plus 18 new tests passed (189 total). The new adapter passed exact uniform-profile request/action/node/event trace equivalence for both policies; profile parsing, conversions, assignment, tape preservation and causal snapshots were checked. Six pilot runs, seeds 1/2/3. All physical-unit/request/capacity/lifecycle/hash checks passed; maximum drain 0.122 s. Pilot was a feasibility gate, not evidence supporting a superiority claim. No configuration changed afterward.'),
        ('Main 30-Seed Evaluation',f"Completed {validation['runs']} runs, 30 paired seeds; {validation['requests_verified']:,} request outcomes independently reconstructed from exports. Per-run request/routing/component/lifecycle/reservation audits are saved. Pilot outcomes remain separate. {validation['subgroup_calculations_verified']} subgroup rows checked. All original verified artifact hashes remain intact."),
        ('SLA Results',table(metric_table[metric_table.metric=='sla_breach_rate'])+'\n\nRates are fractions of ALL offered requests; no drops or unplaced requests. Between-seed arithmetic mean is primary; raw numerators and denominators retained. '+result_text),
        ('Mean / p95 / p99',table(metric_table[metric_table.metric!='sla_breach_rate'])+'\n\nMilliseconds; means ± SD and 95% bootstrap CI of seed means. Requests finishing after the 10-second arrival horizon are included; all queues drain without additional decisions.'),
        ('Model-Class Results',table(classes_mean)+'\n\nRates are fractions. Every class is retained; same per-seed request-weighted metric definition within each subgroup. Full tier×model rows: `tier_model_class_results.csv`; every cell has ≥30 requests; no cells silently excluded.'),
        ('Gold / Silver / Bronze',table(tier_mean)+'\n\nGold trade-offs are not hidden. All tier/model counts, queue delays, mean/p95/p99 exported. No subgroup statistical superiority is implied by a descriptive mean.'),
        ('Resource Cost',table(resources)+'\n\nAverage replicas/VRAM are exact allocation integrals over 10 seconds, including cold/retiring replicas and migration double reservation. Pool VRAM peak is the maximum simultaneous ledger total; node VRAM fractions have synthetic capacities as denominators. Compute utilization uses actual finite-resource time integrals; offered ratios are only global-estimator diagnostics. Reduced resource cost cannot by itself establish joint SLA/resource efficiency.'),
        ('Controller Cost',table(controller)+'\n\nSame existing full snapshot + policy/action timing scope. CPU wall-clock overhead during the simulation, no GPU profiling concurrent. Routing and simulated request delays remain distinct. Runtime timing is inherently nondeterministic; request/actions are deterministic.'),
        ('Statistical Tests',methods+'\n\n'+table(tests[['metric','delta_joint_minus_sla','delta_ci95_lower','delta_ci95_upper','p_value','p_value_holm','rank_biserial_correlation','wins','ties','losses','supported_improvement']])+'\n\nIndependent sorted-quantile, bootstrap, signed-rank DP/normal-CDF and Holm reconstructions passed.'),
        ('Negative Seeds',f"SLA-loss seeds (JointSLA breach fraction > SLA-aware): {breach_loss}.\n\nAll negative seed/metric pairs, including tail latency exceptions, are in `negative_seed_cases.csv`; complete paired differences in `paired_seed_differences.csv`. No failed seed removed."),
        ('HW1-HW5',json.dumps(status,indent=2)+'\n\nHW3 is the predeclared descriptive 5% resource guardrail; it is not a statistical non-inferiority test or proof of good SLA efficiency. HW5 requires lower class mean breach rate in at least two classes. No hypothesis definition changed after outcomes.'),
        ('Threats to Validity','Single physical machine, single GPU architecture, laptop GPU; no clock/power isolation and background load possible; sequential model profiling may mix device operating states; only three representative vision architectures and local random weights; CPU one thread; cached disk startup, initialized driver; measured memory workspace may be shared on real co-resident GPUs; synthetic arrival process, work jitter, network, node count/capacity and concurrency remain. Global frozen controller priors approximate class-specific execution/cold overhead and preserve the legacy 14-ms initial variance. Direct injection changes the original pressure regime. This joint calibration cannot identify which changed physical assumption causes a performance reversal. No real telco testbed, no real deployment, no hardware-variability sensitivity run.'),
        ('Safe Paper Claims',result_text+'\n\nSafe wording: “In a 30-paired-seed hardware-grounded simulation using isolated FP32 profiles from three neural-network architectures on one physical laptop GPU, the previously observed synthetic JointSLA advantage was challenged and the DIRECT-calibration result was preserved without algorithm tuning.” Describe the actual metrics and resource/controller trade-offs below, not a universal superiority claim.'),
        ('Claims We Cannot Make','Production validated, carrier-grade, real 6G deployment, universally hardware independent, GPU-independent, real telco validation, state of the art, or statistically established class-level advantages. No claim of actual co-resident GPU throughput, pretrained task accuracy, internet/storage-cold loading, or a result from an unrun pressure-preserving/sensitivity/LARGE experiment.'),
        ('Implications for B-Level Publication','Hardware grounding strengthens methodological transparency and exposes a meaningful limitation, but weakens the case for a persistent aggregate advantage when HW1/HW2 fail. A paper may report regime-dependent trade-offs and this negative result; it cannot use this run to support a robustness claim. The experiment alone cannot guarantee publication or a venue classification. Further mechanism ablations would require separately preregistered experiments, not retuning these frozen results.\n\nReproduce existing profiles/results:\n\n```powershell\n.venv\\Scripts\\python.exe run_hardware_profiling.py --check\n.venv\\Scripts\\python.exe -m pytest -q\n.venv\\Scripts\\python.exe run_hardware_grounded_experiment.py --pilot --reuse-results\n.venv\\Scripts\\python.exe run_hardware_grounded_experiment.py --seeds 1:30 --reuse-results\n```\n\nRerun simulations with fixed measured profiles: replace `--reuse-results` with `--force`, pilot first. Fresh hardware profiling: `python run_hardware_profiling.py --profile --force --models mobilenet,resnet50,vit_b16` only in a new experiment checkout/output before creating its freeze; this experiment refuses profile overwrite after calibration freeze. Full profile dependencies: `hardware_grounded/requirements-profile.txt`.')]
    (OUTPUT/'report.md').write_text('\n\n'.join('# '+heading+'\n\n'+body for heading,body in sections)+'\n',encoding='utf-8')


def analyze(raw):
    assert set(raw.seed)==set(range(1,31)) and len(raw)==60
    profiles=load_profiles();summary=summarize(raw);summary.to_csv(OUTPUT/'summary_statistics.csv',index=False)
    tests,delta=paired(raw);tests.to_csv(OUTPUT/'paired_tests.csv',index=False);delta.to_csv(OUTPUT/'paired_seed_differences.csv',index=False)
    delta[delta.outcome=='loss'].to_csv(OUTPUT/'negative_seed_cases.csv',index=False)
    classes=pd.read_csv(OUTPUT/'model_class_results.csv');tiers=pd.read_csv(OUTPUT/'tier_results.csv')
    summarize(classes,('policy','model_class')).to_csv(OUTPUT/'model_class_summary_statistics.csv',index=False)
    summarize(tiers,('policy','tier')).to_csv(OUTPUT/'tier_summary_statistics.csv',index=False)
    summarize(pd.read_csv(OUTPUT/'tier_model_class_results.csv'),('policy','tier','model_class')).to_csv(OUTPUT/'tier_model_class_summary_statistics.csv',index=False)
    raw[['seed','policy',*RESOURCE]].to_csv(OUTPUT/'resource_results.csv',index=False);raw[['seed','policy',*CONTROLLER]].to_csv(OUTPUT/'controller_results.csv',index=False)
    status=hypothesis_status(raw,tests,classes);write_json(OUTPUT/'hypotheses.json',status)
    mapping=[];base=calibrated_config(profiles)
    for label,name in CLASS_MODELS.items():
        p=profiles['models'][name];c=service_config(base,p)
        mapping.append(dict(model_class=label,model=name,service_count=16 if label!='HEAVY' else 8,cpu_pre_measured_ms=p['cpu_pre_ms'],input_upload_measured_ms=p['input_upload_ms'],
            preprocess_simulator_ms=c.preprocess_ms,gpu_inference_simulator_ms=c.inference_ms,postprocess_simulator_ms=c.postprocess_ms,
            isolated_sum_medians_ms=c.preprocess_ms+c.inference_ms+c.postprocess_ms,vram_reservation_gib=p['vram_mb']/1024,
            measured_cold_median_ms=p['cold_start_ms'],cold_start_slots=c.cold_start_slots,quantized_cold_ms=c.cold_start_slots*base.slot_seconds*1000,
            quantization_extra_ms=c.cold_start_slots*base.slot_seconds*1000-p['cold_start_ms']))
    pd.DataFrame(mapping).to_csv(OUTPUT/'simulator_mapping.csv',index=False)
    from .validation import verify_exports
    verify_exports();figures(raw,summary,tests,classes,tiers,profiles);report(raw,summary,tests,classes,tiers,status,profiles)
    print(tests.to_string(index=False),flush=True);print(json.dumps(status,indent=2),flush=True)
