"""Sequential paired experiments, frozen endpoints, auditable full exports."""
from dataclasses import asdict
from pathlib import Path
import gc,json,time
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_gzip
from dynamic_placement.metrics import calculate_metrics
from dynamic_placement.scenario_model import traffic_hash_payload
from paper_evaluation.accounting import augment_metrics
from joint_routing.experiment import extra_metrics
from joint_routing.router import Settings
from scalability.experiment import export_run,baseline_metrics
from scalability.measurement import normalized_metrics,MemoryMonitor
from hardware_grounded.environment import ROOT,OUTPUT,write_json
from hardware_grounded.integrity import sha
from hardware_grounded.audit import validate_run
from hardware_grounded.calibration import load_profiles,arrival_hash
from .design import LOADS,REGIMES,POLICIES,regime_inputs,scale_traffic,regime_definitions
from .observer import ObservedBaseline,ObservedJoint
from .diagnostics import pressure_metrics,burst_recovery

SWEEP=ROOT/'results/hardware_pressure_sweep'
CAUSAL=ROOT/'results/hardware_causal_decomposition'

def verify_protected():
    files=json.loads((SWEEP/'protected_hashes.json').read_text())
    changed=[p for p,v in files.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=v]
    if changed:raise RuntimeError('Protected artifact changed: '+str(changed))
    protocol=json.loads((OUTPUT/'experiment_freeze.json').read_text())
    assert sha(OUTPUT/'hardware_profiles.json')==protocol['profile_sha256']
    load_profiles()
    return dict(protected_files=len(files),changed_files=changed,profile_sha256=protocol['profile_sha256'])

def configuration_record():
    return dict(scale='MEDIUM',loads=list(LOADS),seeds=list(range(1,31)),policies=list(POLICIES),
        hardware_profile_sha256=sha(OUTPUT/'hardware_profiles.json'),
        direct_freeze_sha256=sha(OUTPUT/'experiment_freeze.json'),
        plan_sha256=sha(ROOT/'hardware_pressure/PLAN.md'),
        statistics=dict(resamples=10000,bootstrap_seed=73001,primary_family_size=14,secondary_family_size=14,tier_family_size=21,class_family_size=21),
        original_config=asdict(regime_inputs('D0',1)[0]),hardware_config=asdict(regime_inputs('D7',1)[0]),
        source_hashes={f:sha(ROOT/f) for f in ('hardware_pressure/design.py','hardware_pressure/observer.py','hardware_pressure/diagnostics.py','hardware_pressure/experiment.py')})

def freeze():
    value=configuration_record();p=SWEEP/'configuration.json'
    if p.exists():assert json.loads(p.read_text())==value,'new experiment source/config changed after freeze'
    else:write_json(p,value)
    write_json(CAUSAL/'regime_definitions.json',dict(regimes=regime_definitions(),seeds=list(range(1,11)),configuration_sha256=sha(p)))
    return value

def group_rows(outcomes,seed,policy,column,metadata):
    from hardware_grounded.calibration import model_class
    from paper_evaluation.accounting import request_metrics
    f=outcomes.copy();f['model_class']=f.service_id.map(model_class)
    rows=[]
    for key,g in f.groupby(column):
        assert len(g)>=30
        m=request_metrics(g)
        rows.append(dict(**metadata,seed=seed,policy=policy,**{column:key},
            **{k:m[k] for k in ('total_requests','sla_breaches','sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms')},
            mean_queue_delay_ms=float((g.service_queue_ms+g.node_queue_ms).mean())))
    return rows

def verify_export(folder,w,cs,metrics):
    """Vectorized independent re-read; request IDs, components and all totals."""
    f=pd.read_csv(folder/'request_outcomes.csv.gz').sort_values('request_id')
    assert len(f)==len(w.requests) and np.array_equal(f.request_id,np.arange(len(w.requests)))
    assert not f.unplaced.any() and not f.get('dropped',pd.Series(False,index=f.index)).any()
    arrival=np.array([r.arrival_s for r in w.requests]);factor=np.array([r.work_factor for r in w.requests])
    sid=np.array([r.service_id for r in w.requests])
    assert np.array_equal(f.service_id,sid)
    assert np.allclose(f.arrival_s,arrival,rtol=0,atol=1e-12)
    compute=np.array([cs[int(s)].preprocess_ms+cs[int(s)].inference_ms+cs[int(s)].postprocess_ms for s in sid])*factor
    assert np.allclose(f.compute_ms,compute,rtol=0,atol=1e-7)
    network=np.array([w.scenario.network_latency_ms[w.services[int(s)].ingress,int(n)]+1000*r.payload_mbit/w.scenario.nodes[int(n)].bandwidth_capacity_mbps for s,n,r in zip(sid,f.node,w.requests)])
    assert np.allclose(f.network_ms,network,rtol=0,atol=1e-7)
    actual=1000*(f.completion_s-arrival)
    total=f[['compute_ms','network_ms','service_queue_ms','node_queue_ms','lifecycle_penalty_ms']].sum(axis=1)
    assert np.allclose(actual,f.latency_ms,rtol=0,atol=1e-7) and np.allclose(total,actual,rtol=0,atol=1e-7)
    assert np.array_equal(f.breach,actual>f.deadline_ms)
    quant=np.quantile(f.latency_ms,[.5,.95,.99])
    for k,x in zip(('median_latency_ms','p95_latency_ms','p99_latency_ms'),quant):assert abs(metrics[k]-x)<1e-7
    assert abs(metrics['mean_request_latency_ms']-f.latency_ms.mean())<1e-7
    assert abs(metrics['sla_breach_rate']-f.breach.mean())<1e-12
    return len(f)

