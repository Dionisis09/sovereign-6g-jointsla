"""Block-level comparative statistics and independently reconstructed outcomes."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prototype.benchmark.experiment import MAIN,ROOT,source_hashes

LABELS={'static':'Static-2 / RR','reactive':'Reactive / SQ','hpa':'Native HPA / SQ',
        'joint':'JointSLA','joint_sq':'Joint scaler / SQ','reactive_joint':'Reactive / Joint router'}
OUT=ROOT/'prototype/kubernetes/evidence/comparison_v2'


def integrate(samples,key,start,end):
    rows=sorted((r for r in samples if key in r),key=lambda r:r['unix_s'])
    preceding=[r for r in rows if r['unix_s']<=start]
    if not preceding: raise ValueError('No initial observation for '+key)
    value=preceding[-1][key];cursor=start;total=0.
    for row in rows:
        stamp=row['unix_s']
        if stamp<=start: continue
        if stamp>end: break
        total+=(stamp-cursor)*value;cursor=stamp;value=row[key]
    return total+(end-cursor)*value


def reconstruct(folder,block,policy,seed):
    rows=pd.read_csv(folder/'burst/request_outcomes.csv')
    original=json.loads((folder/'burst/summary.json').read_text())
    assert len(rows)==1280 and rows.request.nunique()==1280
    done=rows.status==200;failures=(~done)|(rows.latency_ms>rows.deadline_ms)
    assert failures.equals(rows.sla_failure)
    assert int(done.sum())==original['completed'] and int(failures.sum())==original['sla_failures']
    assert rows.loc[done,['queue_ms','execution_ms','pod_uid','request_id_echo']].notna().all().all()
    assert rows.loc[done,'request_id'].equals(rows.loc[done,'request_id_echo'])
    timeline=[json.loads(line) for line in (folder/'timeline.jsonl').read_text().splitlines()]
    start=original['started_unix_s'];end=original['finished_unix_s']+20
    record=dict(block=block,seed=seed,policy=policy,offered=1280,completed=int(done.sum()),
        sla_failure_percent=100*failures.mean(),completion_percent=100*done.mean(),
        rejection_percent=100*(rows.status==503).mean(),late_completion_percent=100*(done&failures).mean(),
        transport_error_percent=100*(rows.status==0).mean(),
        unknown_error_percent=100*rows.category.isin(['unknown_rejection','other_http_error']).mean(),
        mean_completed_latency_ms=rows.loc[done,'latency_ms'].mean(),
        p95_completed_latency_ms=np.percentile(rows.loc[done,'latency_ms'],95),
        p99_completed_latency_ms=np.percentile(rows.loc[done,'latency_ms'],99),
        mean_backend_queue_ms=rows.loc[done,'queue_ms'].mean(),
        mean_execution_ms=rows.loc[done,'execution_ms'].mean(),
        mean_client_queue_ms=rows.client_queue_ms.mean(),
        target_replica_seconds=integrate(timeline,'target',start,end),
        ready_replica_seconds=integrate(timeline,'ready',start,end),
        sampler_error_count=sum('sampling_error' in r for r in timeline),
        timeline_samples=len(timeline),trial_observed_wall_seconds=timeline[-1]['unix_s']-timeline[0]['unix_s'],
        preparation_seconds=json.loads((folder/'initial_state.json').read_text())['preparation_seconds'],
        peak_target=max(r.get('target',0) for r in timeline),
        workload_sha256=original['workload_sha256'])
    record['readiness_deficit_replica_seconds']=integrate([dict(r,deficit=max(r['target']-r['ready'],0)) for r in timeline if 'target' in r and 'ready' in r],'deficit',start,end)
    during=[r for r in timeline if start<=r['unix_s']<=end]
    record['target_changes_observed']=sum(a.get('target')!=b.get('target') for a,b in zip(during,during[1:]) if 'target' in a and 'target' in b)
    initial_uids={p['pod_uid'] for p in json.loads((folder/'initial_state.json').read_text())['replica_states']}
    ready_delays={}
    controls={}
    for row in during:
        if 'control_step_ms' in row and row.get('gateway_state'):
            controls[row['gateway_state'].get('snapshot_unix_s')]=row['control_step_ms']
        for pod in row.get('pods',[]):
            if pod['uid'] in initial_uids or pod['uid'] in ready_delays or not pod['ready']: continue
            transitions=[c['last_transition'] for c in pod['conditions'] if c['type']=='Ready' and c['status']=='True']
            if transitions and transitions[0]:
                ready_delays[pod['uid']]=(datetime.fromisoformat(transitions[0])-datetime.fromisoformat(pod['created'])).total_seconds()
    record.update(new_pods_observed_ready=len(ready_delays),
        mean_new_pod_creation_to_ready_ms=np.mean(list(ready_delays.values()))*1000 if ready_delays else np.nan,
        mean_sampled_control_step_ms=np.mean(list(controls.values())) if controls else np.nan)
    traces={}
    max_memory=0;steps=[]
    for row in timeline:
        if not start-.8<=row['unix_s']<=end: continue
        state=row.get('gateway_state') or {}
        memory=0
        for backend in state.get('replica_states',[]):
            if not backend.get('pod_uid'): continue
            cg=backend.get('cgroup',{})
            traces.setdefault(backend['pod_uid'],[]).append(cg)
            memory+=cg.get('memory_bytes',0)
        max_memory=max(max_memory,memory)
    for line in (folder/'gateway.log').read_text().splitlines():
        if line.startswith('{'):
            entry=json.loads(line)
            if entry.get('event')=='reconciliation' and start<=entry.get('unix_s',0)<=end:
                steps.append(entry)
    usage=periods=throttled=0
    for values in traces.values():
        for key in ('usage_usec','nr_periods','nr_throttled'):
            available=[v[key] for v in values if key in v]
            if len(available)<2: continue
            delta=max(available)-min(available)
            if key=='usage_usec': usage+=delta
            elif key=='nr_periods': periods+=delta
            else: throttled+=delta
    record.update(observed_cpu_core_seconds=usage/1e6,
                  observed_throttled_period_percent=100*throttled/periods if periods else np.nan,
                  peak_observed_inference_memory_bytes=max_memory,
                  applied_joint_or_reactive_actions=len([e for e in steps if e.get('outcome')=='applied']))
    for tier in ('Gold','Silver','Bronze'):
        part=rows[rows.tier==tier]
        record[tier.lower()+'_sla_failure_percent']=100*part.sla_failure.mean()
    categories=[dict(block=block,seed=seed,policy=policy,tier=tier,category=kind,count=int(count))
                for (tier,kind),count in rows.groupby(['tier','category']).size().items()]
    return record,categories


def bootstrap_interval(values,rng):
    values=np.asarray(values,float)
    draws=rng.integers(0,len(values),size=(10000,len(values)))
    means=values[draws].mean(axis=1)
    return tuple(np.percentile(means,[2.5,97.5]))


def holm(values):
    values=np.asarray(values,float);order=np.argsort(values);out=np.empty_like(values)
    previous=0.
    for rank,index in enumerate(order):
        previous=max(previous,min(1.,(len(values)-rank)*values[index]));out[index]=previous
    return out


def report(data,comparisons,categories):
    """Write a compact report from reconstructed run values, without cherry-picking."""
    lines=['# JointSLA: matched real Kubernetes comparison v2', '',
        'Completed: 30 paired blocks, six registered treatments, 180 trials, 230,400 verified offered request outcomes. Pilot data and historical 38.83%/47.27% bursts are excluded.', '',
        '## Findings', '',
        '| Policy | SLA failures, mean ± std (%) | Completed p95, mean ± std (ms) | HTTP 503 (%) | Target replica-seconds |',
        '|---|---:|---:|---:|---:|']
    for policy in LABELS:
        part=data[data.policy==policy]
        fmt=lambda c:f'{part[c].mean():.2f} ± {part[c].std():.2f}'
        lines.append(f'| {LABELS[policy]} | {fmt("sla_failure_percent")} | {fmt("p95_completed_latency_ms")} | {fmt("rejection_percent")} | {fmt("target_replica_seconds")} |')
    lines+=['',f'Observed trial wall time averaged {data.trial_observed_wall_seconds.mean():.2f} s; preparation averaged {data.preparation_seconds.mean():.2f} s. These timings describe v2, not a paired end-to-end speed comparison with the aborted v1.', '', 'Latency is conditional on completion. Every rejection remains in the all-offered SLA denominator. Resource-seconds cover burst start to last response plus a fixed 20-second follow-up.', '',
        '| Paired contrast | SLA difference (percentage points) | 95% paired block-bootstrap interval | Holm p (three core contrasts) |',
        '|---|---:|---:|---:|']
    for c in comparisons:
        adjusted=c.get('holm_three_core_comparisons_p')
        pv=f'{adjusted:.5g}' if adjusted is not None else 'exploratory'
        lines.append(f'| {c["comparison"]} | {c["sla_failure_difference_pp"]:.2f} | [{c["ci95_low_pp"]:.2f}, {c["ci95_high_pp"]:.2f}] | {pv} |')
    primary=comparisons[0]
    if primary['ci95_high_pp']<0:
        finding='The registered primary contrast supports lower all-offered SLA failures for JointSLA than reactive under this burst regime.'
    elif primary['ci95_low_pp']>0:
        finding='The registered primary contrast supports higher all-offered SLA failures for JointSLA than reactive under this burst regime.'
    else:
        finding='The registered primary interval crosses zero; these data do not establish a primary SLA advantage.'
    goal=data[data.policy=='joint'].sla_failure_percent.mean()<15
    lines+=['',finding,'',f'The <15% mean all-offered SLA target is {"met" if goal else "not met"} in this registered regime.', '',
        '## Failure attribution', '',
        '| Policy | Tier | Failure category | Requests |', '|---|---|---|---:|']
    grouped=categories.groupby(['policy','tier','category'])['count'].sum()
    for (policy,tier,category),count in grouped.items():
        if category!='completed_on_time': lines.append(f'| {LABELS[policy]} | {tier} | {category} | {count:,} |')
    lines+=['', 'Error reasons identify explicit rejection branches. Queue time and execution time are observed for completed requests; rejected requests have no fabricated compute duration. Pod readiness and cgroup throttling are measured concurrent exposures, not mutually exclusive causal labels.', '',
        '## Contribution and limits', '',
        'The experiment tests the unchanged integrated JointSLA controller on real pretrained CPU inference against fixed, CPU-reactive and native Kubernetes HPA baselines, with paired workload tapes, balanced order and explicit drops. Two registered exploratory rule substitutions test scaling/routing contributions. Feedback means those substitutions do not preserve identical realized replica trajectories.', '',
        'This adds empirical evidence and reproducible infrastructure. It does not establish that SLA-aware routing, warm replicas or autoscaling are new ideas. Literature novelty needs a verifiable prior-work comparison of the exact joint mechanism; unsupported citations remain excluded.', '',
        'The local operational prototype is complete within its audited scope. Scientific generalization remains limited: one physical host, one virtual node, one CPU model, synthetic tensors, short ~10.7-second burst, background host activity, sampled/cached telemetry, and 30 blocks on the same deployment. Native HPA retains asynchronous metrics and default stabilization; the sustained pilot verifies actuation but is not a repeated sustained-workload comparison.', '',
        'Historical 38.83% and 47.27% are all-offered failure rates from separate 1,280-request bursts at different infrastructure revisions/start states. Neither is a baseline-relative improvement. The new benchmark also adds common instrumentation and identical preconditioning, so its levels must not be pooled with those historical runs.', '',
        '## Reproduction and evidence', '',
        'See the frozen [protocol](../../RESEARCH_EVALUATION_PROTOCOL.md) and [manifest](manifest.json). Raw immutable CSV outcomes, workload tapes, pod/HPA timelines and logs reside in `prototype/.cache/kubernetes_comparison_v2/`; all 230,400 outcomes were independently reconstructed. Curated [runs](runs.csv), [summary](summary.csv), [paired contrasts](paired_comparisons.csv), [failure categories](failure_categories.csv), and [verification/hashes](analysis.json) are exported alongside this report.', '',
        '```powershell', '.venv/Scripts/python.exe -m prototype.benchmark.experiment --run', '.venv/Scripts/python.exe -m prototype.benchmark.analyze', '```', '',
        '![All-offered SLA](sla_comparison.png)', '', '![SLA versus resources](sla_resource_tradeoff.png)', '', '![Latency and rejection](latency_and_rejections.png)', '']
    (OUT/'COMPARATIVE_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')


def analyze():
    frozen=json.loads((MAIN/'manifest.json').read_text(encoding='utf-8'))
    assert source_hashes()==frozen['source_hashes'],'Source changed after freeze'
    assert json.loads((MAIN/'completion.json').read_text())['finished']==180
    records=[];categories=[];hashes={}
    for block in frozen['schedule']:
        for policy in block['order']:
            folder=MAIN/f'block_{block["block"]:02d}'/policy
            verification=json.loads((folder/'verification.json').read_text())
            assert verification['status']=='passed'
            record,parts=reconstruct(folder,block['block'],policy,block['seed'])
            assert record['workload_sha256']==frozen['workload_sha256'][str(block['seed'])]
            records.append(record);categories.extend(parts)
            for path in (folder/'burst/request_outcomes.csv',folder/'timeline.jsonl',folder/'verification.json'):
                hashes[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
    data=pd.DataFrame(records);OUT.mkdir(parents=True,exist_ok=True)
    assert data.groupby('policy').size().eq(30).all()
    data.to_csv(OUT/'runs.csv',index=False);pd.DataFrame(categories).to_csv(OUT/'failure_categories.csv',index=False)
    metrics=[c for c in data.columns if c not in ('block','seed','policy','workload_sha256')]
    summary=data.groupby('policy')[metrics].agg(['mean','std'])
    summary.columns=['_'.join(c) for c in summary.columns];summary.to_csv(OUT/'summary.csv')
    rng=np.random.default_rng(39108);comparisons=[]
    pivot=data.pivot(index='block',columns='policy',values='sla_failure_percent')
    for baseline in ('reactive','static','hpa','joint_sq','reactive_joint'):
        differences=pivot['joint']-pivot[baseline]
        lo,hi=bootstrap_interval(differences,rng)
        p=1. if np.all(differences==0) else float(wilcoxon(differences,zero_method='pratt',alternative='two-sided',method='auto').pvalue)
        comparisons.append(dict(comparison='joint minus '+baseline,blocks=30,
            sla_failure_difference_pp=differences.mean(),ci95_low_pp=lo,ci95_high_pp=hi,
            paired_wilcoxon_p=p,role='primary' if baseline=='reactive' else 'secondary_core' if baseline in ('static','hpa') else 'registered_exploratory_mechanism'))
    adjusted=holm([c['paired_wilcoxon_p'] for c in comparisons[:3]])
    for row,value in zip(comparisons[:3],adjusted): row['holm_three_core_comparisons_p']=value
    pd.DataFrame(comparisons).to_csv(OUT/'paired_comparisons.csv',index=False)
    order=frozen['policies'];colors=['#7b8792','#dc9750','#6384bc','#22866a','#65a897','#996f9d']
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
    means=[];errors=[]
    for policy in order:
        values=data[data.policy==policy].sla_failure_percent
        lo,hi=bootstrap_interval(values,rng);mean=values.mean()
        means.append(mean);errors.append((mean-lo,hi-mean))
    ax.bar(range(len(order)),means,color=colors,yerr=np.array(errors).T,capsize=4)
    ax.set_xticks(range(len(order)),[LABELS[p].replace(' / ','\n') for p in order],fontsize=9)
    ax.set(ylabel='All-offered SLA failures (%)',ylim=(0,100),title='30 paired real Kubernetes blocks · pointwise 95% block-bootstrap intervals')
    ax.axhline(15,color='#b33c49',ls='--',label='15% target');ax.legend(frameon=False)
    fig.savefig(OUT/'sla_comparison.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
    for i,policy in enumerate(order):
        part=data[data.policy==policy]
        ax.scatter(part.target_replica_seconds,part.sla_failure_percent,s=20,alpha=.45,color=colors[i])
        ax.scatter(part.target_replica_seconds.mean(),part.sla_failure_percent.mean(),marker='D',s=65,color=colors[i],label=LABELS[policy])
    ax.set(xlabel='Deployment target replica-seconds (burst + fixed 20 s follow-up)',ylabel='All-offered SLA failures (%)',ylim=(0,100),title='Individual paired-arm trials; diamonds = policy means')
    ax.legend(frameon=False,fontsize=8,ncol=2)
    fig.savefig(OUT/'sla_resource_tradeoff.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for i,policy in enumerate(order):
        part=data[data.policy==policy]
        axes[0].scatter([i]*30,part.p95_completed_latency_ms,s=16,alpha=.5,color=colors[i])
        axes[1].bar(i,part.rejection_percent.mean(),color=colors[i])
    for ax in axes: ax.set_xticks(range(len(order)),[LABELS[p].replace(' / ','\n') for p in order],fontsize=8)
    axes[0].set(ylabel='Exact per-trial completed-request p95 (ms)',ylim=(0,None),title='30 run values · completed requests only')
    axes[1].set(ylabel='Rejected HTTP 503 / all offered (%)',ylim=(0,100),title='Drops retained in SLA denominator')
    fig.savefig(OUT/'latency_and_rejections.png',dpi=170);plt.close(fig)
    result=dict(status='complete',analyzed_utc=datetime.now(timezone.utc).isoformat(),blocks=30,trials=180,
                offered_outcomes_verified=int(data.offered.sum()),paired_workloads_verified=True,
                registered_source_hashes_unchanged=True,comparisons=comparisons,
                source_manifest_sha256=hashlib.sha256((MAIN/'manifest.json').read_bytes()).hexdigest(),
                evidence_hashes=hashes,
                limitations=['One physical host and one virtual validation node','Synthetic tensors, one CPU model',
                    'Short ~10.7 s primary burst; native HPA has asynchronous resource metrics and default stabilization',
                    'Counter deltas cover observed ready backends; initial startup/retirement CPU can be missed',
                    'Target/ready replica-seconds use sampled step integration',
                    'Mechanism interventions hold a rule fixed, not identical realized replica trajectories',
                    'Results do not by themselves prove literature novelty'])
    report(data,comparisons,pd.DataFrame(categories))
    (OUT/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (OUT/'manifest.json').write_bytes((MAIN/'manifest.json').read_bytes())
    print(json.dumps({k:v for k,v in result.items() if k!='evidence_hashes'},indent=2))
    return result


if __name__=='__main__': analyze()
