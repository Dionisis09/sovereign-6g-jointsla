"""Independent exported-input, subgroup, memory and endpoint verification."""
import gzip,json
import numpy as np
import pandas as pd
from catalyst.reused import digest
from hardware_grounded.environment import ROOT,OUTPUT,write_json
from hardware_grounded.integrity import sha
from hardware_grounded.calibration import model_class
from paper_evaluation.validation import linear_quantile
from .experiment import SWEEP,CAUSAL,verify_protected

def close(a,b):assert np.allclose(a,b,rtol=1e-10,atol=1e-7),(a,b)

def verify_study(out,index):
    raw=pd.read_csv(out/'raw_results.csv');tiers=pd.read_csv(out/'tier_results.csv');classes=pd.read_csv(out/'model_class_results.csv')
    requests=0;groups=0;endpoint_checks=0
    endpoints=pd.read_csv(OUTPUT/'raw_results.csv').set_index(['seed','policy'])
    original=pd.read_csv(ROOT/'results/scalability_30seeds/raw_results.csv')
    original=original[original.scale=='MEDIUM'].set_index(['seed','policy'])
    endpoint_metrics=('sla_breach_rate','mean_request_latency_ms','median_latency_ms','p95_latency_ms','p99_latency_ms','average_replicas','total_actions','scale_outs','scale_ins','migrations','cold_starts')
    for (point,seed),pair in raw.groupby([index,'seed']):
        label=f'load_{point:.2f}' if index=='load_multiplier' else point
        with gzip.open(out/'inputs'/label/f'seed_{seed:03d}.json.gz','rt',encoding='utf-8') as stream:w=json.load(stream)
        assert digest(w)==pair.workload_hash.iloc[0]
        assert digest({k:w[k] for k in ('seed','services','requests','traffic')})==pair.traffic_hash.iloc[0]
        assert all(pair[k].nunique()==1 for k in ('traffic_hash','workload_hash','total_requests'))
        request=pd.DataFrame(w['requests']).set_index('request_id')
        services={s['service_id']:s for s in w['services']}
        traffic=pd.DataFrame(w['traffic'])
        original_traffic=pd.DataFrame(json.loads(gzip.decompress((OUTPUT/'inputs'/f'seed_{seed:03d}.json.gz').read_bytes()))['traffic'])
        assert np.array_equal(traffic.burst,original_traffic.burst)
        close(traffic.expected_rate_rps,original_traffic.expected_rate_rps*(point if index=='load_multiplier' else 1))
        for r in pair.itertuples():
            folder=out/'runs'/label/f'seed_{seed:03d}'/r.policy
            f=pd.read_csv(folder/'request_outcomes.csv.gz').set_index('request_id').sort_index()
            assert np.array_equal(f.index,request.index) and f.index.is_unique and len(f)==r.total_requests
            close(f.service_id,request.service_id);close(f.arrival_s,request.arrival_s);close(f.arrival_slot,request.arrival_slot)
            f['model_class']=f.service_id.map(model_class)
            for column,source in [('tier',tiers),('model_class',classes)]:
                for key,g in f.groupby(column):
                    row=source[(source[index]==point)&(source.seed==seed)&(source.policy==r.policy)&(source[column]==key)].iloc[0]
                    assert row.total_requests==len(g) and row.sla_breaches==g.breach.sum()
                    close(row.sla_breach_rate,g.breach.mean());close(row.mean_request_latency_ms,g.latency_ms.mean())
                    close(row.p95_latency_ms,linear_quantile(g.latency_ms,.95));close(row.p99_latency_ms,linear_quantile(g.latency_ms,.99))
                    close(row.mean_queue_delay_ms,(g.service_queue_ms+g.node_queue_ms).mean());groups+=1
            nodes=pd.read_csv(folder/'node_trajectories.csv.gz');slots=pd.read_csv(folder/'slot_trajectories.csv.gz')
            events=pd.read_csv(folder/'reservation_events.csv.gz');actions=pd.read_csv(folder/'actions.csv.gz');lc=pd.read_csv(folder/'lifecycle_events.csv.gz')
            snapshot=pd.read_csv(folder/'control_snapshot_times.csv.gz')
            for resource in ('cpu','gpu'):close(getattr(r,f'average_{resource}_utilization'),nodes[f'{resource}_utilization'].mean())
            waiting=f.service_queue_ms+f.node_queue_ms;close(r.mean_queue_delay_ms,waiting.mean());close(r.p95_queue_delay_ms,linear_quantile(waiting,.95))
            close(r.average_queue_length,slots.waiting_requests.mean());assert r.peak_queue_length==slots.waiting_requests.max()
            total=slots.set_index('slot').decision_runtime_ms+snapshot.set_index('slot').runtime_ms
            close(r.controller_total_instrumented_mean_ms,total.mean());close(r.controller_total_instrumented_p95_ms,linear_quantile(total,.95))
            # Ledger integration: migration adds memory but not a new replica.
            pool=0.;replicas=0.;last=0.;area=0.;replica_area=0.;peak=0.;horizon=10.
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
            for metric,kind in [('scale_outs','scale_up'),('scale_ins','scale_down'),('migrations','migrate')]:assert getattr(r,metric)==actions.kind.eq(kind).sum()
            # Both endpoints exactly reproduce their frozen original regimes.
            reference=endpoints.loc[seed,r.policy] if point in (1.,'D7') else original.loc[seed,r.policy] if point=='D0' else None
            if reference is not None:
                assert r.workload_hash==reference.workload_hash and r.traffic_hash==reference.traffic_hash
                for metric in endpoint_metrics:close(getattr(r,metric),reference[metric])
                endpoint_checks+=1
            requests+=len(f)
    receipt=dict(runs=len(raw),requests_verified=requests,subgroup_rows_verified=groups,endpoint_policy_runs_verified=endpoint_checks,
        independent_input_hashes=True,independent_memory_integrals=True,independent_controller_quantiles=True,independent_subgroup_metrics=True,
        preserved=verify_protected())
    write_json(out/'independent_validation.json',receipt);return receipt

