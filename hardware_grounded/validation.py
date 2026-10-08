"""Read exported artifacts to verify calculations independently of the runner."""
from dataclasses import asdict
import gzip,json,hashlib
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from paper_evaluation.validation import linear_quantile,reference_ci,reference_signed_rank
from catalyst.reused import digest
from .environment import OUTPUT,ROOT,write_json
from .integrity import sha,verify


def pilot_gate():
    check=json.loads((OUTPUT/'pilot/pilot_validation.json').read_text())
    protocol=json.loads((OUTPUT/'experiment_freeze.json').read_text())
    assert check['successful'] and check['runs']==6 and check['unit_and_component_checks'] and check['common_hashes']
    assert check['profile_sha256']==sha(OUTPUT/'hardware_profiles.json')==protocol['profile_sha256']
    xml=ET.parse(OUTPUT/'tests.xml').getroot()
    suites=list(xml.iter('testsuite'));assert sum(int(s.attrib['tests']) for s in suites)==189
    assert sum(int(s.attrib['failures'])+int(s.attrib['errors']) for s in suites)==0
    regime=pd.read_csv(OUTPUT/'pilot/workload_regime.csv')
    assert np.isfinite(regime.select_dtypes(include='number').to_numpy()).all()
    assert regime.hardware_gpu_pressure.between(0,1).all() and regime.hardware_cpu_pressure.between(0,1).all()
    write_json(OUTPUT/'regime_validation.json',dict(ready_for_full_run=True,pilot_requests=check['requests_verified'],tests_passed=189,
        catastrophic_overload=False,maximum_drain_seconds=check['max_drain_seconds'],maximum_waiting_requests=check['maximum_waiting_requests'],
        mean_expected_gpu_pressure=float(regime.hardware_gpu_pressure.mean()),mean_expected_cpu_pressure=float(regime.hardware_cpu_pressure.mean()),
        initial_vram_fraction=float(regime.initial_vram_pressure.mean()),profile_sha256=protocol['profile_sha256'],
        decision='Dimensionally valid DIRECT timing/memory mapping; complete request drain, no unit/overflow errors; no profile/traffic/SLA/controller changes after pilot.',
        prior_artifacts=verify()))


def close(actual,expected):
    assert np.allclose(actual,expected,atol=1e-7,rtol=1e-10),(actual,expected)


def verify_profiles():
    catalog=json.loads((OUTPUT/'hardware_profiles.json').read_text());assert catalog['hardware_sha256']==sha(OUTPUT/'hardware_info.json')
    summary=pd.read_csv(OUTPUT/'profiling/model_profile_summary.csv');cold=pd.read_csv(OUTPUT/'profiling/cold_start_summary.csv');cpu=pd.read_csv(OUTPUT/'profiling/cpu_profile_summary.csv')
    memory=pd.read_csv(OUTPUT/'profiling/vram_summary.csv').set_index('model');count=0
    for name,profile in catalog['models'].items():
        path=OUTPUT/'profiling'/f'{name}_raw.csv';assert sha(path)==profile['raw_sha256']
        assert sha(OUTPUT/'profiling/states'/f'{name}.pt')==profile['checkpoint_sha256']
        raw=pd.read_csv(path);assert np.isfinite(raw.latency_ms).all() and (raw.latency_ms>0).all()
        assert raw.measurement_order.is_unique and raw.measurement_order.tolist()==list(range(1,len(raw)+1))
        for (phase,stage),group in raw.groupby(['phase','stage']):
            frame=summary if phase=='steady' else cold if phase=='cold' else cpu
            row=frame[(frame.model==name)&(frame.stage==stage)].iloc[0];x=group.latency_ms.to_numpy()
            assert len(x)==row['count']==(300 if phase=='steady' else 20 if phase=='cold' else 30)
            close(row['mean'],sum(x)/len(x));close(row['median'],linear_quantile(x,.5));close(row['std'],np.sqrt(sum((x-x.mean())**2)/(len(x)-1)))
            for percentile in (50,90,95,99):close(row[f'p{percentile}'],linear_quantile(x,percentile/100))
            close(row['min'],min(x));close(row['max'],max(x))
        close(profile['vram_mb']*2**20,memory.loc[name,'inference_peak_allocated_bytes'])
        close(profile['model_residency_mb']*2**20,memory.loc[name,'model_residency_bytes'])
        assert memory.loc[name,'inference_peak_reserved_bytes']>=memory.loc[name,'inference_peak_allocated_bytes']>0
        count+=len(raw)
    assert count==5010
    return dict(raw_rows_verified=count,models_verified=3,raw_hashes_and_checkpoint_hashes=True,summary_units_and_quantiles=True)


