"""Engineering checks; simulation fixtures exclusively development seed 101."""
from dataclasses import replace,asdict
import json
from collections import deque
import numpy as np
import pytest
from hardware_pressure.design import regime_inputs
from hardware_pressure.observer import ObservedJoint
from hardware_grounded.audit import validate_run
from hardware_grounded.integrity import sha
from hardware_grounded.environment import ROOT
from joint_sla_v2.policy import Parameters,required_warm,headroom_rows,actions
from joint_sla_v2.simulator import V2Simulator
from joint_sla_v2.protocol import seed_gate,verify_freeze,SEEDS
from dynamic_placement.policies import Action,POLICIES
from controller_optimization.reference import semantic_rows

@pytest.mark.parametrize('tier,floor',[('Gold',2),('Silver',1),('Bronze',1)])
def test_floor_and_units(tier,floor):
    assert required_warm(0,0,.5,.01,.1,tier)==floor
    expected=min(3,max(floor,int(np.ceil({'Gold':1.5,'Silver':np.sqrt(1.5),'Bronze':1}[tier]*max(2*.01/.09,(2+30*.5)*.01/.59)))))
    assert required_warm(2,30,.5,.01,.1,tier)==expected

@pytest.mark.parametrize('tier',['Gold','Silver','Bronze'])
def test_monotone_bounded(tier):
    values=[required_warm(0,200,r,.01,.05,tier) for r in (.1,.2,.5,1)]
    assert values==sorted(values) and all(1<=v<=3 for v in values)
    assert required_warm(1000,10000,.5,.01,.1,tier)==3
    assert required_warm(1,1,.5,.1,.05,tier)==3
    assert required_warm(0,0,.5,float('inf'),.1,tier)==3

@pytest.mark.parametrize('values',[(-1,1,.1,.01,.1),(1,-1,.1,.01,.1),(1,1,0,.01,.1),(1,1,.1,.01,0)])
def test_invalid_units(values):
    with pytest.raises(ValueError):required_warm(*values,'Gold')

def test_parameters_fixed():
    assert asdict(Parameters())==dict(gold_multiplier=1.5,gold_floor=2,base_headroom=1.)
    with pytest.raises(Exception):Parameters().gold_floor=9

@pytest.fixture(scope='module')
def runs():
    c,w,cs=regime_inputs('D7',101)
    # Short event horizon remains original workload shape for physical checks.
    c=replace(c,slots=8);cs={s:replace(v,slots=8) for s,v in cs.items()}
    w=replace(w,requests=[r for r in w.requests if r.arrival_slot<8],traffic=[r for r in w.traffic if r['slot']<8])
    values=[]
    for _ in range(2):
        engine=V2Simulator(c,w,'joint_sla',cs);result=engine.run();values.append((engine,result))
    return c,w,cs,values

def test_deterministic_results_and_routing(runs):
    c,w,cs,values=runs;a,b=[v[1] for v in values]
    for name in ('outcomes','actions','reservations','lifecycle','routing','deployment_audit','headroom'):
        assert semantic_rows(a[name])==semantic_rows(b[name])
    assert values[0][0].routing_policy=='joint_sla'
    assert V2Simulator.dispatch is ObservedJoint.dispatch
    assert V2Simulator.worker is ObservedJoint.worker
    assert V2Simulator.source is ObservedJoint.source
    assert V2Simulator.decisions is ObservedJoint.decisions

def test_accounting_and_capacity(runs):
    c,w,cs,values=runs
    for e,r in values:
        check=validate_run(c,w,r,cs)
        assert check['requests_verified']==len(w.requests)
        assert len({a['request_id'] for a in r['outcomes']})==len(w.requests)
        assert all(a['accepted_actions']<=2 for a in r['slots'])
        assert not any(a['unplaced'] for a in r['outcomes'])

def test_history_matches_observed_counts(runs):
    c,w,cs,values=runs;e,r=values[0]
    assert e.history_window==max(v.cold_start_slots for v in cs.values())==5
    for slot in range(c.slots):
        rows=[a for a in r['headroom'] if a['slot']==slot]
        for row in rows:
            actual=sum(a.service_id==row['service_id'] and max(0,slot-5)<=a.arrival_slot<slot for a in w.requests)
            assert row['observed_history_slots']==min(slot,5)
            assert np.isclose(row['recent_rate_rps'],actual/(min(slot,5)*c.slot_seconds) if slot else 0)
    assert len(e.arrival_history)==5

def test_future_tape_not_controller_input(runs):
    c,w,cs,values=runs
    e=V2Simulator(c,w,'joint_sla',cs);e.prepare_timing();snap=e.snapshot()
    class NoFuture:
        def __getattribute__(self,name):raise AssertionError('future tape accessed: '+name)
    e.workload=NoFuture()
    rows=headroom_rows(c,snap,cs,np.zeros(c.service_count),0)
    result=actions(c,snap,e.settings,[],rows)
    assert len(result)<=2 and all(r['recent_rate_rps']==0 for r in rows)