def execute(out,points,seeds,kind,reuse=False,force=False):
    out.mkdir(parents=True,exist_ok=True);raw_path=out/'raw_results.csv'
    index='load_multiplier' if kind=='sweep' else 'regime'
    expected={(p,s,a) for p in points for s in seeds for a in POLICIES}
    if reuse:
        raw=pd.read_csv(raw_path)
        assert set(zip(raw[index],raw.seed,raw.policy))==expected
        return raw
    if raw_path.exists() and not force:raise FileExistsError('use --reuse-results or --force')
    profiles=load_profiles();rows=[];tier=[];classes=[];bursts=[];checks=[];start=time.perf_counter()
    for point in points:
        label=f'load_{point:.2f}' if kind=='sweep' else point
        for seed in seeds:
            c,w,cs=regime_inputs('D7' if kind=='sweep' else point,seed,profiles)
            if kind=='sweep':w=scale_traffic(w,float(point),c)
            meta={index:point};wh=digest(w.to_dict());th=digest(traffic_hash_payload(w));ah=arrival_hash(w)
            inp=out/'inputs'/label;inp.mkdir(parents=True,exist_ok=True)
            write_gzip(inp/f'seed_{seed:03d}.json.gz',w.to_dict())
            write_json(inp/f'seed_{seed:03d}_config.json',dict(config=asdict(c),service_configs={str(k):asdict(v) for k,v in cs.items()},traffic_hash=th,workload_hash=wh))
            for policy in POLICIES:
                gc.collect()
                with MemoryMonitor() as memory:
                    engine=(ObservedBaseline if policy=='sla_aware' else ObservedJoint)(c,w,policy,cs,Settings())
                    result=engine.run()
                check=validate_run(c,w,result,cs)
                legacy,slots,nodes,outcomes=calculate_metrics(c,w,result)
                m=augment_metrics(c,w,result,legacy,outcomes,slots,nodes)
                m.update(baseline_metrics(result) if policy=='sla_aware' else extra_metrics(result,outcomes))
                m.update(normalized_metrics(m,c,result['timing'],len(result['routing'])))
                pool=0.;peak=0.
                for event in result['reservations']:
                    pool+=event['sign']*w.services[event['service_id']].gpu_vram_gb;peak=max(peak,pool)
                m.update(average_vram_residency_gib=m['vram_gb_seconds']/(c.slots*c.slot_seconds),peak_pool_vram_gib=peak,
                    max_waiting_requests=int(slots.waiting_requests.max()),sampled_peak_process_rss_mib=memory.peak,
                    triggered_downtime_seconds=sum(v['ready_s']-v['start_s'] for v in result['lifecycle']),N_nodes=c.node_count,N_services=c.service_count)
                m.update(pressure_metrics(c,w,result,slots,nodes,outcomes))
                m={k:v for k,v in m.items() if 'utilization_node_' not in k}
                assert all(np.isfinite(v) for k,v in m.items() if isinstance(v,(int,float)) and k!='routing_under_contention_fraction')
                row=dict(**meta,seed=seed,policy=policy,traffic_hash=th,workload_hash=wh,original_arrival_hash=ah,**m)
                rows.append(row);tier.extend(group_rows(outcomes,seed,policy,'tier',meta));classes.extend(group_rows(outcomes,seed,policy,'model_class',meta))
                br=burst_recovery(c,w,outcomes,result['pressure_services'],result['actions'],result['lifecycle'],result['replica_services'])
                for k,v in dict(**meta,seed=seed,policy=policy).items():br[k]=v
                bursts.append(br)
                folder=out/'runs'/label/f'seed_{seed:03d}'/policy
                export_run(folder,result,slots,nodes,outcomes)
                for name in ('pressure_services','pressure_nodes'):
                    pd.DataFrame(result[name]).to_csv(folder/f'{name}.csv.gz',index=False,compression={'method':'gzip','mtime':0})
                check['export_requests_verified']=verify_export(folder,w,cs,m)
                checks.append(dict(**meta,seed=seed,policy=policy,**check))
                pd.DataFrame(rows).to_csv(out/'progress_results.csv',index=False)
                print(f'{kind} {point} seed {seed:02d} {policy}: requests {len(w.requests)}, breach {100*m["sla_breach_rate"]:.2f}%, p95 {m["p95_latency_ms"]:.2f}, wall {m["wall_clock_seconds"]:.2f}s',flush=True)
                del result,engine,outcomes,slots,nodes
            assert digest(w.to_dict())==wh
    raw=pd.DataFrame(rows)
    assert set(zip(raw[index],raw.seed,raw.policy))==expected and not raw.duplicated([index,'seed','policy']).any()
    for _,g in raw.groupby([index,'seed']):
        assert all(g[k].nunique()==1 for k in ('traffic_hash','workload_hash','original_arrival_hash','total_requests'))
    raw.to_csv(raw_path,index=False);pd.DataFrame(tier).to_csv(out/'tier_results.csv',index=False)
    pd.DataFrame(classes).to_csv(out/'model_class_results.csv',index=False);pd.concat(bursts).to_csv(out/'burst_recovery.csv',index=False)
    write_json(out/'validation.json',dict(runs=len(raw),requests_verified=int(raw.total_requests.sum()),
        exported_request_outcomes_verified=int(raw.total_requests.sum()),routing_choices_verified=sum(x['routing_choices_verified'] for x in checks),
        shared_tapes=True,no_lost_or_duplicate_requests=True,per_run_checks=checks,wall_seconds=time.perf_counter()-start))
    return raw

