"""Controller-injection adapter; delegates every physical event to old engine."""
from collections import deque
from time import perf_counter,process_time_ns
import numpy as np
from dynamic_placement.simulator import Simulator
from dynamic_placement.policies import POLICIES
from hardware_pressure.observer import ObservedJoint
from .policy import Parameters,headroom_rows,actions

class V2Simulator(ObservedJoint):
    def __init__(self,*args,parameters=Parameters(),**kwargs):
        self.parameters=parameters;self.headroom=[];self.arrival_history=deque();self.history_cursor=0
        super().__init__(*args,**kwargs)
        self.history_window=max(c.cold_start_slots for c in self.service_configs.values())

    def recent_rates(self):
        """Only fully completed observed slots; no workload.requests/traffic read."""
        while self.history_cursor<len(self.observed_history):
            self.arrival_history.append(self.observed_history[self.history_cursor]);self.history_cursor+=1
            if len(self.arrival_history)>self.history_window:self.arrival_history.popleft()
        if not self.arrival_history:return np.zeros(len(self.services)),0
        return np.sum(self.arrival_history,axis=0)/(len(self.arrival_history)*self.config.slot_seconds),len(self.arrival_history)

    def observed_slot_counts(self):
        """Invert unchanged EWMA update to recover completed-slot counts.

        rates_t=alpha*(counts/Δ)+(1−alpha)*rates_(t−1). This reads only
        controller telemetry and introduces no events or arrival-tape access.
        """
        if self.slot>0:
            counts=(self.rates-(1-self.config.ewma_alpha)*self.previous_rates)*self.config.slot_seconds/self.config.ewma_alpha
            assert np.allclose(counts,np.rint(counts),atol=1e-7) and (counts>=-1e-7).all()
            self.observed_history.append(np.rint(counts).astype(int))
        self.previous_rates=self.rates.copy()

    def run(self):
        """Same Timing adapter with only controller callback replaced by v2.

        Routing policy remains 'joint_sla', so candidates, score, tie breaking
        and request dispatch are inherited literally. No event-loop fork.
        """
        self.prepare_timing();self.observed_history=[];self.previous_rates=self.rates.copy()
        def controller(config,snapshot):
            start=process_time_ns()
            try:
                self.observed_slot_counts();rates,n=self.recent_rates()
                rows=headroom_rows(config,snapshot,self.service_configs,rates,n,self.parameters)
                decision=actions(config,snapshot,self.settings,self.deployment_audit,rows)
                self.headroom.extend(rows);return decision
            finally:self.cpu_times[snapshot['slot']]['policy_cpu_ms']+=(process_time_ns()-start)/1e6
        prior=POLICIES.get(self.policy);POLICIES[self.policy]=controller
        start=perf_counter();cpu=process_time_ns()
        try:result=Simulator.run(self)
        finally:
            if prior is None:del POLICIES[self.policy]
            else:POLICIES[self.policy]=prior
        result['timing']=dict(wall_clock_seconds=perf_counter()-start,simulation_cpu_seconds=(process_time_ns()-cpu)/1e9,
            routing_cpu_ms=self.routing_cpu_ms,eligible_replica_seconds=float(np.mean(self.eligible_samples))*self.config.slots*self.config.slot_seconds,
            eligible_slot_samples=self.eligible_samples,control_cpu_times=[dict(slot=s,**v) for s,v in sorted(self.cpu_times.items())])
        for name,attribute in (('routing','routing_events'),('routing_attempts','routing_attempts'),('deployment_audit','deployment_audit'),('control_snapshot_times','control_snapshot_times')):
            result[name]=getattr(self,attribute)
        result.update(replica_services=dict(self.hardware_replica_services),pressure_services=self.pressure_services,
            pressure_nodes=self.pressure_nodes,headroom=self.headroom)
        return result
