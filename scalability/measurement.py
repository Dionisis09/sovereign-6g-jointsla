"""Timing-only adapters; delegate every scheduling decision to verified code."""
from collections import defaultdict
import ctypes
import os
import threading
from time import perf_counter,process_time_ns
import numpy as np
from dynamic_placement.simulator import Simulator
from dynamic_placement.policies import POLICIES,sla_aware
from joint_routing.simulator import RoutedSimulator
from joint_routing.controller import joint_actions


def rss_mib():
    """Current Windows process working set; Linux current RSS as fallback."""
    if os.name=="nt":
        class Counters(ctypes.Structure):
            _fields_=[("cb",ctypes.c_ulong),("faults",ctypes.c_ulong),
                      *[(name,ctypes.c_size_t) for name in ("peak_working","working","peak_paged","paged","peak_nonpaged","nonpaged","pagefile","peak_pagefile")]]
        kernel=ctypes.WinDLL("kernel32",use_last_error=True);psapi=ctypes.WinDLL("psapi",use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
        counter=Counters();counter.cb=ctypes.sizeof(counter)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counter),counter.cb): raise ctypes.WinError()
        return counter.working/1024**2
    with open("/proc/self/statm",encoding="ascii") as stream:
        return int(stream.read().split()[1])*os.sysconf("SC_PAGE_SIZE")/1024**2


class MemoryMonitor:
    """Sample process RSS every 100 ms; retain only scalar peak, no policy state."""
    def __enter__(self):
        self.peak=self.initial=rss_mib();self.stop=threading.Event()
        def sample():
            while not self.stop.wait(.1):self.peak=max(self.peak,rss_mib())
        self.thread=threading.Thread(target=sample,daemon=True);self.thread.start()
        return self
    def __exit__(self,*args):
        self.peak=max(self.peak,rss_mib());self.stop.set();self.thread.join()


class Timing:
    """Mixin around the original snapshot/apply/run; no state/decision changes."""
    def prepare_timing(self):
        self.cpu_times=defaultdict(lambda:dict(snapshot_cpu_ms=0.,policy_cpu_ms=0.,apply_cpu_ms=0.))
        self.outer_snapshot_times=[];self.routing_cpu_ms=0.;self.eligible_samples=[]

    def snapshot(self):
        control=abs(self.env.now-self.slot*self.config.slot_seconds)<1e-8
        start=process_time_ns();wall=perf_counter()
        value=super().snapshot()
        if control:
            self.cpu_times[self.slot]["snapshot_cpu_ms"]+=(process_time_ns()-start)/1e6
            self.outer_snapshot_times.append(dict(slot=self.slot,runtime_ms=(perf_counter()-wall)*1000))
        else:
            self.eligible_samples.append(sum(r["ready"] for rows in value["replicas"].values() for r in rows))
        return value

    def apply(self,action):
        start=process_time_ns();nested=self.routing_cpu_ms
        try:return super().apply(action)
        finally:self.cpu_times[self.slot]["apply_cpu_ms"]+=max(0.,(process_time_ns()-start)/1e6-(self.routing_cpu_ms-nested))

    def run(self):
        self.prepare_timing()
        routed=isinstance(self,RoutedSimulator)
        def controller(config,snapshot):
            start=process_time_ns()
            try:
                if not routed or self.routing_policy=="sla_shortest_queue":return sla_aware(config,snapshot)
                return joint_actions(config,snapshot,self.settings,self.deployment_audit)
            finally:self.cpu_times[snapshot["slot"]]["policy_cpu_ms"]+=(process_time_ns()-start)/1e6
        prior=POLICIES.get(self.policy);POLICIES[self.policy]=controller
        start=perf_counter();cpu=process_time_ns()
        try: result=Simulator.run(self)
        finally:
            if prior is None:del POLICIES[self.policy]
            else:POLICIES[self.policy]=prior
        result["timing"]=dict(wall_clock_seconds=perf_counter()-start,simulation_cpu_seconds=(process_time_ns()-cpu)/1e9,
               routing_cpu_ms=self.routing_cpu_ms,eligible_replica_seconds=float(np.mean(self.eligible_samples))*self.config.slots*self.config.slot_seconds,
               eligible_slot_samples=self.eligible_samples,
               control_cpu_times=[dict(slot=s,**v) for s,v in sorted(self.cpu_times.items())])
        if routed:
            for name,attribute in (("routing","routing_events"),("routing_attempts","routing_attempts"),
                                   ("deployment_audit","deployment_audit"),("control_snapshot_times","control_snapshot_times"),
                                   ("replica_services","replica_services")):
                result[name]=getattr(self,attribute)
        else:
            result.update(routing=[],routing_attempts=[],deployment_audit=[],control_snapshot_times=self.outer_snapshot_times,
                          replica_services={r.replica_id:r.service_id for r in self.replicas.values()})
        return result


class MeasuredBaseline(Timing,Simulator):
    pass


class MeasuredRouted(Timing,RoutedSimulator):
    def dispatch(self,request,queue,reason):
        start=process_time_ns()
        try:return super().dispatch(request,queue,reason)
        finally:self.routing_cpu_ms+=(process_time_ns()-start)/1e6


def normalized_metrics(metrics,config,timing,routing_count):
    """Explicit request, service, slot and residency denominators."""
    requests=metrics["total_requests"];horizon=config.slots*config.slot_seconds
    control=sum(sum(v[k] for k in ("snapshot_cpu_ms","policy_cpu_ms","apply_cpu_ms")) for v in timing["control_cpu_times"])
    total=control+timing["routing_cpu_ms"]
    wall=timing["wall_clock_seconds"]
    return dict(wall_clock_seconds=wall,wall_seconds_per_100k_requests=wall*100000/requests,
                simulation_cpu_seconds=timing["simulation_cpu_seconds"],control_only_cpu_ms=control,
                routing_cpu_ms=timing["routing_cpu_ms"],total_controller_cpu_ms=total,
                controller_cpu_ms_per_request=total/requests,
                routing_decisions=routing_count,routing_decisions_per_simulation_wall_second=routing_count/wall,
                routing_decisions_per_routing_cpu_second=routing_count*1000/timing["routing_cpu_ms"] if timing["routing_cpu_ms"]>0 else 0.,
                actions_per_1000_requests=metrics["total_actions"]*1000/requests,
                cold_starts_per_1000_requests=metrics["cold_starts"]*1000/requests,
                replicas_per_service=metrics["average_replicas"]/config.service_count,
                sla_violations_per_1000_requests=metrics["sla_breach_rate"]*1000,
                requests_processed_per_slot=metrics["completed_requests"]/config.slots,
                average_eligible_replicas=timing["eligible_replica_seconds"]/horizon,
                completed_requests_per_average_eligible_replica=metrics["completed_requests"]/(timing["eligible_replica_seconds"]/horizon),
                vram_reserved_gib_per_node=metrics["vram_gb_seconds"]/(horizon*config.node_count))
