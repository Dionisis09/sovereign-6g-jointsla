"""Exact snapshot/index optimization; all decisions and physical events are inherited.

Only immutable service/topology/config arithmetic persists across time. Dynamic
node-derived values are cached inside one synchronous snapshot and invalidated
in finally. Ordered indexes hold the same replica/store objects as the original
insertion-ordered dictionaries; queues, workers and candidate scoring are intact.
"""
from time import perf_counter_ns, process_time_ns
import numpy as np
from joint_routing.simulator import RoutedSimulator, ServiceQueues
from scalability.measurement import Timing


class IndexedServiceQueues(ServiceQueues):
    @property
    def items(self):
        e=self.engine
        rows=self.pending.copy()
        # Store IDs are never removed: the legacy aggregate includes retired
        # stores too, and retaining them preserves that observable precisely.
        for rid in e.service_store_ids[self.sid]:
            rows.extend(e.replica_stores[rid].items)
        return sorted(rows,key=lambda r:(r.arrival_s,r.request_id))


class OptimizedRoutedSimulator(RoutedSimulator):
    """Drop-in engine for the unchanged JointSLA controller and routing methods."""
    def __init__(self,config,workload,policy,settings=None):
        self.service_replicas=[{} for _ in workload.services]
        self.service_store_ids=[[] for _ in workload.services]
        self._nominal_instant=None
        super().__init__(config,workload,policy,settings)
        # Initial stores are created by RoutedSimulator after add_replica.
        for rid in self.replica_stores:
            self.service_store_ids[self.replica_services[rid]].append(rid)
        self.queues=[IndexedServiceQueues(self,s.service_id) for s in self.services]
        c=self.config
        self._compute=c.preprocess_ms+c.inference_ms+c.postprocess_ms
        self._cpu_work=c.preprocess_ms+c.postprocess_ms+c.gpu_stage_cpu_fraction*c.inference_ms
        self._variance=(c.work_sigma*self._compute)**2
        # Preserve the original scalar formulas and NumPy reduction order.
        self._static={}
        for service in self.services:
            fraction=(service.cpu_cores/self.capacities[:,0].sum()+service.gpu_vram_gb/self.capacities[:,1].sum())/2
            for node in range(len(self.nodes)):
                network=float(self.workload.scenario.network_latency_ms[service.ingress,node])+1000*service.payload_mbit/self.capacities[node,2]
                feasible=bool(np.all(service.reservation<=self.capacities[node]+1e-9) and self.workload.gpu_units[node]>=1)
                self._static[service.service_id,node]=(network,float(fraction),feasible)

    def add_replica(self,sid,node,warm=False):
        r=super().add_replica(sid,node,warm)
        self.service_replicas[sid][r.replica_id]=r
        if hasattr(self,"replica_stores"):
            self.service_store_ids[sid].append(r.replica_id)
        return r

    def worker(self,replica,warm):
        # No yields/events are introduced. Removal follows exactly the original
        # worker deletion, after it completes, at the same SimPy instant.
        try:
            yield from super().worker(replica,warm)
        finally:
            if replica.replica_id not in self.replicas:
                self.service_replicas[replica.service_id].pop(replica.replica_id,None)

    def _node_state(self,node):
        c=self.config
        cpu,gpu=np.clip(self.utilization[node],0,.98)
        resource=(self._cpu_work*cpu/(1-cpu)+c.inference_ms*gpu/(1-gpu)
                  +len(self.nodes[node].gpu.queue)*c.inference_ms/self.workload.gpu_units[node])
        feasible=bool(np.all(self.reserved[node]<=self.capacities[node]+1e-9))
        return float(resource),feasible

    def nominal(self,service,node):
        network,fraction,static_feasible=self._static[service.service_id,node]
        instant=self._nominal_instant
        if instant is None:
            resource,reserved_feasible=self._node_state(node)
        else:
            if node not in instant:instant[node]=self._node_state(node)
            resource,reserved_feasible=instant[node]
        return dict(id=-1,node=node,queue_length=0,busy=False,remaining_busy_ms=0.,
                    cycle_ms=network+self._compute+resource,cycle_variance_ms2=self._variance,
                    network_ms=network,compute_ms=self._compute,resource_wait_ms=resource,penalty_ms=0.,
                    available_in_ms=0.,resource_fraction=fraction,ready=True,pending=False,retiring=False,
                    capacity_feasible=bool(static_feasible and reserved_feasible))

    def candidates(self,sid):
        self.refresh_completed()
        service=self.services[sid]
        candidates=[]
        for rid,r in self.service_replicas[sid].items():
            if not r.ready or r.pending_target is not None or r.retiring:
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

    def snapshot(self):
        started=perf_counter_ns()
        assert self._nominal_instant is None,"snapshot cache must never escape its invocation"
        self._nominal_instant={}
        try:
            # Exactly the legacy observable fields, copies, ordering and formulas.
            replicas={s.service_id:[] for s in self.services}
            for r in self.replicas.values():
                if not r.retiring:
                    replicas[r.service_id].append(dict(id=r.replica_id,node=r.node,
                                    ready=r.ready and r.pending_target is None,busy=r.busy))
            waiting=[q.items for q in self.queues]
            snap=dict(slot=self.slot,services=self.services,capacities=self.capacities.copy(),
                      reserved=self.reserved.copy(),utilization=self.utilization.copy(),replicas=replicas,
                      rates=self.rates.copy(),latency_ms=self.recent_latency.copy(),last_action=self.last_action.copy(),
                      queue_lengths=np.array([len(rows) for rows in waiting]),
                      oldest_wait_ms=np.array([(self.env.now-rows[0].arrival_s)*1000 if rows else 0 for rows in waiting]),
                      network_ms=self.workload.scenario.network_latency_ms.copy())
            control_start=abs(self.env.now-self.slot*self.config.slot_seconds)<1e-8
            if control_start and hasattr(self,"replica_stores") and self.routing_policy.startswith("joint_"):
                snap["routing_candidates"]={s.service_id:self.candidates(s.service_id) for s in self.services}
                snap["nominal_candidates"]={s.service_id:[self.nominal(s,n) for n in range(len(self.nodes))] for s in self.services}
                snap["waiting_ages"]={s.service_id:[max(0.,(self.env.now-r.arrival_s)*1000) for r in waiting[s.service_id]] for s in self.services}
            if control_start:
                self.control_snapshot_times.append(dict(slot=self.slot,runtime_ms=(perf_counter_ns()-started)/1e6))
            return snap
        finally:
            self._nominal_instant=None


class OptimizedMeasured(Timing,OptimizedRoutedSimulator):
    """Same instrumentation scope as the verified MeasuredRouted engine."""
    def dispatch(self,request,queue,reason):
        start=process_time_ns()
        try:return super().dispatch(request,queue,reason)
        finally:self.routing_cpu_ms+=(process_time_ns()-start)/1e6
