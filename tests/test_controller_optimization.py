"""Differential correctness tests: no tolerance for scientific state or outcomes."""
from dataclasses import replace
import numpy as np
import pytest
from catalyst.reused import digest
from dynamic_placement.workload import generate_workload
from dynamic_placement.metrics import validate_run
from dynamic_placement.policies import Action
from joint_routing.simulator import RoutedSimulator
from joint_routing.router import choose,estimate
from scalability.configuration import SCALES,configuration
from controller_optimization.reference import GoldenLegacy,Capture,plain,traces
from controller_optimization.optimized import OptimizedRoutedSimulator,OptimizedMeasured


def pair(scale="SMALL"):
    c=configuration(scale);w=generate_workload(c,1)
    return RoutedSimulator(c,w,"joint_sla"),OptimizedRoutedSimulator(c,w,"joint_sla")


def snapshot_equal(a,b):
    assert plain(a.snapshot())==plain(b.snapshot())
    assert b._nominal_instant is None


@pytest.mark.parametrize("scale",SCALES)
def test_static_metadata_nominal_and_candidate_inputs_exact(scale):
    a,b=pair(scale);rng=np.random.default_rng(871)
    for iteration in range(3):
        utilization=rng.uniform(0,1.1,a.utilization.shape)
        a.utilization[:]=b.utilization[:]=utilization
        for s in a.services:
            for node in range(len(a.nodes)):
                assert a.nominal(s,node)==b.nominal(s,node)
            before,after=a.candidates(s.service_id),b.candidates(s.service_id)
            assert before==after
            for x,y in zip(before,after):assert estimate(x,s.deadline_ms)==estimate(y,s.deadline_ms)
        snapshot_equal(a,b)


def test_snapshot_copies_and_dynamic_cache_invalidation():
    a,b=pair();snapshot_equal(a,b)
    s=b.snapshot();s["reserved"][:]=999;s["rates"][:]=999;s["replicas"][0].clear()
    snapshot_equal(a,b)
    a.utilization[0]=b.utilization[0]=[.91,.93]
    a.reserved[0,0]=b.reserved[0,0]=a.capacities[0,0]+2
    snapshot_equal(a,b)
    assert a.nominal(a.services[0],0)==b.nominal(b.services[0],0)
    assert not b.nominal(b.services[0],0)["capacity_feasible"]


def test_within_snapshot_node_state_computed_once_and_cache_cleared(monkeypatch):
    _,b=pair("LARGE");calls=[];original=b._node_state
    def record(node):calls.append(node);return original(node)
    monkeypatch.setattr(b,"_node_state",record)
    b.snapshot();assert calls==list(dict.fromkeys(calls)) and set(calls)==set(range(20))
    assert b._nominal_instant is None
    calls.clear();b.snapshot();assert len(calls)==20
    def fail(node):raise RuntimeError("diagnostic failure")
    monkeypatch.setattr(b,"_node_state",fail)
    with pytest.raises(RuntimeError):b.snapshot()
    assert b._nominal_instant is None


def feasible_target(engine,sid,source=None):
    for n in range(len(engine.nodes)):
        if n!=source and np.all(engine.reserved[n]+engine.services[sid].reservation<=engine.capacities[n]+1e-9):return n
    return None


def test_replica_add_remove_indexes_and_historical_store_membership():
    a,b=pair()
    sid,target=next((s.service_id,n) for s in a.services if (n:=feasible_target(a,s.service_id)) is not None)
    ra=a.add_replica(sid,target,warm=True);rb=b.add_replica(sid,target,warm=True)
    assert ra.replica_id==rb.replica_id
    assert list(b.service_replicas[sid])==[r.replica_id for r in b.replicas.values() if r.service_id==sid]
    snapshot_equal(a,b)
    ra.retiring=rb.retiring=True
    a.env.run(until=.001);b.env.run(until=.001)
    assert rb.replica_id not in b.service_replicas[sid]
    assert rb.replica_id in b.service_store_ids[sid] and rb.replica_id in b.replica_stores
    snapshot_equal(a,b)
    assert a.candidates(sid)==b.candidates(sid)