def test_scalein_guard_and_gold_repair(runs,monkeypatch):
    c,w,cs,values=runs;e=V2Simulator(c,w,'joint_sla',cs);e.prepare_timing();snap=e.snapshot()
    sid=next(s.service_id for s in w.services if s.tier=='Gold')
    monkeypatch.setattr('joint_sla_v2.policy.joint_actions',lambda *args:[Action('scale_down',sid,replica_id=0)])
    rows=headroom_rows(c,snap,cs,np.zeros(c.service_count),0)
    result=actions(c,snap,e.settings,[],rows)
    row=next(r for r in rows if r['service_id']==sid)
    assert row['prevented_scale_ins_due_to_headroom']==row['prevented_scale_ins_Gold']==1
    assert not any(a.kind=='scale_down' and a.service_id==sid for a in result)
    assert len(result)<=2 and len({a.service_id for a in result})==len(result)
    assert all(w.services[a.service_id].tier=='Gold' for a in result)

def test_capacity_infeasible_floor_never_waived(runs):
    c,w,cs,values=runs;e=V2Simulator(c,w,'joint_sla',cs);e.prepare_timing();snap=e.snapshot()
    snap['reserved']=snap['capacities'].copy()
    rows=headroom_rows(c,snap,cs,np.zeros(c.service_count),0)
    assert all(not r['capacity_feasible_scaleout'] for r in rows)
    assert all(a.kind!='scale_up' for a in actions(c,snap,e.settings,[],rows))

@pytest.mark.parametrize('seed',[31,45,60,1,100,106])
def test_development_rejects_non_development(seed):
    with pytest.raises(ValueError):seed_gate('development',seed)

def test_heldout_cannot_run_before_freeze(tmp_path):
    with pytest.raises(FileNotFoundError):seed_gate('heldout',31,tmp_path)
    assert set(SEEDS['development']).isdisjoint(SEEDS['heldout'])

def test_hash_and_frozen_config_mutation(tmp_path):
    content=json.dumps(dict(parameters=asdict(Parameters())))
    for name in ('frozen_config.json','jointsla_v2_frozen_config.json','joint_sla_v2_frozen_config.json'):(tmp_path/name).write_text(content)
    (tmp_path/'algorithm_description.md').write_text('test')
    (tmp_path/'freeze_manifest.json').write_text(json.dumps(dict(config_sha256=sha(tmp_path/'frozen_config.json'),source_hashes={},algorithm_description_sha256=sha(tmp_path/'algorithm_description.md'))))
    verify_freeze(tmp_path)
    (tmp_path/'frozen_config.json').write_text('{}')
    with pytest.raises(RuntimeError):verify_freeze(tmp_path)

def test_v1_and_hardware_sources_unchanged():
    protected=json.loads((ROOT/'results/jointsla_v2_development/protected_hashes.json').read_text())
    for name in ('joint_routing/controller.py','joint_routing/router.py','controller_optimization/optimized.py','dynamic_placement/simulator.py','results/hardware_grounded/hardware_profiles.json'):
        assert sha(ROOT/name)==protected[name]

def test_policy_registration_restored(runs):
    assert '__joint_adapter__' not in POLICIES

def test_frozen_source_mutation_rejected(tmp_path):
    content=json.dumps(dict(parameters=asdict(Parameters())))
    for name in ('frozen_config.json','jointsla_v2_frozen_config.json','joint_sla_v2_frozen_config.json'):(tmp_path/name).write_text(content)
    source=tmp_path/'source.py';source.write_text('fixed')
    description=tmp_path/'algorithm_description.md';description.write_text('fixed')
    (tmp_path/'freeze_manifest.json').write_text(json.dumps(dict(config_sha256=sha(tmp_path/'frozen_config.json'),source_hashes={str(source):sha(source)},algorithm_description_sha256=sha(description))))
    verify_freeze(tmp_path)
    source.write_text('changed')
    with pytest.raises(RuntimeError,match='Frozen source modified'):verify_freeze(tmp_path)

def test_frozen_description_mutation_rejected(tmp_path):
    content=json.dumps(dict(parameters=asdict(Parameters())))
    for name in ('frozen_config.json','jointsla_v2_frozen_config.json','joint_sla_v2_frozen_config.json'):(tmp_path/name).write_text(content)
    description=tmp_path/'algorithm_description.md';description.write_text('fixed')
    (tmp_path/'freeze_manifest.json').write_text(json.dumps(dict(config_sha256=sha(tmp_path/'frozen_config.json'),source_hashes={},algorithm_description_sha256=sha(description))))
    verify_freeze(tmp_path)
    description.write_text('changed')
    with pytest.raises(RuntimeError,match='Frozen algorithm description'):verify_freeze(tmp_path)
