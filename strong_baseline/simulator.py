"""Current-backlog min-cost routing over the unchanged physical SimPy worker."""
import json
from time import perf_counter_ns,process_time_ns,perf_counter
import numpy as np
from dynamic_placement.simulator import Simulator
from dynamic_placement.policies import POLICIES
from controller_optimization.optimized import OptimizedMeasured,IndexedServiceQueues
from joint_routing.router import estimate,choose
from .optimization import Solver,controller


class Observation:
    """Identical extra lifecycle telemetry for both newly timed primary policies."""
    def snapshot(self):
        start=perf_counter_ns();snap=super().snapshot()
        extra_cpu=process_time_ns()
        if abs(self.env.now-self.slot*self.config.slot_seconds)<1e-8:
            snap["observable_lifecycle"]={s.service_id:[] for s in self.services}
            for r in self.replicas.values():
                snap["observable_lifecycle"][r.service_id].append(dict(id=r.replica_id,node=r.node,ready=r.ready,
                          busy=r.busy,pending=r.pending_target is not None,retiring=r.retiring))
            self.observation_times.append(dict(slot=self.slot,runtime_ms=(perf_counter_ns()-start)/1e6))
            # The inherited CPU mixin measures only its own nested snapshot.
            # Charge the common telemetry extension outside that scope too.
            self.cpu_times[self.slot]["snapshot_cpu_ms"]+=(process_time_ns()-extra_cpu)/1e6
        return snap

    def __init__(self,*args,**kwargs):
        self.observation_times=[]
        super().__init__(*args,**kwargs)

    def run(self):
        result=super().run();result["control_snapshot_times"]=self.observation_times
        return result


class FairJoint(Observation,OptimizedMeasured):
    pass


class MJOQueues(IndexedServiceQueues):
    def flush(self,reason):
        self.redistribute(reason)

    def redistribute(self,reason):
        """Optimize all currently waiting service work, preserving in-flight jobs."""
        e=self.engine;start=perf_counter_ns();cpu=process_time_ns()
        rows=self.items
        if not rows:return
        candidates=e.candidates(self.sid)
        base=[{**c,"queue_length":0} for c in candidates]
        s=e.services[self.sid];ages=[max(0.,(e.env.now-r.arrival_s)*1000) for r in rows]
        choices,cost,status=e.solver.assignment(base,ages,s.deadline_ms,s.priority,"routing")
        if status!="optimal":
            # Previous queued assignments remain intact; new pending requests
            # wait for eligibility or the next attempt. Never use JointSLA.
            e.routing_attempts.append(dict(request_id=rows[-1].request_id,time_s=e.env.now,success=False,
                                           runtime_ms=(perf_counter_ns()-start)/1e6))
            e.routing_cpu_ms+=(process_time_ns()-cpu)/1e6
            return
        self.pending.clear()
        for rid in e.service_store_ids[self.sid]:
            store=e.replica_stores[rid]
            while store.items:store.get()
        projected={c["id"]:c.copy() for c in base}
        runtime=(perf_counter_ns()-start)/1e6
        e.routing_attempts.append(dict(request_id=rows[-1].request_id,time_s=e.env.now,success=True,
                                      runtime_ms=runtime,batch_size=len(rows)))
        e.routing_batches.append(dict(time_s=e.env.now,service_id=self.sid,reason=reason,deadline_ms=s.deadline_ms,
            requests_json=json.dumps([r.request_id for r in rows],separators=(",",":")),
            destinations_json=json.dumps(choices,separators=(",",":")),candidates_json=json.dumps(base,separators=(",",":")),
            objective=cost,runtime_ms=runtime,status=status))
        # Rows are put in their original arrival/ID order: same FIFO store
        # semantics. Convex costs admit this within-replica canonical optimum.
        for request,rid,age in zip(rows,choices,ages):
            selected=projected[rid];current=list(projected.values())
            counter=self.rr_counter;self.rr_counter+=1
            if e.assignment_locations.get(request.request_id)==rid:
                selected["queue_length"]+=1
                e.replica_stores[rid].put(request)
                continue
            e.assignment_locations[request.request_id]=rid
            no_queue=choose(current,s.deadline_ms,"joint_no_queue",age_ms=age)
            scored=estimate(selected,s.deadline_ms,age)
            least=min(current,key=lambda c:(c["network_ms"],c["id"]))["id"]
            e.routing_events.append(dict(request_id=request.request_id,service_id=self.sid,time_s=e.env.now,
                arrival_s=request.arrival_s,reason=reason,replica_id=rid,node=selected["node"],eligible_count=len(base),
                deadline_ms=s.deadline_ms,age_ms=age,rr_counter=counter,lowest_network_replica=least,no_queue_choice=no_queue,
                routed_away_from_lowest_network=selected["network_ms"]>min(c["network_ms"] for c in current)+1e-12,
                queue_changed_choice=rid!=no_queue,runtime_ms=runtime/len(rows),batch_size=len(rows),batch_objective=cost,
                **{k:v for k,v in scored.items() if k!="key"},candidates_json=json.dumps(current,separators=(",",":"))))
            selected["queue_length"]+=1
            self.waiting_for_eligible.discard(request.request_id)
            e.replica_stores[rid].put(request)
        e.routing_cpu_ms+=(process_time_ns()-cpu)/1e6


class MJOEngine(OptimizedMeasured):
    def __init__(self,config,workload,solver=None):
        self.solver=solver or Solver()
        self.routing_batches=[];self.assignment_locations={}
        super().__init__(config,workload,"joint_mjo")
        self.queues=[MJOQueues(self,s.service_id) for s in self.services]

    def run(self):
        self.prepare_timing()
        def optimize(c,snapshot):
            start=process_time_ns()
            try:return controller(c,snapshot,self.solver)
            finally:self.cpu_times[snapshot["slot"]]["policy_cpu_ms"]+=(process_time_ns()-start)/1e6
        prior=POLICIES.get(self.policy);POLICIES[self.policy]=optimize
        started=perf_counter();cpu=process_time_ns()
        try:result=Simulator.run(self)
        finally:
            if prior is None:del POLICIES[self.policy]
            else:POLICIES[self.policy]=prior
        result.update(routing=self.routing_events,routing_attempts=self.routing_attempts,deployment_audit=[],
                      control_snapshot_times=self.control_snapshot_times,replica_services=self.replica_services,solver=self.solver.events,
                      routing_batches=self.routing_batches)
        result["timing"]=dict(wall_clock_seconds=perf_counter()-started,simulation_cpu_seconds=(process_time_ns()-cpu)/1e9,
             routing_cpu_ms=self.routing_cpu_ms,eligible_replica_seconds=float(np.mean(self.eligible_samples))*self.config.slots*self.config.slot_seconds,
             eligible_slot_samples=self.eligible_samples,control_cpu_times=[dict(slot=s,**v) for s,v in sorted(self.cpu_times.items())])
        return result


class MJO(Observation,MJOEngine):
    pass
