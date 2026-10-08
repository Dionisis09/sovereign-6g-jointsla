"""Paired hardware-grounded runs using unchanged policies and request metrics."""
from dataclasses import asdict
import gc,json,time
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_gzip
from dynamic_placement.metrics import calculate_metrics
from dynamic_placement.scenario_model import traffic_hash_payload
from paper_evaluation.accounting import augment_metrics,request_metrics
from joint_routing.experiment import extra_metrics
from joint_routing.router import Settings
from scalability.measurement import normalized_metrics,MemoryMonitor
from scalability.experiment import export_run,baseline_metrics
from .environment import ROOT,OUTPUT,write_json
from .integrity import sha,verify
from .calibration import freeze,hardware_workload,configs_for_services,arrival_hash,model_class
from .physics import HardwareBaseline,HardwareJoint
from .audit import validate_run


def source_freeze():
    paths=[ROOT/'hardware_grounded'/n for n in ('calibration.py','physics.py','audit.py','experiment.py','PLAN.md','SIMULATOR_MAPPING.md')]
    value={p.relative_to(ROOT).as_posix():sha(p) for p in paths};path=OUTPUT/'execution_source_hashes.json'
    if path.exists():assert json.loads(path.read_text())==value,'execution/calibration source changed after freeze'
    else:write_json(path,value)


def group_results(outcomes,seed,policy,columns):
    frame=outcomes.copy();frame['model_class']=frame.service_id.map(model_class)
    rows=[]
    for key,g in frame.groupby(columns,sort=True):
        key=key if isinstance(key,tuple) else (key,)
        if len(g)<30:raise ValueError('predeclared subgroup minimum 30 requests not met')
        m=request_metrics(g);keep=('total_requests','completed_requests','sla_breaches','sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms')
        rows.append(dict(seed=seed,policy=policy,**dict(zip(columns,key)),**{k:m[k] for k in keep},
            mean_queue_delay_ms=float((g.service_queue_ms+g.node_queue_ms).mean())))
    return rows


def input_summary(config,w,cs):
    rates=pd.DataFrame(w.traffic).groupby('service_id').expected_rate_rps.mean()
    return dict(seed=w.seed,requests=len(w.requests),nodes=config.node_count,services=config.service_count,
        hardware_gpu_pressure=float(sum(rates[s.service_id]*cs[s.service_id].inference_ms/1000 for s in w.services)/sum(w.gpu_units)),
        hardware_cpu_pressure=float(sum(rates[s.service_id]*s.cpu_cores*(cs[s.service_id].preprocess_ms+cs[s.service_id].postprocess_ms+config.gpu_stage_cpu_fraction*cs[s.service_id].inference_ms)/1000 for s in w.services)/w.scenario.capacities[:,0].sum()),
        initial_vram_pressure=float(sum(s.gpu_vram_gb for s in w.services)/w.scenario.capacities[:,1].sum()),
        original_deadline_min_ms=min(s.deadline_ms for s in w.services),original_deadline_max_ms=max(s.deadline_ms for s in w.services),
        original_arrival_hash=arrival_hash(w),workload_hash=digest(w.to_dict()),traffic_hash=digest(traffic_hash_payload(w)))


