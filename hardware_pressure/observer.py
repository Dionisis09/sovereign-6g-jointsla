"""Read-only snapshots after frozen instrumentation; no simulation events added."""
import numpy as np
from hardware_grounded.physics import HardwareBaseline,HardwareJoint

class Observation:
    def __init__(self,*args,**kwargs):
        self.pressure_services=[];self.pressure_nodes=[]
        super().__init__(*args,**kwargs)

    def snapshot(self):
        value=super().snapshot()
        if abs(self.env.now-self.slot*self.config.slot_seconds)<1e-8:
            c=self.config
            for s in self.services:
                rs=[r for r in self.replicas.values() if r.service_id==s.service_id]
                capacity=bool(np.any(np.all(self.reserved+s.reservation<=self.capacities+1e-9,axis=1)))
                eligible=len(rs)<c.max_replicas and self.slot-self.last_action[s.service_id]>=c.cooldown_slots
                self.pressure_services.append(dict(slot=self.slot,service_id=s.service_id,
                    waiting=len(self.queues[s.service_id].items),allocated=len(rs),
                    active=sum(r.ready and r.pending_target is None and not r.retiring for r in rs),
                    scaleout_capacity_feasible=capacity,scaleout_feasible=capacity and eligible))
            for n,node in enumerate(self.nodes):
                free=self.capacities[n]-self.reserved[n]
                self.pressure_nodes.append(dict(slot=self.slot,node=n,free_cpu_reservation=free[0],
                    free_vram_gib=free[1],free_bandwidth_mbps=free[2],
                    free_cpu_cores=node.cpu.level/10000,free_gpu_units=node.gpu.capacity-node.gpu.count,
                    gpu_queue=len(node.gpu.queue),active_replicas=sum(r.node==n and r.ready and r.pending_target is None and not r.retiring for r in self.replicas.values())))
        return value

    def run(self):
        result=super().run()
        result.update(pressure_services=self.pressure_services,pressure_nodes=self.pressure_nodes)
        return result

class ObservedBaseline(Observation,HardwareBaseline):pass
class ObservedJoint(Observation,HardwareJoint):pass
