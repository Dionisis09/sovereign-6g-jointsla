"""Independent re-read of exported inputs, accounting, telemetry and statistics."""
import gzip,json
import numpy as np
import pandas as pd
from catalyst.reused import digest
from hardware_grounded.environment import write_json
from hardware_grounded.calibration import model_class
from paper_evaluation.validation import linear_quantile,reference_ci,reference_signed_rank
from .protocol import read,now,verify_freeze,SEEDS,verify_protected

def close(a,b):assert np.allclose(a,b,rtol=1e-10,atol=1e-7),(a,b)

def verify_study(out,phase,tests=None):
    raw=pd.read_csv(out/'raw_results.csv');tiers=pd.read_csv(out/'tier_results.csv');classes=pd.read_csv(out/'model_class_results.csv')
    requests=groups=headroom_checks=0
    for (point,seed),pair in raw.groupby(['load_multiplier','seed']):
        label=f'load_{point:.2f}'
        with gzip.open(out/'inputs'/label/f'seed_{seed:03d}.json.gz','rt',encoding='utf-8') as stream:w=json.load(stream)
        assert seed in SEEDS[phase] and digest(w)==pair.workload_hash.iloc[0]
        assert digest({k:w[k] for k in ('seed','services','requests','traffic')})==pair.traffic_hash.iloc[0]
        assert all(pair[k].nunique()==1 for k in ('traffic_hash','workload_hash','total_requests'))
        request=pd.DataFrame(w['requests']).set_index('request_id');services={s['service_id']:s for s in w['services']}
        for r in pair.itertuples():
            folder=out/'runs'/label/f'seed_{seed:03d}'/r.policy
            f=pd.read_csv(folder/'request_outcomes.csv.gz').set_index('request_id').sort_index()
            assert np.array_equal(f.index,request.index) and f.index.is_unique and len(f)==r.total_requests
            close(f.service_id,request.service_id);close(f.arrival_s,request.arrival_s);close(f.arrival_slot,request.arrival_slot)
            assert np.array_equal(f.breach,f.latency_ms>f.deadline_ms)
            close(f.latency_ms,1000*(f.completion_s-f.arrival_s))
            close(f.latency_ms,f[['compute_ms','network_ms','service_queue_ms','node_queue_ms','lifecycle_penalty_ms']].sum(axis=1))
            close(r.sla_breach_rate,f.breach.mean());close(r.mean_request_latency_ms,f.latency_ms.mean())
            for metric,p in [('median_latency_ms',.5),('p95_latency_ms',.95),('p99_latency_ms',.99)]:close(getattr(r,metric),linear_quantile(f.latency_ms,p))
            f['model_class']=f.service_id.map(model_class)
            for column,source in [('tier',tiers),('model_class',classes)]:
                for key,g in f.groupby(column):
                    row=source[(source.load_multiplier==point)&(source.seed==seed)&(source.policy==r.policy)&(source[column]==key)].iloc[0]
                    assert row.total_requests==len(g) and row.sla_breaches==g.breach.sum()
                    close(row.sla_breach_rate,g.breach.mean());close(row.mean_request_latency_ms,g.latency_ms.mean())
                    close(row.p95_latency_ms,linear_quantile(g.latency_ms,.95));close(row.p99_latency_ms,linear_quantile(g.latency_ms,.99));groups+=1
            nodes=pd.read_csv(folder/'node_trajectories.csv.gz');slots=pd.read_csv(folder/'slot_trajectories.csv.gz')
            events=pd.read_csv(folder/'reservation_events.csv.gz');actions=pd.read_csv(folder/'actions.csv.gz');lc=pd.read_csv(folder/'lifecycle_events.csv.gz')
            snapshot=pd.read_csv(folder/'control_snapshot_times.csv.gz')
            assert slots.accepted_actions.le(2).all()
            for resource in ('cpu','gpu'):close(getattr(r,f'average_{resource}_utilization'),nodes[f'{resource}_utilization'].mean())
            close(r.mean_queue_delay_ms,(f.service_queue_ms+f.node_queue_ms).mean())
            close(r.p95_queue_delay_ms,linear_quantile(f.service_queue_ms+f.node_queue_ms,.95))
            total=slots.set_index('slot').decision_runtime_ms+snapshot.set_index('slot').runtime_ms
            close(r.controller_total_instrumented_mean_ms,total.mean());close(r.controller_total_instrumented_p95_ms,linear_quantile(total,.95))
            close(r.controller_decision_median_ms,linear_quantile(slots.decision_runtime_ms,.5))
            pool=replicas=last=area=replica_area=peak=0.;horizon=10.
            for ev in events.itertuples():
                t=min(ev.time_s,horizon);area+=pool*(t-last);replica_area+=replicas*(t-last);last=t
                if ev.time_s>horizon:break
                pool+=ev.sign*services[ev.service_id]['gpu_vram_gb'];replicas+=ev.sign;peak=max(peak,pool)
            area+=pool*(horizon-last);replica_area+=replicas*(horizon-last)
            for action in actions[actions.kind=='migrate'].itertuples():
                pause=lc[(lc.kind=='migration_downtime')&(lc.replica_id==action.replica_id)&(lc.start_s>=action.time_s-1e-8)].start_s.min()
                assert np.isfinite(pause);replica_area-=min(pause,horizon)-min(action.time_s,horizon)
            close(r.average_vram_residency_gib,area/horizon);close(r.peak_pool_vram_gib,peak);close(r.average_replicas,replica_area/horizon)
            assert r.total_actions==len(actions) and r.cold_starts==lc.kind.eq('cold_start').sum()
            if r.policy=='joint_sla_v2':
                hr=pd.read_csv(folder/'headroom.csv.gz')
                assert len(hr)==4000 and not hr.duplicated(['slot','service_id']).any()
                counts=request.groupby(['arrival_slot','service_id']).size()
                for row in hr.itertuples():
                    n=min(row.slot,5)
                    count=sum(counts.get((t,row.service_id),0) for t in range(max(0,row.slot-5),row.slot))
                    close(row.recent_rate_rps,count/(n*.1) if n else 0)
                    assert row.observed_history_slots==n
                    L=row.estimated_cycle_ms/1000;R=row.cold_readiness_ms/1000;D=row.deadline_ms/1000
                    floor=2 if row.tier=='Gold' else 1
                    if not np.isfinite(L) or L<=0:required=3
                    elif D<=L:required=floor if row.current_queue==0 and row.recent_rate_rps==0 else 3
                    else:
                        factor={'Gold':1.5,'Silver':np.sqrt(1.5),'Bronze':1}[row.tier]
                        required=min(3,max(floor,int(np.ceil(factor*max(row.current_queue*L/(D-L),(row.current_queue+row.recent_rate_rps*R)*L/(R+D-L))))))
                    assert row.required_warm_replicas==required and row.deficit==max(0,required-row.actual_ready_replicas)
                    if row.accepted_scalein:assert row.actual_ready_replicas-1>=required
                    headroom_checks+=1
                close(r.headroom_deficit_frequency,hr.deficit.gt(0).mean())
                close(r.service_seconds_below_required,.1*hr.deficit.gt(0).sum())
            requests+=len(f)
    statistical=0
    if tests is not None:
        for t in tests.itertuples():
            p=raw[raw.load_multiplier==t.load_multiplier].pivot(index='seed',columns='policy',values=t.metric).sort_index()
            d=p.joint_sla_v2.to_numpy()-p[t.comparator].to_numpy()
            close(t.delta_v2_minus_comparator,d.mean());close([t.delta_ci95_lower,t.delta_ci95_upper],reference_ci(d,t.bootstrap_key))
            W,pvalue,rbc=reference_signed_rank(-d)
            close(t.test_statistic,W);close(t.p_value,pvalue);close(t.rank_biserial_correlation,rbc)
            statistical+=1
        for _,g in tests.groupby(['comparator','family']):
            ordered=g.sort_values('p_value',kind='stable');running=0.
            for i,t in enumerate(ordered.itertuples()):
                running=max(running,min(1.,t.p_value*(len(g)-i)));close(t.p_value_holm,running)
    ledger=[json.loads(s) for s in (out/'generation_ledger.jsonl').read_text().splitlines()]
    assert all(x['seed'] in SEEDS[phase] for x in ledger)
    if phase=='heldout':
        manifest=verify_freeze()
        assert all(x['timestamp']>=manifest['timestamp'] and x['freeze_config_sha256']==manifest['config_sha256'] for x in ledger)
    receipt=dict(timestamp=now(),runs=len(raw),requests_verified=requests,subgroup_rows_verified=groups,
        headroom_service_slots_verified=headroom_checks,paired_tests_independently_verified=statistical,
        input_hashes=True,request_components=True,memory_integrals=True,controller_quantiles=True,
        observed_history_only=True,seed_gate_and_generation_timestamps_verified=True,preserved=verify_protected())
    write_json(out/'independent_validation.json',receipt);return receipt
