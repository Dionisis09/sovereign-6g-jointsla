"""Min-cost current-work assignment and exact budget-two deployment selection."""
from dataclasses import dataclass,asdict
from time import perf_counter_ns
import numpy as np
from scipy.optimize import linear_sum_assignment
from dynamic_placement.policies import Action


@dataclass(frozen=True)
class Weights:
    """Predeclared before any pilot outcomes; all components dimensionless."""
    sla: float=1.
    latency: float=1.
    congestion: float=.25
    resource: float=.35
    cold_scale: float=.25
    migration: float=.25
    routing_block: int=64
    pair_limit: int=50000
    competitive_relative_margin_percent: float=5.


class Solver:
    def __init__(self,weights=None):
        self.weights=weights or Weights();self.events=[]

    def record(self,kind,start,status,**extra):
        self.events.append(dict(kind=kind,status=status,runtime_ms=(perf_counter_ns()-start)/1e6,
                                fallback=status not in ("optimal","feasible"),**extra))

    def assignment(self,candidates,ages,deadline,priority,context="routing"):
        """Exact rectangular matching per block; queue slots model marginal work.

        Request rows retain arrival order; replica columns retain ID/order, then
        slot order. Equal-cost solver output is deterministic for identical input.
        All rows are already-arrived work; virtual deployments add availability
        delays, never future requests. Blocks use accumulated assignments.
        """
        start=perf_counter_ns();count=len(ages)
        if count==0:return [],0.,"optimal"
        if not candidates:
            self.record(context,start,"infeasible",requests=count,candidates=0)
            return [],float("inf"),"infeasible"
        w=self.weights;assigned=np.zeros(len(candidates),dtype=int);destinations=[];objective=0.
        for offset in range(0,count,w.routing_block):
            block=np.array(ages[offset:offset+w.routing_block],dtype=float);size=len(block)
            costs=[]
            for i,c in enumerate(candidates):
                k=np.arange(size,dtype=float)+assigned[i]+c["queue_length"]
                queue=k*c["cycle_ms"]+c["remaining_busy_ms"]
                duration=c["network_ms"]+c["compute_ms"]+c["resource_wait_ms"]+c["penalty_ms"]
                completion=block[:,None]+c.get("available_in_ms",0.)+queue[None,:]+duration
                normalized=completion/deadline
                # Convex normalized lateness surrogate keeps an optimal matching
                # compatible with arrival-order FIFO within each replica.
                violation=np.maximum(0.,normalized-1.)
                costs.append(priority*(w.sla*violation+w.latency*normalized)+w.congestion*queue[None,:]/deadline)
            matrix=np.concatenate(costs,axis=1)
            if not np.isfinite(matrix).all():
                self.record(context,start,"infeasible",requests=count,candidates=len(candidates),reason="nonfinite cost")
                return [],float("inf"),"infeasible"
            try:rows,cols=linear_sum_assignment(matrix)
            except (ValueError,MemoryError) as exc:
                self.record(context,start,"infeasible",requests=count,candidates=len(candidates),reason=type(exc).__name__)
                return [],float("inf"),"infeasible"
            assert np.array_equal(rows,np.arange(size))
            for column in cols:
                idx=int(column//size);destinations.append(candidates[idx]["id"]);assigned[idx]+=1
            objective+=float(matrix[rows,cols].sum())
        self.record(context,start,"optimal",requests=count,candidates=len(candidates),blocks=(count+w.routing_block-1)//w.routing_block,
                    objective=objective)
        return destinations,objective,"optimal"

    def select(self,options,headroom,budget=2):
        """Globally optimal selection over the finite additive action menu.

        No capacity is credited for future removal/source release. Each feasible
        option has nonnegative instantaneous reservation increments. Therefore
        non-improving options cannot enable an improving pair. Ordered lower
        bounds prune only provably dominated pairs. Limit exhaustion returns
        no-op, never a different heuristic or partial incumbent.
        """
        start=perf_counter_ns()
        if budget!=2:raise ValueError("fixed verified budget must be two")
        if any(not np.isfinite(o["delta"]) for o in options):
            self.record("deployment",start,"infeasible",options=len(options),pairs=0)
            return [],"infeasible"
        eligible=sorted((o for o in options if o["delta"]<0),key=lambda o:(o["delta"],o["key"]))
        best=0.;choice=[];best_key=();pairs=0
        def consider(candidate,value):
            nonlocal best,choice,best_key
            key=tuple(sorted(o["key"] for o in candidate))
            if value<best or (value==best and key<best_key):best=value;choice=candidate;best_key=key
        for i,a in enumerate(eligible):
            if 2*a["delta"]>best:break
            if np.all(a["increment"]<=headroom+1e-9):consider([a],a["delta"])
            for b in eligible[i+1:]:
                value=a["delta"]+b["delta"]
                if value>best:break
                pairs+=1
                if pairs>self.weights.pair_limit:
                    self.record("deployment",start,"timeout",options=len(options),pairs=pairs,reason="deterministic pair-work limit; no wall-clock cutoff")
                    return [],"timeout"
                if a["action"].service_id==b["action"].service_id:continue
                if np.all(a["increment"]+b["increment"]<=headroom+1e-9):consider([a,b],value)
        self.record("deployment",start,"optimal",options=len(options),pairs=pairs,objective=best)
        return [o["action"] for o in sorted(choice,key=lambda o:o["key"])],"optimal"


def controller(config,snap,solver):
    """Enumerate feasible deployment menus and jointly choose resource-coupled actions."""
    w=solver.weights;options=[];shape=snap["reserved"].shape
    lifecycle=snap["observable_lifecycle"]
    for s in snap["services"]:
        sid=s.service_id
        if snap["slot"]-snap["last_action"][sid]<config.cooldown_slots:continue
        states=lifecycle[sid];live=snap["routing_candidates"][sid]
        ready=[{**r,"queue_length":0} for r in live]
        ages=snap["waiting_ages"][sid]
        _,keep,_=solver.assignment(ready,ages,s.deadline_ms,s.priority,"deployment_assignment")
        # No eligible current replica while cold/migrating: do not reward an
        # infinite subtraction. Preserve the feasible state until activation.
        if not np.isfinite(keep):continue
        def resource(candidates):
            return w.resource*sum((s.cpu_cores/snap["capacities"][r["node"],0]+s.gpu_vram_gb/snap["capacities"][r["node"],1])/2 for r in candidates)
        keep+=resource(ready)
        def add(action,candidates,overhead,increment):
            _,cost,status=solver.assignment(candidates,ages,s.deadline_ms,s.priority,"deployment_assignment")
            if status=="optimal":
                total=cost+resource(candidates)+overhead
                key=(sid,{"scale_up":0,"scale_down":1,"migrate":2}[action.kind],-1 if action.target is None else action.target,
                     -1 if action.replica_id is None else action.replica_id)
                options.append(dict(action=action,delta=total-keep,increment=increment,key=key))
        for node in range(len(snap["capacities"])):
            if np.any(snap["reserved"][node]+s.reservation>snap["capacities"][node]+1e-9):continue
            nominal=snap["nominal_candidates"][sid][node]
            if not nominal["capacity_feasible"]:continue
            increment=np.zeros(shape);increment[node]=s.reservation
            if len(states)<config.max_replicas:
                pause=config.cold_start_slots*config.slot_seconds*1000
                candidate={**nominal,"id":100000+sid,"available_in_ms":pause,"penalty_ms":config.cold_penalty_ms}
                overhead=w.cold_scale*(pause+config.cold_penalty_ms)/s.deadline_ms
                add(Action("scale_up",sid,node),ready+[candidate],overhead,increment)
            for r in ready:
                if r["node"]==node:continue
                pause=config.migration_down_slots*config.slot_seconds*1000
                candidate={**nominal,"id":r["id"],"available_in_ms":r["remaining_busy_ms"]+pause,"penalty_ms":config.migration_penalty_ms}
                overhead=w.migration*(pause+config.migration_penalty_ms)/s.deadline_ms
                add(Action("migrate",sid,node,r["id"]),[c for c in ready if c["id"]!=r["id"]]+[candidate],overhead,increment)
        if len([r for r in states if not r["retiring"]])>1 and not ages:
            for r in ready:
                if r["busy"]:continue
                overhead=w.cold_scale*(config.preprocess_ms+config.inference_ms+config.postprocess_ms)/s.deadline_ms
                add(Action("scale_down",sid,replica_id=r["id"]),[c for c in ready if c["id"]!=r["id"]],overhead,np.zeros(shape))
    actions,status=solver.select(options,snap["capacities"]-snap["reserved"],config.action_budget)
    return actions
