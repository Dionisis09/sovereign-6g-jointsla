"""Paired three-policy exports with unchanged physical/accounting auditors."""
from dataclasses import asdict
import gc,time,json
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
from hardware_grounded.environment import write_json
from hardware_grounded.audit import validate_run
from hardware_grounded.calibration import arrival_hash
from hardware_pressure.experiment import group_rows,verify_export
from hardware_pressure.observer import ObservedBaseline,ObservedJoint
from hardware_pressure.diagnostics import pressure_metrics,burst_recovery
from .simulator import V2Simulator
from .policy import headroom_rows,Parameters
from .protocol import DEV,FINAL,SEEDS,LOADS,POLICIES,generate,seed_gate,now

def headroom_metrics(c,result):
    frame=pd.DataFrame(result['headroom'])
    accepted=pd.DataFrame(result['actions'])
    scale=accepted[accepted.kind=='scale_up'] if len(accepted) else accepted
    frame['accepted_scaleout']=False;frame['accepted_scalein']=False
    for a in accepted.itertuples():
        slot=int(round(a.time_s/c.slot_seconds))
        key=frame.slot.eq(slot)&frame.service_id.eq(a.service_id)
        if a.kind=='scale_up':frame.loc[key,'accepted_scaleout']=True
        if a.kind=='scale_down':frame.loc[key,'accepted_scalein']=True
    if len(frame):
        assert (frame.loc[frame.accepted_scalein,'actual_ready_replicas']-1>=frame.loc[frame.accepted_scalein,'required_warm_replicas']).all()
    return frame,dict(prevented_scale_ins_due_to_headroom=int(frame.prevented_scale_ins_due_to_headroom.sum()),
        prevented_scale_ins_Gold=int(frame.prevented_scale_ins_Gold.sum()),
        headroom_deficit_frequency=float(frame.deficit.gt(0).mean()),
        service_seconds_below_required=float(frame.deficit.gt(0).sum()*c.slot_seconds),
        mean_required_warm_replicas=float(frame.required_warm_replicas.mean()),mean_actual_ready_replicas=float(frame.actual_ready_replicas.mean()),
        scaleouts_during_cold_exposure=int((frame.accepted_scaleout&frame.cold_exposure).sum()),
        gold_repair_scaleouts_proposed=int(frame.gold_repair_scaleouts.sum()),
        gold_repair_scaleouts_accepted=int((frame.gold_repair_scaleouts.gt(0)&frame.accepted_scaleout).sum()))

