"""Delegate the original physical worker with a per-service configuration view.

No event-loop/worker implementation is copied. The frozen global controller and
nominal estimator are inherited unchanged. Heterogeneity affects execution only.
"""
from dynamic_placement.simulator import Simulator
from joint_routing.simulator import RoutedSimulator
from scalability.measurement import MeasuredBaseline
from controller_optimization.optimized import OptimizedMeasured


class ConfigView:
    """Only config differs; every other read or mutation reaches the real engine."""
    def __init__(self,engine,config):
        object.__setattr__(self,'engine',engine);object.__setattr__(self,'config',config)
    def __getattr__(self,name):return getattr(self.engine,name)
    def __setattr__(self,name,value):setattr(self.engine,name,value)


class ProfilePhysics:
    def __init__(self,config,workload,policy,service_configs,settings=None):
        self.service_configs=service_configs;self.hardware_replica_services={}
        if isinstance(self,RoutedSimulator):super().__init__(config,workload,policy,settings)
        else:super().__init__(config,workload,policy)

    def add_replica(self,sid,node,warm=False):
        replica=super().add_replica(sid,node,warm)
        self.hardware_replica_services[replica.replica_id]=sid
        return replica

    def worker(self,replica,warm):
        routed=isinstance(self,RoutedSimulator)
        if routed:self.process_replicas[self.env.active_process]=replica
        try:
            yield from Simulator.worker(ConfigView(self,self.service_configs[replica.service_id]),replica,warm)
        finally:
            if routed:
                self.inflight.pop(replica.replica_id,None)
                if replica.replica_id not in self.replicas:self.service_replicas[replica.service_id].pop(replica.replica_id,None)

    def run(self):
        result=super().run()
        result['replica_services']=dict(self.hardware_replica_services)
        return result


class HardwareBaseline(ProfilePhysics,MeasuredBaseline):pass
class HardwareJoint(ProfilePhysics,OptimizedMeasured):pass