def test_queue_changes_pending_and_retired_stores_keep_original_sorted_order():
    a,b=pair();sid=a.workload.requests[0].service_id
    requests=[r for r in a.workload.requests if r.service_id==sid][:4]
    rid=next(r.replica_id for r in a.replicas.values() if r.service_id==sid)
    for e in (a,b):
        e.queues[sid].pending.extend(reversed(requests[:2]))
        e.replica_stores[rid].items.extend(reversed(requests[2:]))
    assert a.queues[sid].items==b.queues[sid].items==requests
    snapshot_equal(a,b)
    for e in (a,b):e.queues[sid].pending.pop();e.replica_stores[rid].items.pop()
    snapshot_equal(a,b)


def test_migration_pending_downtime_and_activation_state_exact():
    a,b=pair()
    r,target=next((r,n) for r in a.replicas.values() if (n:=feasible_target(a,r.service_id,r.node)) is not None)
    action=Action("migrate",r.service_id,target,r.replica_id,.7)
    assert a.apply(action)==b.apply(action)==True
    snapshot_equal(a,b);assert a.candidates(r.service_id)==b.candidates(r.service_id)
    for until in (.05,.15):
        a.env.run(until=until);b.env.run(until=until)
        snapshot_equal(a,b);assert a.candidates(r.service_id)==b.candidates(r.service_id)
    assert list(b.service_replicas[r.service_id])==[r.replica_id for r in b.replicas.values() if r.service_id==action.service_id]
    assert a.actions==b.actions and a.lifecycle_events==b.lifecycle_events and a.reservation_events==b.reservation_events


def test_candidate_set_order_and_tie_breaking_unchanged():
    a,b=pair()
    sid,target=next((s.service_id,n) for s in a.services if (n:=feasible_target(a,s.service_id)) is not None)
    a.add_replica(sid,target,warm=True);b.add_replica(sid,target,warm=True)
    x,y=a.candidates(sid),b.candidates(sid);assert x==y
    assert [c["id"] for c in y]==sorted(c["id"] for c in y)
    # The original scorer/chooser functions are reused directly.
    for policy in ("joint_sla","joint_no_slack","joint_no_queue","sla_rr","sla_shortest_queue"):
        assert choose(x,100,policy)==choose(y,100,policy)
    tied=[{**y[0],"id":8},{**y[0],"id":2}]
    assert choose(tied,100,"joint_sla")==2
    assert OptimizedRoutedSimulator.dispatch is RoutedSimulator.dispatch


@pytest.mark.parametrize("scale",SCALES)
@pytest.mark.parametrize("seed",(1,12,22))
def test_full_observables_actions_routing_event_and_outcome_order_exact(scale,seed):
    c=replace(configuration(scale),slots=4);w=generate_workload(c,seed);fingerprint=digest(w.to_dict())
    a=GoldenLegacy(c,w,"joint_sla")
    klass=type("CapturedOptimized",(Capture,OptimizedMeasured),{})
    b=klass(c,w,"joint_sla");b.captured_snapshots=[]
    x=a.run();y=b.run();validate_run(c,w,y)
    assert traces(x,a.captured_snapshots)==traces(y,b.captured_snapshots)
    assert digest(w.to_dict())==fingerprint


@pytest.mark.parametrize("scale",SCALES)
def test_optimized_future_traffic_still_cannot_change_prefix(scale):
    c=replace(configuration(scale),slots=4);w=generate_workload(c,3)
    future=replace(w,requests=tuple(replace(r,work_factor=900) if r.arrival_s>=.2 else r for r in w.requests))
    def prefix(workload):
        rows=OptimizedMeasured(c,workload,"joint_sla").run()["routing"]
        return [{k:v for k,v in r.items() if k!="runtime_ms"} for r in rows if r["time_s"]<.2]
    assert prefix(w)==prefix(future)


def test_csv_default_parser_difference_reproduces_exactly_without_tolerance():
    import pandas as pd
    from io import StringIO
    value=1089.8791033297935
    decimal=pd.DataFrame({"value":[value]}).to_csv(index=False)
    assert pd.read_csv(StringIO(decimal),float_precision="round_trip").value.iloc[0]==value
    parsed=pd.read_csv(StringIO(decimal)).value.iloc[0]
    assert parsed==1089.8791033297937 and parsed!=value