def execute(phase,reuse=False,force=False):
    out=DEV if phase=='development' else FINAL
    for seed in SEEDS[phase]:seed_gate(phase,seed)
    expected={(p,s,a) for p in LOADS[phase] for s in SEEDS[phase] for a in POLICIES}
    raw_path=out/'raw_results.csv'
    if reuse:
        raw=pd.read_csv(raw_path)
        assert set(zip(raw.load_multiplier,raw.seed,raw.policy))==expected
        return raw
    if raw_path.exists() and not force:raise FileExistsError('Use --reuse-results or --force')
    rows=[];tiers=[];classes=[];bursts=[];headrooms=[];checks=[];start=time.perf_counter()
    for point in LOADS[phase]:
        label=f'load_{point:.2f}'
        for seed in SEEDS[phase]:
            c,w,cs=generate(phase,seed,point);meta=dict(load_multiplier=point)
            wh=digest(w.to_dict());th=digest(traffic_hash_payload(w));ah=arrival_hash(w)
            inp=out/'inputs'/label;inp.mkdir(parents=True,exist_ok=True)
            write_gzip(inp/f'seed_{seed:03d}.json.gz',w.to_dict())
            write_json(inp/f'seed_{seed:03d}_config.json',dict(config=asdict(c),service_configs={str(k):asdict(v) for k,v in cs.items()},traffic_hash=th,workload_hash=wh))
            for policy in POLICIES:
                gc.collect()
                engine_class={'sla_aware':ObservedBaseline,'joint_sla_v1':ObservedJoint,'joint_sla_v2':V2Simulator}[policy]
                original_policy='sla_aware' if policy=='sla_aware' else 'joint_sla'
                with MemoryMonitor() as memory:
                    engine=engine_class(c,w,original_policy,cs,Settings());result=engine.run()
                check=validate_run(c,w,result,cs)
                legacy,slots,nodes,outcomes=calculate_metrics(c,w,result)
                m=augment_metrics(c,w,result,legacy,outcomes,slots,nodes)
                m.update(baseline_metrics(result) if policy=='sla_aware' else extra_metrics(result,outcomes))
                m.update(normalized_metrics(m,c,result['timing'],len(result['routing'])))
                pool=peak=0.
                for event in result['reservations']:
                    pool+=event['sign']*w.services[event['service_id']].gpu_vram_gb;peak=max(peak,pool)
                m.update(average_vram_residency_gib=m['vram_gb_seconds']/(c.slots*c.slot_seconds),peak_pool_vram_gib=peak,
                    max_waiting_requests=int(slots.waiting_requests.max()),sampled_peak_process_rss_mib=memory.peak,
                    triggered_downtime_seconds=sum(v['ready_s']-v['start_s'] for v in result['lifecycle']),N_nodes=c.node_count,N_services=c.service_count,
                    controller_decision_median_ms=float(slots.decision_runtime_ms.median()))
                m.update(pressure_metrics(c,w,result,slots,nodes,outcomes))
                m={k:v for k,v in m.items() if 'utilization_node_' not in k}
                if policy=='joint_sla_v2':
                    hr,hm=headroom_metrics(c,result);m.update(hm)
                    hr=hr.assign(**meta,seed=seed,policy=policy);headrooms.append(hr)
                assert all(np.isfinite(v) for k,v in m.items() if isinstance(v,(int,float)) and k!='routing_under_contention_fraction')
                rows.append(dict(**meta,seed=seed,policy=policy,traffic_hash=th,workload_hash=wh,original_arrival_hash=ah,**m))
                tiers.extend(group_rows(outcomes,seed,policy,'tier',meta));classes.extend(group_rows(outcomes,seed,policy,'model_class',meta))
                br=burst_recovery(c,w,outcomes,result['pressure_services'],result['actions'],result['lifecycle'],result['replica_services'])
                # Retrospective action count and physical cold exposure, no controller access to burst masks.
                ac=pd.DataFrame(result['actions']);sv=pd.DataFrame(result['pressure_services'])
                br['scaleout_count']=0;br['cold_exposure_service_seconds']=0.
                for i,b in br.iterrows():
                    a=ac[(ac.service_id==b.service_id)&ac.kind.eq('scale_up')&ac.time_s.ge(b.burst_start_slot*c.slot_seconds)&ac.time_s.lt(b.next_burst_or_horizon_slot*c.slot_seconds)]
                    br.loc[i,'scaleout_count']=len(a)
                    exposure=sv[sv.service_id.eq(b.service_id)&sv.slot.ge(b.burst_start_slot)&sv.slot.lt(b.next_burst_or_horizon_slot)]
                    br.loc[i,'cold_exposure_service_seconds']=float((exposure.allocated-exposure.active).clip(lower=0).gt(0).sum()*c.slot_seconds)
                for k,v in dict(**meta,seed=seed,policy=policy).items():br[k]=v
                bursts.append(br)
                folder=out/'runs'/label/f'seed_{seed:03d}'/policy
                export_run(folder,result,slots,nodes,outcomes)
                for name in ('pressure_services','pressure_nodes'):
                    pd.DataFrame(result[name]).to_csv(folder/f'{name}.csv.gz',index=False,compression={'method':'gzip','mtime':0})
                if policy=='joint_sla_v2':hr.to_csv(folder/'headroom.csv.gz',index=False,compression={'method':'gzip','mtime':0})
                check['export_requests_verified']=verify_export(folder,w,cs,m)
                check['max_accepted_actions_per_slot']=int(slots.accepted_actions.max())
                assert check['max_accepted_actions_per_slot']<=c.action_budget
                checks.append(dict(**meta,seed=seed,policy=policy,**check))
                pd.DataFrame(rows).to_csv(out/'progress_results.csv',index=False)
                print(f'{phase} {point} seed {seed} {policy}: requests {len(w.requests)}, breach {100*m["sla_breach_rate"]:.2f}%, p95 {m["p95_latency_ms"]:.2f}, wall {m["wall_clock_seconds"]:.2f}s',flush=True)
                del result,engine,outcomes,slots,nodes
            assert digest(w.to_dict())==wh
    raw=pd.DataFrame(rows)
    assert set(zip(raw.load_multiplier,raw.seed,raw.policy))==expected
    assert not raw.duplicated(['load_multiplier','seed','policy']).any()
    for _,g in raw.groupby(['load_multiplier','seed']):
        assert all(g[k].nunique()==1 for k in ('traffic_hash','workload_hash','original_arrival_hash','total_requests'))
    raw.to_csv(raw_path,index=False);pd.DataFrame(tiers).to_csv(out/'tier_results.csv',index=False)
    pd.DataFrame(classes).to_csv(out/'model_class_results.csv',index=False);pd.concat(bursts).to_csv(out/'burst_results.csv',index=False)
    pd.concat(headrooms).to_csv(out/'headroom_results.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    # Requested plain CSV companion; trajectories retain explicit per-service/slot units.
    pd.concat(headrooms).to_csv(out/'headroom_results.csv',index=False)
    write_json(out/'validation.json',dict(timestamp=now(),runs=len(raw),requests_verified=int(raw.total_requests.sum()),
        exported_request_outcomes_verified=int(raw.total_requests.sum()),routing_choices_verified=sum(x['routing_choices_verified'] for x in checks),
        shared_tapes=True,no_lost_or_duplicate_requests=True,per_run_checks=checks,wall_seconds=time.perf_counter()-start))
    if phase=='development':
        v2=raw[raw.policy=='joint_sla_v2']
        passed=bool(raw.wall_clock_seconds.le(600).all() and raw.sampled_peak_process_rss_mib.le(4096).all() and raw.drain_seconds.le(120).all() and v2.controller_decision_mean_ms.lt(10).all())
        write_json(out/'engineering_acceptance.json',dict(passed=passed,candidates_evaluated=1,selection='engineering gates only; no QoS optimization',
            runs=len(raw),seeds=list(SEEDS[phase]),loads=list(LOADS[phase]),max_v2_controller_mean_ms=float(v2.controller_decision_mean_ms.max()),
            max_wall_seconds=float(raw.wall_clock_seconds.max()),max_drain_seconds=float(raw.drain_seconds.max()),max_rss_mib=float(raw.sampled_peak_process_rss_mib.max())))
        assert passed,'Engineering gate failed; do not freeze'
    return raw
