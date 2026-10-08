"""Slow-timescale deployment quality estimated through virtual current routing."""
import copy
import numpy as np
from dynamic_placement.policies import Action, risk_score, _eligible, _fits, _removal
from .router import estimate


def deployment_quality(config, service, candidates, waiting_ages, available_memory, overhead_ms=0.):
    """Greedy virtual dispatch of a bounded prefix of currently waiting requests.

    Empty queues use one nominal probe to assess possible routing, not a future
    arrival or its hidden service work. Candidate availability includes cold
    starts/migration pauses. The virtual copy does not affect actual execution.
    """
    if not candidates:
        return float("inf")
    virtual=copy.deepcopy(candidates)
    ages=waiting_ages or [0.]
    costs=[]
    for age in ages:
        best=min(virtual,key=lambda c:estimate(c,service.deadline_ms,age)["key"])
        e=estimate(best,service.deadline_ms,age)
        costs.append(e["estimated_completion_ms"]/service.deadline_ms+e["risk_proxy"])
        best["queue_length"]+=1
    resource = sum(c["resource_fraction"] for c in virtual)
    return (service.priority*float(np.mean(costs)) + config.headroom_weight*resource
            + config.overhead_weight*overhead_ms/(service.deadline_ms*len(ages)))


def joint_actions(config,snap,settings,audit):
    """Same action feasibility/budget/cooldown; routing-aware keep/action choice."""
    ranked=sorted(snap["services"],key=lambda s:(-risk_score(config,snap,s),-s.priority,-snap["rates"][s.service_id],s.service_id))
    actions=[]
    for service in ranked:
        sid=service.service_id
        replicas=snap["replicas"][sid]
        if not replicas or not _eligible(config,snap,sid):
            continue
        ready=snap["routing_candidates"][sid]
        # All waiting work is reassigned virtually, so remove existing queued counts.
        ready=[{**r,"queue_length":0} for r in ready]
        ages=snap["waiting_ages"][sid][:settings.virtual_batch_limit]
        current=deployment_quality(config,service,ready,ages,snap["capacities"][:,1].sum())
        risk=risk_score(config,snap,service)
        active=max(1,len(ready))
        compute=(config.preprocess_ms+config.inference_ms+config.postprocess_ms)/1000
        pressure=(risk/service.priority>=config.risk_threshold or snap["rates"][sid]*compute/active>=config.high_threshold)
        choices=[]
        if not pressure:
            remove=_removal(config,snap,service)
            if remove:
                subset=[r for r in ready if r["id"]!=remove.replica_id]
                score=deployment_quality(config,service,subset,ages,snap["capacities"][:,1].sum())
                choices.append((score,remove))
        if pressure:
            for node in range(len(snap["capacities"])):
                if not _fits(snap,service,node):
                    continue
                projected=snap["nominal_candidates"][sid][node]
                if len(replicas)<config.max_replicas:
                    overhead=config.cold_start_slots*config.slot_seconds*1000+config.cold_penalty_ms
                    candidate={**projected,"id":max([r["id"] for r in replicas])+10000,
                               "available_in_ms":config.cold_start_slots*config.slot_seconds*1000,
                               "penalty_ms":config.cold_penalty_ms}
                    score=deployment_quality(config,service,ready+[candidate],ages,snap["capacities"][:,1].sum(),overhead)
                    choices.append((score,Action("scale_up",sid,node,risk=risk)))
                for replica in ready:
                    if replica["node"]==node or max(snap["utilization"][replica["node"]])<=config.high_threshold:
                        continue
                    overhead=config.migration_down_slots*config.slot_seconds*1000+config.migration_penalty_ms
                    target={**projected,"id":replica["id"],
                            "available_in_ms":replica["remaining_busy_ms"]+config.migration_down_slots*config.slot_seconds*1000,
                            "penalty_ms":config.migration_penalty_ms}
                    candidates=[r for r in ready if r["id"]!=replica["id"]]+[target]
                    score=deployment_quality(config,service,candidates,ages,snap["capacities"][:,1].sum(),overhead)
                    choices.append((score,Action("migrate",sid,node,replica["id"],risk)))
        if choices:
            score,action=min(choices,key=lambda pair:(pair[0],pair[1].kind!="scale_up",pair[1].target or 0,pair[1].replica_id or 0))
            accepted=score<current-1e-12
            audit.append(dict(slot=snap["slot"],service_id=sid,keep_score=current,candidate_score=score,
                              kind=action.kind,target=action.target,proposed=accepted,
                              observed_waiting=int(snap["queue_lengths"][sid]),virtual_batch_size=len(ages) or 1))
            if accepted:
                actions.append(action)
        if len(actions)==config.action_budget:
            break
    return actions
