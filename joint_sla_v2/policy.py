"""Dimensionally explicit causal warm headroom; v1 routing is untouched."""
from dataclasses import dataclass,asdict
import math
import numpy as np
from dynamic_placement.policies import Action,risk_score,_eligible,_fits
from joint_routing.controller import joint_actions,deployment_quality

@dataclass(frozen=True)
class Parameters:
    gold_multiplier:float=1.5
    gold_floor:int=2
    base_headroom:float=1.

def required_warm(queue,rate_rps,cold_seconds,cycle_seconds,deadline_seconds,tier,max_replicas=3,parameters=Parameters()):
    """Requests / serial-service capacity -> bounded integer ready replicas."""
    if queue<0 or rate_rps<0 or cold_seconds<=0 or deadline_seconds<=0:raise ValueError('invalid causal demand/units')
    floor=parameters.gold_floor if tier=='Gold' else 1
    multiplier={'Gold':parameters.gold_multiplier,'Silver':math.sqrt(parameters.gold_multiplier),'Bronze':1.}[tier]*parameters.base_headroom
    if not math.isfinite(cycle_seconds) or cycle_seconds<=0:return max_replicas
    slack=max(0.,deadline_seconds-cycle_seconds)
    if slack<=0:return min(max_replicas,floor) if queue==0 and rate_rps==0 else max_replicas
    immediate=queue*cycle_seconds/slack
    recovery=(queue+rate_rps*cold_seconds)*cycle_seconds/(cold_seconds+slack)
    return min(max_replicas,max(floor,math.ceil(multiplier*max(immediate,recovery))))

def headroom_rows(config,snap,service_configs,observed_rates,history_slots,parameters=Parameters()):
    rows=[]
    for service in snap['services']:
        sid=service.service_id;ready=snap['routing_candidates'][sid]
        candidates=ready or [c for c in snap['nominal_candidates'][sid] if c['capacity_feasible']]
        cycle=min((c['cycle_ms'] for c in candidates if c['cycle_ms']>0 and math.isfinite(c['cycle_ms'])),default=float('inf'))/1000
        required=required_warm(int(snap['queue_lengths'][sid]),float(observed_rates[sid]),service_configs[sid].cold_start_slots*config.slot_seconds,cycle,service.deadline_ms/1000,service.tier,config.max_replicas,parameters)
        current=snap['replicas'][sid]
        capacity=bool(any(_fits(snap,service,n) for n in range(len(snap['capacities']))))
        rows.append(dict(slot=int(snap['slot']),service_id=sid,tier=service.tier,
            recent_rate_rps=float(observed_rates[sid]),observed_history_slots=history_slots,
            cold_readiness_ms=service_configs[sid].cold_start_slots*config.slot_seconds*1000,
            estimated_cycle_ms=cycle*1000,deadline_ms=service.deadline_ms,current_queue=int(snap['queue_lengths'][sid]),
            required_warm_replicas=required,actual_ready_replicas=len(ready),current_nonretiring_replicas=len(current),
            cold_exposure=any(not r['ready'] for r in current),capacity_feasible_scaleout=capacity,
            deficit=max(0,required-len(ready)),prevented_scale_ins_due_to_headroom=0,
            prevented_scale_ins_Gold=0,gold_repair_scaleouts=0))
    return rows

def actions(config,snap,settings,audit,rows):
    """Retain v1 decisions except unsafe scale-in; bounded Gold-only repair."""
    original=joint_actions(config,snap,settings,audit);retained=[]
    by_sid={r['service_id']:r for r in rows}
    for action in original:
        row=by_sid[action.service_id]
        if action.kind=='scale_down' and row['actual_ready_replicas']-1<row['required_warm_replicas']:
            row['prevented_scale_ins_due_to_headroom']+=1
            row['prevented_scale_ins_Gold']+=int(row['tier']=='Gold')
        else:retained.append(action)
    gold=[s for s in snap['services'] if s.tier=='Gold' and by_sid[s.service_id]['current_nonretiring_replicas']<by_sid[s.service_id]['required_warm_replicas'] and _eligible(config,snap,s.service_id)]
    gold.sort(key=lambda s:(-(by_sid[s.service_id]['required_warm_replicas']-by_sid[s.service_id]['current_nonretiring_replicas']),-risk_score(config,snap,s),-by_sid[s.service_id]['recent_rate_rps'],s.service_id))
    result=[];used=set()
    for service in gold:
        sid=service.service_id;replicas=snap['replicas'][sid]
        if not replicas or len(replicas)>=config.max_replicas:continue
        ready=[{**r,'queue_length':0} for r in snap['routing_candidates'][sid]]
        ages=snap['waiting_ages'][sid][:settings.virtual_batch_limit];choices=[]
        overhead=config.cold_start_slots*config.slot_seconds*1000+config.cold_penalty_ms
        for node in range(len(snap['capacities'])):
            if not _fits(snap,service,node):continue
            projected=snap['nominal_candidates'][sid][node]
            candidate={**projected,'id':max(r['id'] for r in replicas)+10000,
                'available_in_ms':config.cold_start_slots*config.slot_seconds*1000,'penalty_ms':config.cold_penalty_ms}
            score=deployment_quality(config,service,ready+[candidate],ages,snap['capacities'][:,1].sum(),overhead)
            choices.append((score,node))
        if choices:
            _,target=min(choices);result.append(Action('scale_up',sid,target,risk=risk_score(config,snap,service)))
            used.add(sid);by_sid[sid]['gold_repair_scaleouts']+=1
        if len(result)==config.action_budget:break
    for action in retained:
        if len(result)==config.action_budget:break
        if action.service_id not in used:result.append(action);used.add(action.service_id)
    assert len(result)<=config.action_budget
    return result
