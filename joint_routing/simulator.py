"""Per-replica dispatch adapter around the unchanged baseline worker.

The base worker and source execute unchanged through a service queue facade.
Only queue selection and new policy snapshots are extended. No compute,
resource, lifecycle, arrival or request-outcome implementation is copied.
"""
import json
from time import perf_counter_ns
import numpy as np
import simpy
from dynamic_placement.simulator import Simulator
from dynamic_placement.policies import POLICIES, sla_aware
from .router import Settings, choose, estimate
from .controller import joint_actions


class ServiceQueues:
    """Aggregate waiting queue view plus replica-specific Store.get/put."""
    def __init__(self,engine,sid):
        self.engine,self.sid=engine,sid
        self.pending=[]
        self.rr_counter=0
        self.waiting_for_eligible=set()

    @property
    def items(self):
        e=self.engine
        rows=self.pending.copy()
        for rid,store in e.replica_stores.items():
            if e.replica_services[rid]==self.sid:
                rows.extend(store.items)
        return sorted(rows,key=lambda r:(r.arrival_s,r.request_id))

    def put(self,request):
        self.pending.append(request)
        self.waiting_for_eligible.add(request.request_id)
        self.flush("arrival")
        event=self.engine.env.event();event.succeed()
        return event

    def flush(self,reason):
        e=self.engine
        # Process each current request once; empty eligibility retains it.
        for request in self.pending.copy():
            if e.dispatch(request,self,reason):
                self.pending.remove(request)
                self.waiting_for_eligible.discard(request.request_id)

    def redistribute(self,reason):
        """Reassign waiting work only; never move an in-flight request."""
        e=self.engine
        rows=self.items
        self.pending.clear()
        for rid,store in e.replica_stores.items():
            if e.replica_services[rid]==self.sid:
                while store.items:
                    store.get()
        self.pending.extend(rows)
        self.flush(reason)

    def get(self):
        e=self.engine
        replica=e.process_replicas[e.env.active_process]
        e.inflight.pop(replica.replica_id,None)
        e.refresh_completed()
        key=(replica.replica_id,replica.node)
        if key not in e.activated:
            e.activated.add(key)
            self.redistribute("replica_ready")
        else:
            self.flush("eligible")
        event=e.replica_stores[replica.replica_id].get()
        def started(done):
            e.inflight[replica.replica_id]=(done.value,e.env.now)
        event.callbacks.append(started)
        return event