def finalize(reuse_validation=False):
    if reuse_validation:
        a=json.loads((SWEEP/'independent_validation.json').read_text(encoding='utf-8'))
        b=json.loads((CAUSAL/'independent_validation.json').read_text(encoding='utf-8'))
        assert a['runs']==420 and b['runs']==160
    else:a=verify_study(SWEEP,'load_multiplier');b=verify_study(CAUSAL,'regime')
    import xml.etree.ElementTree as ET
    suites=list(ET.parse(SWEEP/'tests.xml').getroot().iter('testsuite'))
    tests=sum(int(s.attrib['tests']) for s in suites);assert tests>=213 and sum(int(s.attrib['failures'])+int(s.attrib['errors']) for s in suites)==0
    protected=verify_protected()
    requested_sweep=['01_sla_vs_load','02_mean_latency_vs_load','03_p95_vs_load','04_p99_vs_load','05_delta_sla_vs_load','06_delta_p95_vs_load','07_replicas_vs_load','08_vram_vs_load','09_actions_vs_load','10_queue_delay_vs_load','11_performance_resource_frontier','12_gold_silver_bronze_vs_load','13_model_class_vs_load','14_controller_overhead_vs_load']
    requested_causal=['01_sla_difference_by_regime','02_p95_difference_by_regime','03_replica_difference_by_regime','04_cold_start_difference_by_regime','05_queue_difference_by_regime','06_burst_recovery_example','07_replica_time_series_example']
    for out,names,count in [(SWEEP,requested_sweep,22),(CAUSAL,requested_causal,16)]:
        assert sum(line.startswith('# ') for line in (out/'report.md').read_text(encoding='utf-8').splitlines())==count
        for name in names:
            for ext in ('png','svg','pdf'):
                path=out/'figures'/f'{name}.{ext}';assert path.is_file() and path.stat().st_size>1000
                if ext=='svg':ET.parse(path)
                if ext=='pdf':assert path.read_bytes().startswith(b'%PDF')
    totals=dict(primary_simulations=a['runs']+b['runs'],reproduction_simulations=6,pilot_simulations=12,
        total_simulations=a['runs']+b['runs']+18,primary_requests_verified=a['requests_verified']+b['requests_verified'],
        total_requests_verified=a['requests_verified']+b['requests_verified']+int(pd.read_csv(SWEEP/'reproduction/raw_results.csv').total_requests.sum())+int(pd.read_csv(SWEEP/'pilot/raw_results.csv').total_requests.sum()),
        tests_passed=tests,protected_files=protected['protected_files'],changed_files=[],new_figure_groups=23,
        requested_figure_groups=21,formats=['PNG 300dpi','SVG','PDF'],old_hardware_profiles_unchanged=True)
    write_json(SWEEP/'delivery_validation.json',totals)
    files={}
    for out in (SWEEP,CAUSAL):
        for path in out.rglob('*'):
            if path.is_file() and path.name!='artifact_hashes.json':files[path.relative_to(ROOT).as_posix()]=sha(path)
    for path in (ROOT/'hardware_pressure').glob('*'):
        if path.is_file():files[path.relative_to(ROOT).as_posix()]=sha(path)
    for name in ('run_hardware_pressure_sweep.py','run_hardware_causal_decomposition.py','tests/test_hardware_pressure.py'):files[name]=sha(ROOT/name)
    write_json(SWEEP/'artifact_hashes.json',files)
    print(json.dumps(totals,indent=2));return totals

if __name__=='__main__':finalize()