def assert_direct_reproduction(raw,folder):
    """Exact physical traces modulo CSV float round trips and wall-clock timings."""
    from pandas.testing import assert_frame_equal
    old=pd.read_csv(OUTPUT/'raw_results.csv').set_index(['seed','policy'])
    metrics=('total_requests','sla_breach_rate','mean_request_latency_ms','median_latency_ms','p95_latency_ms','p99_latency_ms','average_replicas','average_vram_residency_gib','total_actions','cold_starts','migrations')
    checked=0
    for row in raw.itertuples():
        baseline=old.loc[row.seed,row.policy]
        for k in metrics:assert np.isclose(getattr(row,k),baseline[k],atol=1e-10,rtol=0),(row.seed,row.policy,k)
        new=folder/'runs/load_1.00'/f'seed_{row.seed:03d}'/row.policy
        original=OUTPUT/'runs'/f'seed_{row.seed:03d}'/row.policy
        assert row.traffic_hash==baseline.traffic_hash and row.workload_hash==baseline.workload_hash
        for name in ('request_outcomes','slot_trajectories','node_trajectories','actions','reservation_events','lifecycle_events','routing_decisions','routing_attempts','deployment_audit'):
            a=pd.read_csv(new/f'{name}.csv.gz');b=pd.read_csv(original/f'{name}.csv.gz')
            keep=[k for k in a if 'runtime' not in k and 'cpu_ms' not in k]
            assert_frame_equal(a[keep],b[keep],check_exact=False,rtol=0,atol=1e-10)
            checked+=1
    value=dict(passed=True,seeds=sorted(raw.seed.unique().tolist()),runs=len(raw),trace_tables_verified=checked,
        metrics_verified=list(metrics),only_excluded_fields='nondeterministic instrumentation runtime/cpu time',traffic_hash_exact=True,workload_hash_exact=True)
    write_json(SWEEP/'direct_reproduction.json',value);return value

def pilot():
    if not (SWEEP/'direct_reproduction.json').exists():
        raw=execute(SWEEP/'reproduction',[1.],range(1,4),'sweep')
        assert_direct_reproduction(raw,SWEEP/'reproduction')
    else:assert json.loads((SWEEP/'direct_reproduction.json').read_text())['passed']
    out=SWEEP/'pilot';raw=execute(out,[.5,2.],range(1,4),'sweep',reuse=(out/'raw_results.csv').exists())
    good=bool(raw.wall_clock_seconds.le(600).all() and raw.sampled_peak_process_rss_mib.le(4096).all() and raw.drain_seconds.le(120).all())
    write_json(SWEEP/'pilot_validation.json',dict(successful=good,runs=len(raw),requests_verified=int(raw.total_requests.sum()),max_wall_seconds=float(raw.wall_clock_seconds.max()),max_drain_seconds=float(raw.drain_seconds.max()),max_rss_mib=float(raw.sampled_peak_process_rss_mib.max())))
    assert good,'Pilot gate failed; no tuning allowed'
    freeze();return raw