class RoutedSimulator(Simulator):
    """Original physical engine, explicit routing, and causal snapshot extension."""
    def __init__(self,config,workload,policy,settings=None):
        self.routing_policy=policy
        self.settings=settings or Settings()
        self.process_replicas={}
        self.inflight={}
        self.activated=set()
        self.cycle_history={}
        self.completed_cursor=0
        self.routing_events=[]
        self.routing_attempts=[]
        self.deployment_audit=[]
        self.control_snapshot_times=[]
        super().__init__(config,workload,"__joint_adapter__")
        self.replica_stores={rid:simpy.Store(self.env) for rid in self.replicas}
        self.replica_services={rid:r.service_id for rid,r in self.replicas.items()}
        self.queues=[ServiceQueues(self,s.service_id) for s in self.services]

    def add_replica(self,sid,node,warm=False):
        r=super().add_replica(sid,node,warm)
        if hasattr(self,"replica_stores"):
            self.replica_stores[r.replica_id]=simpy.Store(self.env)
            self.replica_services[r.replica_id]=sid
        return r

    def worker(self,replica,warm):
        self.process_replicas[self.env.active_process]=replica
        yield from super().worker(replica,warm)
        self.inflight.pop(replica.replica_id,None)

    def refresh_completed(self):
        for row in self.outcomes[self.completed_cursor:]:
            if row["unplaced"]:
                continue
            rid=row["replica_id"]
            cycle=row["latency_ms"]-row["service_queue_ms"]
            prior=self.cycle_history.get(rid)
            if prior is None or prior[2]!=row["node"]:
                self.cycle_history[rid]=(cycle,(self.config.work_sigma*14)**2,row["node"])
            else:
                mean,var,node=prior
                alpha=self.config.ewma_alpha
                delta=cycle-mean
                self.cycle_history[rid]=(mean+alpha*delta,(1-alpha)*(var+alpha*delta*delta),node)
        self.completed_cursor=len(self.outcomes)

    def nominal(self,service,node):
        c=self.config
        compute=c.preprocess_ms+c.inference_ms+c.postprocess_ms
        network=float(self.workload.scenario.network_latency_ms[service.ingress,node])+1000*service.payload_mbit/self.capacities[node,2]
        cpu,gpu=np.clip(self.utilization[node],0,.98)
        cpu_work=c.preprocess_ms+c.postprocess_ms+c.gpu_stage_cpu_fraction*c.inference_ms
        resource=(cpu_work*cpu/(1-cpu)+c.inference_ms*gpu/(1-gpu)
                  +len(self.nodes[node].gpu.queue)*c.inference_ms/self.workload.gpu_units[node])
        fraction=(service.cpu_cores/self.capacities[:,0].sum()+service.gpu_vram_gb/self.capacities[:,1].sum())/2
        return dict(id=-1,node=node,queue_length=0,busy=False,remaining_busy_ms=0.,
                    cycle_ms=network+compute+float(resource),cycle_variance_ms2=(c.work_sigma*compute)**2,
                    network_ms=network,compute_ms=compute,resource_wait_ms=float(resource),penalty_ms=0.,
                    available_in_ms=0.,resource_fraction=float(fraction),ready=True,pending=False,retiring=False,
                    capacity_feasible=bool(np.all(service.reservation<=self.capacities[node]+1e-9)
                                           and np.all(self.reserved[node]<=self.capacities[node]+1e-9)
                                           and self.workload.gpu_units[node]>=1))

    def candidates(self,sid):
        self.refresh_completed()
        service=self.services[sid]
        candidates=[]
        for rid,r in self.replicas.items():
            if r.service_id!=sid or not r.ready or r.pending_target is not None or r.retiring:
                continue
            candidate=self.nominal(service,r.node)
            if not candidate["capacity_feasible"]:
                continue
            cycle,var,node=self.cycle_history.get(rid,(candidate["cycle_ms"],candidate["cycle_variance_ms2"],r.node))
            if node!=r.node:
                cycle,var=candidate["cycle_ms"],candidate["cycle_variance_ms2"]
            busy=rid in self.inflight
            elapsed=(self.env.now-self.inflight[rid][1])*1000 if busy else 0.
            candidate.update(id=rid,queue_length=len(self.replica_stores[rid].items),busy=busy,
                             remaining_busy_ms=max(0.,cycle-elapsed) if busy else 0.,
                             cycle_ms=cycle,cycle_variance_ms2=max(var,1e-12),penalty_ms=r.penalty_ms)
            candidates.append(candidate)
        return candidates

    def dispatch(self,request,queue,reason):
        started=perf_counter_ns()
        candidates=self.candidates(request.service_id)
        deadline=self.services[request.service_id].deadline_ms
        age=max(0.,(self.env.now-request.arrival_s)*1000)
        rid=choose(candidates,deadline,self.routing_policy,queue.rr_counter,age)
        if rid is None:
            self.routing_attempts.append(dict(request_id=request.request_id,time_s=self.env.now,
                                             success=False,runtime_ms=(perf_counter_ns()-started)/1e6))
            return False
        counter=queue.rr_counter
        queue.rr_counter+=1
        selected=next(c for c in candidates if c["id"]==rid)
        lowest=min(candidates,key=lambda c:(c["network_ms"],c["id"]))["id"]
        no_queue=choose(candidates,deadline,"joint_no_queue",age_ms=age)
        scored=estimate(selected,deadline,age,no_queue=self.routing_policy=="joint_no_queue",no_slack=self.routing_policy=="joint_no_slack")
        # Time excludes serialization and audit formatting, includes estimation,
        # selection and the two observational counterfactual selections.
        runtime=(perf_counter_ns()-started)/1e6
        self.routing_attempts.append(dict(request_id=request.request_id,time_s=self.env.now,success=True,runtime_ms=runtime))
        self.routing_events.append(dict(request_id=request.request_id,service_id=request.service_id,time_s=self.env.now,
             arrival_s=request.arrival_s,reason=reason,replica_id=rid,node=selected["node"],eligible_count=len(candidates),
             deadline_ms=deadline,age_ms=age,rr_counter=counter,lowest_network_replica=lowest,
             no_queue_choice=no_queue,routed_away_from_lowest_network=selected["network_ms"]>min(c["network_ms"] for c in candidates)+1e-12,queue_changed_choice=rid!=no_queue,
             runtime_ms=runtime,**{k:v for k,v in scored.items() if k!="key"},
             candidates_json=json.dumps(candidates,separators=(",",":"))))
        self.replica_stores[rid].put(request)
        return True

    def apply(self,action):
        accepted=super().apply(action)
        if accepted and action.kind=="migrate":
            self.queues[action.service_id].redistribute("migration_reallocation")
        return accepted

    def snapshot(self):
        started=perf_counter_ns()
        snap=super().snapshot()
        control_start=abs(self.env.now-self.slot*self.config.slot_seconds)<1e-8
        if control_start and hasattr(self,"replica_stores") and self.routing_policy.startswith("joint_"):
            snap["routing_candidates"]={s.service_id:self.candidates(s.service_id) for s in self.services}
            snap["nominal_candidates"]={s.service_id:[self.nominal(s,n) for n in range(len(self.nodes))] for s in self.services}
            snap["waiting_ages"]={s.service_id:[max(0.,(self.env.now-r.arrival_s)*1000) for r in self.queues[s.service_id].items] for s in self.services}
        if control_start:
            self.control_snapshot_times.append(dict(slot=self.slot,runtime_ms=(perf_counter_ns()-started)/1e6))
        return snap

    def run(self):
        def controller(config,snapshot):
            if self.routing_policy in ("sla_rr","sla_shortest_queue"):
                return sla_aware(config,snapshot)
            return joint_actions(config,snapshot,self.settings,self.deployment_audit)
        prior=POLICIES.get(self.policy)
        POLICIES[self.policy]=controller
        try:
            result=super().run()
        finally:
            if prior is None:
                del POLICIES[self.policy]
            else:
                POLICIES[self.policy]=prior
        result["routing"]=self.routing_events
        result["routing_attempts"]=self.routing_attempts
        result["deployment_audit"]=self.deployment_audit
        result["replica_services"]=self.replica_services
        result["control_snapshot_times"]=self.control_snapshot_times
        return result