def verify_exports():
    raw=pd.read_csv(OUTPUT/'raw_results.csv');assert len(raw)==60 and not raw.duplicated(['seed','policy']).any()
    assert set(zip(raw.seed,raw.policy))=={(s,p) for s in range(1,31) for p in ('sla_aware','joint_sla')}
    total=0;class_checks=0;subgroup_checks=0
    class_frame=pd.read_csv(OUTPUT/'model_class_results.csv');tier_frame=pd.read_csv(OUTPUT/'tier_results.csv')
    cross_frame=pd.read_csv(OUTPUT/'tier_model_class_results.csv')
    for seed in range(1,31):
        with gzip.open(OUTPUT/'inputs'/f'seed_{seed:03d}.json.gz','rt',encoding='utf-8') as stream:w=json.load(stream)
        with (OUTPUT/'inputs'/f'seed_{seed:03d}_service_configs.json').open() as stream:cs=json.load(stream)
        request=pd.DataFrame(w['requests']).set_index('request_id');services={s['service_id']:s for s in w['services']}
        # Regenerate only exogenous original inputs: an independent tape identity check.
        from dynamic_placement.workload import generate_workload
        from scalability.configuration import configuration
        original=generate_workload(configuration('MEDIUM'),seed)
        assert [asdict(r) for r in original.requests]==w['requests']
        assert list(original.traffic)==w['traffic'] and {str(k):v for k,v in original.initial.items()}==w['initial']
        for service in w['services']:
            prior=asdict(original.services[service['service_id']]);current=dict(service)
            del prior['gpu_vram_gb'];del current['gpu_vram_gb'];assert prior==current
        paired=raw[raw.seed==seed]
        assert all(paired[k].nunique()==1 for k in ('traffic_hash','workload_hash','original_arrival_hash','total_requests'))
        assert digest(w)==paired.workload_hash.iloc[0]
        assert digest({k:w[k] for k in ('seed','services','requests','traffic')})==paired.traffic_hash.iloc[0]
        assert digest({k:w[k] for k in ('seed','requests','traffic')})==paired.original_arrival_hash.iloc[0]
        for policy in ('sla_aware','joint_sla'):
            folder=OUTPUT/'runs'/f'seed_{seed:03d}'/policy
            f=pd.read_csv(folder/'request_outcomes.csv.gz').set_index('request_id').sort_index();m=paired[paired.policy==policy].iloc[0]
            assert f.index.is_unique and np.array_equal(f.index.to_numpy(),request.index.to_numpy())
            assert f.latency_ms.notna().all() and not f.unplaced.any() and m.dropped_requests==0
            close(f.arrival_s,request.arrival_s);close(f.service_id,request.service_id);close(f.arrival_slot,request.arrival_slot)
            times={int(sid):sum(c[k] for k in ('preprocess_ms','inference_ms','postprocess_ms')) for sid,c in cs.items()}
            close(f.compute_ms,f.service_id.map(times)*request.work_factor)
            close(f.latency_ms,1000*(f.completion_s-f.arrival_s))
            close(f.latency_ms,f[['service_queue_ms','node_queue_ms','compute_ms','network_ms','lifecycle_penalty_ms']].sum(axis=1))
            assert f.breach.eq(f.latency_ms>f.deadline_ms).all()
            assert m.total_requests==len(f) and m.completed_requests==len(f) and m.sla_breaches==f.breach.sum()
            close(m.sla_breach_rate,f.breach.mean());close(m.mean_request_latency_ms,f.latency_ms.mean())
            close(m.p95_latency_ms,linear_quantile(f.latency_ms,.95));close(m.p99_latency_ms,linear_quantile(f.latency_ms,.99))
            slots=pd.read_csv(folder/'slot_trajectories.csv.gz');nodes=pd.read_csv(folder/'node_trajectories.csv.gz')
            actions=pd.read_csv(folder/'actions.csv.gz');events=pd.read_csv(folder/'reservation_events.csv.gz');lifecycle=pd.read_csv(folder/'lifecycle_events.csv.gz')
            snapshots=pd.read_csv(folder/'control_snapshot_times.csv.gz');horizon=10.
            assert len(slots)==100 and len(nodes)==1000 and len(snapshots)==100
            assert m.total_actions==len(actions)
            for field,kind in [('scale_outs','scale_up'),('scale_ins','scale_down'),('migrations','migrate')]:assert m[field]==actions.kind.eq(kind).sum()
            assert m.cold_starts==lifecycle.kind.eq('cold_start').sum()
            close(m.peak_replicas,max(slots.replicas.max(),40));close(m.triggered_downtime_seconds,(lifecycle.ready_s-lifecycle.start_s).sum())
            control=slots.set_index('slot').decision_runtime_ms+snapshots.set_index('slot').runtime_ms
            close(m.controller_total_instrumented_mean_ms,control.mean());close(m.controller_total_instrumented_p95_ms,linear_quantile(control,.95))
            for resource in ('cpu','gpu'):
                values=nodes[f'{resource}_utilization'];assert values.between(-1e-8,1+1e-8).all()
                close(m[f'average_{resource}_utilization'],values.mean())
            pool=0.;replicas=0.;last=0.;area=0.;replica_area=0.;peak=0.
            for event in events.itertuples():
                t=min(event.time_s,horizon);area+=pool*(t-last);replica_area+=replicas*(t-last);last=t
                if event.time_s>horizon:break
                pool+=event.sign*services[event.service_id]['gpu_vram_gb'];replicas+=event.sign;peak=max(peak,pool)
            area+=pool*(horizon-last);replica_area+=replicas*(horizon-last)
            for migration in actions[actions.kind=='migrate'].itertuples():
                pause=lifecycle[(lifecycle.kind=='migration_downtime')&(lifecycle.replica_id==migration.replica_id)&(lifecycle.start_s>=migration.time_s-1e-8)].start_s.min()
                assert np.isfinite(pause);replica_area-=min(pause,horizon)-min(migration.time_s,horizon)
            close(m.average_vram_residency_gib,area/horizon);close(m.peak_pool_vram_gib,peak);close(m.average_replicas,replica_area/horizon)
            f['model_class']=f.service_id.map(lambda sid:('LIGHT','LIGHT','MEDIUM','MEDIUM','HEAVY')[sid%5])
            for columns,table in ((['model_class'],class_frame),(['tier'],tier_frame),(['tier','model_class'],cross_frame)):
                selected=table[(table.seed==seed)&(table.policy==policy)]
                assert selected.total_requests.sum()==len(f) and selected.sla_breaches.sum()==f.breach.sum()
                for _,g in selected.iterrows():
                    sub=f
                    for col in columns:sub=sub[sub[col]==g[col]]
                    assert len(sub)==g.total_requests>=30
                    close(g.sla_breach_rate,sub.breach.mean());close(g.mean_request_latency_ms,sub.latency_ms.mean())
                    close(g.p95_latency_ms,linear_quantile(sub.latency_ms,.95));close(g.p99_latency_ms,linear_quantile(sub.latency_ms,.99))
                    close(g.mean_queue_delay_ms,(sub.service_queue_ms+sub.node_queue_ms).mean());subgroup_checks+=1
            total+=len(f)
    tests=pd.read_csv(OUTPUT/'paired_tests.csv');assert len(tests)==4
    for _,row in tests.iterrows():
        pivot=raw.pivot(index='seed',columns='policy',values=row.metric).sort_index();benefit=pivot.sla_aware-pivot.joint_sla
        delta=-benefit;lo,hi=reference_ci(delta,f'hardware:paired:{row.metric}');close(row.delta_joint_minus_sla,delta.mean())
        close([row.delta_ci95_lower,row.delta_ci95_upper],[lo,hi])
        statistic,p,rbc=reference_signed_rank(benefit);close([row.test_statistic,row.p_value,row.rank_biserial_correlation],[statistic,p,rbc])
        assert np.isclose(row.p_value,p,atol=1e-14,rtol=1e-10)
        signs=np.round(benefit,12);assert row.wins==(signs>0).sum() and row.ties==(signs==0).sum() and row.losses==(signs<0).sum()
    p=tests.p_value.to_numpy();order=np.argsort(p,kind='stable');adjusted=np.empty(4);bound=0.
    for i,index in enumerate(order):bound=max(bound,p[index]*(4-i));adjusted[index]=min(1,bound)
    close(tests.p_value_holm,adjusted)
    for _,row in pd.read_csv(OUTPUT/'summary_statistics.csv').iterrows():
        x=raw[(raw.policy==row.policy)][row.metric].to_numpy();close(row['mean'],x.mean());close(row.standard_deviation,x.std(ddof=1))
        lo,hi=reference_ci(x,f"{(row.policy,)}:{row.metric}");close([row.ci95_lower,row.ci95_upper],[lo,hi])
    legacy_count=0
    for manifest_name in ('protected_hashes.json','artifact_hashes.json'):
        manifest=json.loads((ROOT/'results/strong_baseline_30seeds'/manifest_name).read_text())
        for relative,fingerprint in manifest.items():assert sha(ROOT/relative)==fingerprint,relative
        legacy_count+=len(manifest)
    result=dict(successful=True,runs=60,requests_verified=total,subgroup_calculations_verified=subgroup_checks,
        statistical_primary_metrics_verified=4,bootstrap_resamples=10000,profile_validation=verify_profiles(),
        resource_and_controller_exports_verified=True,legacy_manifest_entries_verified=legacy_count,prior_artifacts=verify())
    write_json(OUTPUT/'validation.json',result);print(json.dumps(result),flush=True);return result
