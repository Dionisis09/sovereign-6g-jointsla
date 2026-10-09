"""Pure runtime decisions reusing the frozen routing and warm-headroom functions."""
from dataclasses import dataclass
from joint_routing.router import choose
from joint_sla_v2.policy import required_warm

@dataclass(frozen=True)
class Decision:
    desired_replicas: int
    ready_replicas: int
    queue: int
    reason: str

def plan(states, rate_rps, deadline_ms=200., cold_seconds=10., max_replicas=4, tier='Gold'):
    queue=sum(s['queue']+int(s['busy']) for s in states)
    cycles=[s['cycle_ms']/1000 for s in states if s['ready']]
    if not cycles: return Decision(1,0,queue,'No ready backend; restore one replica')
    target=required_warm(queue,rate_rps,cold_seconds,min(cycles),deadline_ms/1000,tier,max_replicas)
    return Decision(target,len(cycles),queue,'Observed queue/rate and JointSLA-v2 warm-headroom rule')

def route(states, deadline_ms):
    candidates=[]
    for sid,state in enumerate(states):
        if not state['ready']: continue
        cycle=state['cycle_ms']
        candidates.append(dict(id=sid,queue_length=state['queue'],remaining_busy_ms=cycle if state['busy'] else 0.,
            cycle_ms=cycle,compute_ms=cycle,network_ms=0.,resource_wait_ms=0.,penalty_ms=0.,
            cycle_variance_ms2=state['variance_ms2'],busy=state['busy']))
    return choose(candidates,deadline_ms,'joint_sla')