def run(seeds,pilot=False,reuse=False,force=False):
    protocol,profiles,config=freeze();source_freeze()
    out=OUTPUT/'pilot' if pilot else OUTPUT;out.mkdir(parents=True,exist_ok=True)
    raw_path=out/'raw_results.csv'
    if reuse:
        raw=pd.read_csv(raw_path)
        assert set(zip(raw.seed,raw.policy))=={(s,p) for s in seeds for p in ('sla_aware','joint_sla')}
        return raw
    if raw_path.exists() and not force:raise FileExistsError('Use --reuse-results or --force')
    if not pilot:
        check=json.loads((OUTPUT/'pilot/pilot_validation.json').read_text())
        assert check['successful'] and check['profile_sha256']==protocol['profile_sha256']
    rows=[];checks=[];inputs=[];tiers=[];classes=[];cross=[];start=time.perf_counter()
    for seed in seeds:
        w=hardware_workload(profiles,seed);cs=configs_for_services(config,profiles,w.services)
        summary=input_summary(config,w,cs);inputs.append(summary)
        folder=out/'inputs';folder.mkdir(exist_ok=True);write_gzip(folder/f'seed_{seed:03d}.json.gz',w.to_dict())
        write_json(folder/f'seed_{seed:03d}_service_configs.json',{str(k):asdict(v) for k,v in cs.items()})
        for policy in ('sla_aware','joint_sla'):
            gc.collect()
            with MemoryMonitor() as memory:
                engine=(HardwareBaseline if policy=='sla_aware' else HardwareJoint)(config,w,policy,cs,Settings())
                result=engine.run()
            check=validate_run(config,w,result,cs)
            legacy,slots,nodes,outcomes=calculate_metrics(config,w,result)
            m=augment_metrics(config,w,result,legacy,outcomes,slots,nodes)
            m.update(baseline_metrics(result) if policy=='sla_aware' else extra_metrics(result,outcomes))
            m.update(normalized_metrics(m,config,result['timing'],len(result['routing'])))
            pool=0.;peak=0.
            for event in result['reservations']:
                pool+=event['sign']*w.services[event['service_id']].gpu_vram_gb;peak=max(peak,pool)
            m.update(average_vram_residency_gib=m['vram_gb_seconds']/(config.slots*config.slot_seconds),peak_pool_vram_gib=peak,
                max_waiting_requests=int(slots.waiting_requests.max()),sampled_peak_process_rss_mib=memory.peak,
                triggered_downtime_seconds=sum(v['ready_s']-v['start_s'] for v in result['lifecycle']),
                N_nodes=config.node_count,N_services=config.service_count)
            m={k:v for k,v in m.items() if 'utilization_node_' not in k}
            assert np.isfinite([v for v in m.values() if isinstance(v,(int,float))]).all()
            row=dict(regime='DIRECT',scale='MEDIUM',seed=seed,policy=policy,workload_hash=summary['workload_hash'],
                traffic_hash=summary['traffic_hash'],original_arrival_hash=summary['original_arrival_hash'],**m)
            rows.append(row);checks.append(dict(seed=seed,policy=policy,**check))
            tiers.extend(group_results(outcomes,seed,policy,['tier']))
            classes.extend(group_results(outcomes,seed,policy,['model_class']))
            cross.extend(group_results(outcomes,seed,policy,['tier','model_class']))
            export_run(out/'runs'/f'seed_{seed:03d}'/policy,result,slots,nodes,outcomes)
            pd.DataFrame(rows).to_csv(out/'progress_results.csv',index=False)
            print(f"MEDIUM {seed:02d} {policy}: {m['total_requests']:,} verified, SLA {100*m['sla_breach_rate']:.3f}%, mean {m['mean_request_latency_ms']:.2f} ms, p95 {m['p95_latency_ms']:.2f} ms, controller {m['controller_total_instrumented_mean_ms']:.2f} ms, wall {m['wall_clock_seconds']:.2f}s",flush=True)
            del result,engine,outcomes,slots,nodes
        assert digest(w.to_dict())==summary['workload_hash']
    raw=pd.DataFrame(rows)
    for _,g in raw.groupby('seed'):
        assert all(g[k].nunique()==1 for k in ('workload_hash','traffic_hash','original_arrival_hash','total_requests'))
    raw.to_csv(raw_path,index=False);pd.DataFrame(tiers).to_csv(out/'tier_results.csv',index=False)
    pd.DataFrame(classes).to_csv(out/'model_class_results.csv',index=False);pd.DataFrame(cross).to_csv(out/'tier_model_class_results.csv',index=False)
    pd.DataFrame(inputs).to_csv(out/'workload_regime.csv',index=False)
    write_json(out/'simulation_validation.json',dict(successful_runs=len(raw),requests_verified=int(raw.total_requests.sum()),
        routing_choices_verified=sum(r['routing_choices_verified'] for r in checks),per_run_checks=checks,wall_seconds=time.perf_counter()-start))
    if pilot:
        raw.to_csv(OUTPUT/'pilot_results.csv',index=False)
        successful=bool(raw.wall_clock_seconds.le(600).all() and raw.sampled_peak_process_rss_mib.le(4096).all() and raw.drain_seconds.le(120).all())
        write_json(out/'pilot_validation.json',dict(successful=successful,profile_sha256=protocol['profile_sha256'],runs=len(raw),requests_verified=int(raw.total_requests.sum()),
            max_runtime_seconds=float(raw.wall_clock_seconds.max()),max_rss_mib=float(raw.sampled_peak_process_rss_mib.max()),max_drain_seconds=float(raw.drain_seconds.max()),
            maximum_waiting_requests=int(raw.max_waiting_requests.max()),finite_metrics=True,common_hashes=True,unit_and_component_checks=True,
            regime='Direct hardware times; no pressure rescaling or post-pilot tuning. Unlimited queues fully drained.'))
        if not successful:raise RuntimeError('Pilot runtime/RSS/drain gate failed; inspect units without post-hoc traffic changes')
    verify();return raw
