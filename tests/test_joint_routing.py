"""Routing eligibility, causal scores, queue facade and unchanged physical worker."""
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from catalyst.reused import digest
from dynamic_placement.config import Config
from dynamic_placement.workload import Request, generate_workload
from dynamic_placement.policies import Action, POLICIES
from dynamic_placement.metrics import validate_run
from joint_routing.router import choose, estimate, NEW_POLICIES
from joint_routing.simulator import RoutedSimulator


def candidate(rid,q=0,busy=False,net=5,var=4):
    return dict(id=rid,node=rid,queue_length=q,busy=busy,remaining_busy_ms=10 if busy else 0,
                cycle_ms=20,cycle_variance_ms2=var,network_ms=net,compute_ms=14,resource_wait_ms=1,
                penalty_ms=0,resource_fraction=.1,available_in_ms=0)


@pytest.fixture
def tiny():
    c=Config(slots=8)
    w=generate_workload(c,0)
    initial={s.service_id:None for s in w.services};initial[0]=0
    requests=tuple(Request(i,0,.01+i*.003,int((.01+i*.003)/.1),1.,w.services[0].payload_mbit) for i in range(40))
    traffic=tuple(dict(service_id=s.service_id,slot=t,burst=False,expected_rate_rps=s.base_rate_rps,
                       arrivals=sum(r.arrival_slot==t for r in requests) if s.service_id==0 else 0)
                  for s in w.services for t in range(c.slots))
    return c,replace(w,requests=requests,initial=initial,traffic=traffic)


def test_round_robin_and_shortest_queue():
    cs=[candidate(4,q=2),candidate(1,q=1),candidate(3,q=0,busy=True)]
    assert [choose(cs,50,"sla_rr",i) for i in range(6)]==[1,3,4,1,3,4]
    assert choose(cs,50,"sla_shortest_queue")==1  # waiting + in-flight tie; lower ID
    assert choose([candidate(1,q=3),candidate(4,q=0)],50,"sla_shortest_queue")==4


def test_score_components_and_deterministic_ties():
    c=candidate(2,q=2,busy=True)
    e=estimate(c,100,age_ms=5)
    assert e["estimated_queue_wait_ms"]==50
    assert e["estimated_completion_ms"]==75
    assert e["slack_ms"]==25
    assert e["estimated_variance_ms2"]==16
    assert e["risk_proxy"]==pytest.approx(16/(16+625))
    assert choose([candidate(3),candidate(1)],100,"joint_sla")==1
    assert choose([],100,"joint_sla") is None
    assert choose([candidate(9)],100,"joint_sla")==9


def test_slack_proxy_is_not_redundant_when_variance_differs():
    a,b=candidate(1,net=5,var=100),candidate(2,net=10,var=1)
    assert choose([a,b],100,"joint_sla")==2
    assert choose([a,b],100,"joint_no_slack")==1
    assert choose([candidate(1,q=10),candidate(2,net=10)],100,"joint_sla")==2
    assert choose([candidate(1,q=10),candidate(2,net=10)],100,"joint_no_queue")==1


def test_cold_and_migrating_and_retiring_replicas_excluded(tiny):
    c,w=tiny
    e=RoutedSimulator(c,w,"joint_sla")
    assert len(e.candidates(0))==1
    new=e.add_replica(0,1)
    assert new.replica_id not in [r["id"] for r in e.candidates(0)]
    warm=e.replicas[0];warm.pending_target=1
    assert not e.candidates(0)
    warm.pending_target=None;warm.retiring=True
    assert not e.candidates(0)


def test_resident_capacity_infeasibility_excluded(tiny):
    c,w=tiny
    e=RoutedSimulator(c,w,"joint_sla")
    e.reserved[0,1]=e.capacities[0,1]+1
    assert e.candidates(0)==[]


@pytest.mark.parametrize("policy",NEW_POLICIES)
def test_no_lost_or_duplicated_requests_and_hashes(tiny,policy):
    c,w=tiny
    frozen=digest(w.to_dict());registry=POLICIES.copy()
    result=RoutedSimulator(c,w,policy).run()
    validate_run(c,w,result)
    assert digest(w.to_dict())==frozen and POLICIES==registry
    assert len({r["request_id"] for r in result["outcomes"]})==len(w.requests)
    assert all(r["eligible_count"]>0 and all(c["ready"] and not c["pending"] and not c["retiring"] and c["capacity_feasible"] for c in __import__('json').loads(r["candidates_json"])) for r in result["routing"])


def test_pending_requests_wait_for_cold_start_without_drop(tiny):
    c,w=tiny
    e=RoutedSimulator(c,w,"sla_rr")
    warm=e.replicas[0]
    warm.ready=False
    request=w.requests[0]
    e.queues[0].put(request)
    assert e.queues[0].pending==[request] and not e.routing_events
    warm.ready=True
    e.queues[0].flush("test_ready")
    assert not e.queues[0].pending and e.routing_events[0]["request_id"]==request.request_id


def test_migration_adapter_preserves_inflight_and_waiting_work(tiny,monkeypatch):
    c,w=tiny
    import joint_routing.simulator as module
    def forced(config,snapshot):
        return [Action("migrate",0,1,0)] if snapshot["slot"]==1 else []
    monkeypatch.setattr(module,"sla_aware",forced)
    result=RoutedSimulator(c,w,"sla_rr").run()
    validate_run(c,w,result)
    assert len(result["outcomes"])==40
    assert any(r["kind"]=="migration_downtime" for r in result["lifecycle"])
    down=next(r for r in result["lifecycle"] if r["kind"]=="migration_downtime")
    assert not any(down["start_s"]<=r["time_s"]<down["ready_s"]-1e-12 for r in result["routing"])


def test_hidden_request_work_cannot_change_routing(tiny):
    c,w=tiny
    e=RoutedSimulator(c,w,"joint_sla")
    a=w.requests[0]
    e.dispatch(a,e.queues[0],"test")
    first=e.routing_events[-1]["replica_id"]
    other=RoutedSimulator(c,w,"joint_sla")
    other.dispatch(replace(a,work_factor=1000),other.queues[0],"test")
    assert other.routing_events[-1]["replica_id"]==first
    assert other.routing_events[-1]["estimated_completion_ms"]==e.routing_events[-1]["estimated_completion_ms"]


def test_future_tape_changes_do_not_change_past_routing(tiny):
    c,w=tiny
    future=Request(40,0,.7,7,1000.,w.services[0].payload_mbit)
    w2=replace(w,requests=w.requests+(future,),traffic=tuple({**t,"burst":True} if t["slot"]>=7 else t for t in w.traffic))
    for policy in NEW_POLICIES:
        a=RoutedSimulator(c,w,policy).run()
        b=RoutedSimulator(c,w2,policy).run()
        def prefix(result):
            return [{k:v for k,v in row.items() if k!="runtime_ms"} for row in result["routing"] if row["time_s"]<.7]
        assert prefix(a)==prefix(b)
