"""Determinism, constrained action selection and causal physical accounting."""
from dataclasses import replace,asdict
import itertools
import numpy as np
import pytest
from dynamic_placement.workload import generate_workload
from dynamic_placement.metrics import validate_run
from dynamic_placement.policies import Action
from scalability.configuration import configuration,SCALES
from strong_baseline.optimization import Solver,Weights
from strong_baseline.simulator import MJO
from catalyst.reused import digest


def stripped(result):
    return dict(outcomes=result["outcomes"],actions=result["actions"],nodes=result["nodes"],
        routing=[{k:v for k,v in r.items() if k!="runtime_ms"} for r in result["routing"]])


@pytest.mark.parametrize("scale",SCALES)
def test_deterministic_accounting_capacity_lifecycle_and_fixed_inputs(scale):
    c=replace(configuration(scale),slots=3);w=generate_workload(c,1);fingerprint=digest(w.to_dict())
    a=MJO(c,w).run();b=MJO(c,w).run()
    assert stripped(a)==stripped(b);validate_run(c,w,a)
    assert digest(w.to_dict())==fingerprint
    assert len(a["outcomes"])==len(w.requests)==len({r["request_id"] for r in a["outcomes"]})
    assert max(sum(x["slot"]==slot for x in a["actions"]) for slot in range(c.slots))<=2
    assert a["diagnostics"]["rejected_actions"]==0


@pytest.mark.parametrize("scale",SCALES)
def test_no_future_work_or_traffic_leak(scale):
    c=replace(configuration(scale),slots=4);w=generate_workload(c,4)
    future=replace(w,requests=tuple(replace(r,work_factor=1000,arrival_s=.2+(r.arrival_s-.2)*.5) if r.arrival_s>=.2 else r for r in w.requests),
                   traffic=tuple({**r,"burst":True,"expected_rate_rps":9999} if r["slot"]>=2 else r for r in w.traffic))
    def prefix(work):
        result=MJO(c,work).run()
        return ([{k:v for k,v in r.items() if k!="runtime_ms"} for r in result["routing"] if r["time_s"]<.2],
                [r for r in result["actions"] if r["time_s"]<.2])
    assert prefix(w)==prefix(future)


def candidate(rid,cycle):
    return dict(id=rid,queue_length=0,cycle_ms=cycle,remaining_busy_ms=0.,network_ms=2.,compute_ms=14.,
                resource_wait_ms=0.,penalty_ms=0.,available_in_ms=0.)


def test_assignment_global_optimal_cost_and_one_destination():
    solver=Solver();c=[candidate(4,15),candidate(9,25)];ages=[40.,15.,0.]
    ids,value,status=solver.assignment(c,ages,40,3)
    assert status=="optimal" and len(ids)==3 and set(ids)<=set((4,9))
    # Independently enumerate the FIFO-compatible assignment schedules.
    weights=Weights();values=[]
    for destinations in itertools.product((0,1),repeat=3):
        count=[0,0];total=0.
        for age,idx in zip(ages,destinations):
            q=count[idx]*c[idx]["cycle_ms"];n=(age+q+16)/40
            total+=3*(max(0,n-1)+n)+.25*q/40;count[idx]+=1
        values.append(total)
    assert abs(value-min(values))<1e-12
    assert solver.assignment(c,ages,40,3)[:2]==(ids,value)


def options():
    return [dict(action=Action("scale_up",i,i%2),delta=-float(i+1),increment=np.eye(2)[i%2][:,None],key=(i,)) for i in range(5)]


def test_exact_budget_two_selection_matches_exhaustive_feasible_program():
    opts=options();room=np.ones((2,1));chosen,status=Solver().select(opts,room)
    feasible=[0.]
    for size in (1,2):
        for subset in itertools.combinations(opts,size):
            if np.all(sum(o["increment"] for o in subset)<=room):feasible.append(sum(o["delta"] for o in subset))
    value=sum(o["delta"] for o in opts if o["action"] in chosen)
    assert status=="optimal" and value==min(feasible) and len(chosen)<=2


def test_timeout_and_infeasible_fallback_is_noop_never_joint():
    actions,status=Solver(replace(Weights(),pair_limit=0)).select(options(),np.ones((2,1)))
    assert actions==[] and status=="timeout"
    bad=options();bad[0]["delta"]=float("nan")
    solver=Solver();actions,status=solver.select(bad,np.ones((2,1)))
    assert actions==[] and status=="infeasible" and solver.events[-1]["fallback"]
    assert solver.assignment([], [1.],40,1)[2]=="infeasible"


def test_same_service_competition_and_joint_capacity_constraints():
    opts=options();opts[4]["action"]=Action("scale_up",3,0)
    chosen,status=Solver().select(opts,np.ones((2,1)))
    assert status=="optimal" and len({a.service_id for a in chosen})==len(chosen)
    assert all(a.kind=="scale_up" for a in chosen)


def test_fixed_weights_frozen_and_large_block_decomposition():
    w=Weights();assert asdict(w)==asdict(Solver().weights)
    with pytest.raises(Exception):w.sla=9
    c=[candidate(1,10),candidate(2,20)]
    x,cost,status=Solver().assignment(c,[0.]*130,80,2)
    assert len(x)==130 and np.isfinite(cost) and status=="optimal"
