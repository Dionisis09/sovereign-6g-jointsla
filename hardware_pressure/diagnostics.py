"""Retrospective pressure and burst diagnostics with explicit censoring."""
import numpy as np
import pandas as pd

def burst_recovery(config,workload,outcomes,services,actions,lifecycle,replica_services):
    rows=[];traffic=pd.DataFrame(workload.traffic);out=pd.DataFrame(outcomes)
    sv=pd.DataFrame(services);ac=pd.DataFrame(actions);lc=pd.DataFrame(lifecycle)
    for sid,group in traffic.groupby('service_id',sort=True):
        burst=group.sort_values('slot').burst.to_numpy(bool)
        starts=np.where(burst & ~np.r_[False,burst[:-1]])[0]
        ss=sv[sv.service_id==sid].set_index('slot')
        for j,start in enumerate(starts):
            end=int(start)
            while end<config.slots and burst[end]:end+=1
            stop=int(starts[j+1]) if j+1<len(starts) else config.slots
            pre=ss.loc[max(0,int(start)-1)];threshold=max(int(pre.waiting),1)
            after=ss.loc[(ss.index>=end)&(ss.index<stop)]
            recovered=after.index[after.waiting<=threshold]
            recovery=int(recovered[0]) if len(recovered) else None
            window_stop=recovery if recovery is not None else stop
            # Include the burst even when queue is recovered immediately at end.
            cohort=out[(out.service_id==sid)&(out.arrival_slot>=start)&(out.arrival_slot<window_stop)]
            acts=ac[(ac.service_id==sid)&(ac.kind=='scale_up')&(ac.time_s>=start*config.slot_seconds)&(ac.time_s<stop*config.slot_seconds)] if len(ac) else ac
            first=float(acts.time_s.min()) if len(acts) else np.nan
            cold=lc[(lc.kind=='cold_start')&lc.replica_id.map(lambda r:replica_services[int(r)]==sid)&(lc.start_s>=start*config.slot_seconds)&(lc.start_s<stop*config.slot_seconds)] if len(lc) else lc
            peak=float(ss.loc[(ss.index>=start)&(ss.index<end)].waiting.max())
            rows.append(dict(service_id=int(sid),burst_start_slot=int(start),burst_end_slot=end,
                next_burst_or_horizon_slot=stop,preburst_active_replicas=int(pre.active),preburst_allocated_replicas=int(pre.allocated),
                preburst_waiting=int(pre.waiting),queue_threshold=threshold,burst_peak_waiting=peak,
                queue_growth=max(0.,peak-float(pre.waiting)),first_scaleout_delay_slots=(first/config.slot_seconds-start) if np.isfinite(first) else np.nan,
                scaleout_censored=not np.isfinite(first),cold_starts=len(cold),
                mean_cold_delay_ms=float(((cold.ready_s-cold.start_s)*1000).mean()) if len(cold) else np.nan,
                recovery_slot=recovery,recovery_after_burst_slots=(recovery-end) if recovery is not None else np.nan,
                recovery_from_start_slots=(recovery-start) if recovery is not None else np.nan,recovery_censored=recovery is None,
                recovery_window_requests=len(cohort),recovery_window_breaches=int(cohort.breach.sum()),
                recovery_window_breach_rate=float(cohort.breach.mean()) if len(cohort) else np.nan))
    return pd.DataFrame(rows)

def pressure_metrics(c,w,result,slots,nodes,outcomes):
    sv=pd.DataFrame(result['pressure_services']);pn=pd.DataFrame(result['pressure_nodes'])
    per_slot=sv.groupby('slot');routing=pd.DataFrame(result['routing'])
    waiting=outcomes.service_queue_ms+outcomes.node_queue_ms
    horizon=c.slots*c.slot_seconds
    contention=[]
    if len(routing):
        import json
        for row in routing.itertuples():
            chosen=next(x for x in json.loads(row.candidates_json) if x['id']==row.replica_id)
            contention.append(bool(chosen['busy'] or chosen['queue_length']>0 or chosen['resource_wait_ms']>1e-9))
    return dict(offered_requests_per_slot=len(w.requests)/c.slots,
        completed_requests_per_slot_within_horizon=float(outcomes.completion_s.le(horizon).sum()/c.slots),
        arrival_cohort_completed_per_slot=float(outcomes.latency_ms.notna().sum()/c.slots),
        mean_queue_delay_ms=float(waiting.mean()),p95_queue_delay_ms=float(waiting.quantile(.95)),
        average_queue_length=float(slots.waiting_requests.mean()),peak_queue_length=int(slots.waiting_requests.max()),
        average_active_replicas_per_service=float(sv.active.mean()),
        mean_queue_per_service=float(sv.waiting.mean()),
        resource_saturation_frequency=float((nodes.cpu_utilization.ge(c.high_threshold)|nodes.gpu_utilization.ge(c.high_threshold)|nodes.gpu_vram_reserved_fraction.ge(c.high_threshold)).mean()),
        fraction_slots_no_feasible_scaleout=float((~per_slot.scaleout_feasible.any()).mean()),
        fraction_slots_no_capacity_feasible_scaleout=float((~per_slot.scaleout_capacity_feasible.any()).mean()),
        realized_request_wait_fraction=float(waiting.gt(1e-7).mean()),
        realized_node_contention_fraction=float(outcomes.node_queue_ms.gt(1e-7).mean()),
        routing_under_contention_fraction=float(np.mean(contention)) if contention else np.nan,
        action_budget_exhausted_fraction=float(slots.accepted_actions.ge(c.action_budget).mean()),
        mean_free_cpu_cores=float(pn.free_cpu_cores.mean()),mean_free_gpu_units=float(pn.free_gpu_units.mean()),
        mean_free_vram_gib=float(pn.free_vram_gib.mean()))
