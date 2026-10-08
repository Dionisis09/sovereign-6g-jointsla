"""Fairness, component isolation, exact identity and diagnostic boundaries."""
from dataclasses import replace,asdict
import numpy as np
import pandas as pd
import pytest
from catalyst.reused import digest
from dynamic_placement.workload import generate_workload
from scalability.configuration import configuration
from hardware_grounded.calibration import load_profiles,hardware_workload,calibrated_config,configs_for_services,model_class
from hardware_grounded.audit import validate_run
from hardware_pressure.design import scale_traffic,regime_inputs,REGIMES,LOADS
from hardware_pressure.observer import ObservedBaseline,ObservedJoint
from hardware_grounded.physics import HardwareBaseline,HardwareJoint
from hardware_pressure.diagnostics import burst_recovery
from controller_optimization.reference import semantic_rows

@pytest.fixture(scope='module')
def w():return hardware_workload(load_profiles(),1)

@pytest.mark.parametrize('m',LOADS)
def test_scaling_deterministic_structure(w,m):
    a=scale_traffic(w,m);b=scale_traffic(w,m)
    assert digest(a.to_dict())==digest(b.to_dict())
    assert a.services==w.services and a.initial==w.initial
    assert a.scenario is w.scenario
    assert [x['burst'] for x in a.traffic]==[x['burst'] for x in w.traffic]
    assert np.allclose([x['expected_rate_rps'] for x in a.traffic],[m*x['expected_rate_rps'] for x in w.traffic],rtol=0,atol=1e-10)
    for attr in ('tier','priority'):
        assert [getattr(s,attr) for s in a.services]==[getattr(s,attr) for s in w.services]
    assert [model_class(s.service_id) for s in a.services]==[model_class(s.service_id) for s in w.services]
    for column in ('tier','model_class'):
        def sums(work):
            values={}
            for row in work.traffic:
                key=work.services[row['service_id']].tier if column=='tier' else model_class(row['service_id'])
                values[key]=values.get(key,0)+row['expected_rate_rps']
            return values
        sa,sb=sums(a),sums(w)
        assert all(np.isclose(sa[k]/sum(sa.values()),sb[k]/sum(sb.values())) for k in sa)
    counts=pd.Series([(r.service_id,r.arrival_slot) for r in a.requests]).value_counts()
    assert all(x['arrivals']==counts.get((x['service_id'],x['slot']),0) for x in a.traffic)
    assert [r.request_id for r in a.requests]==list(range(len(a.requests)))

def test_one_exact_identity(w):assert scale_traffic(w,1.) is w

def test_same_policy_hashes_without_mutation(w):
    from dynamic_placement.scenario_model import traffic_hash_payload
    from hardware_pressure.design import POLICIES
    scaled=scale_traffic(w,1.25);hashes={}
    for policy in POLICIES:
        c,_,cs=regime_inputs('D7',1)
        engine=(ObservedBaseline if policy=='sla_aware' else ObservedJoint)(c,scaled,policy,cs)
        hashes[policy]=digest(traffic_hash_payload(engine.workload))
    assert len(set(hashes.values()))==1

@pytest.mark.parametrize('m',[0,-1,float('nan'),float('inf')])
def test_invalid_scale(w,m):
    with pytest.raises(ValueError):scale_traffic(w,m)

@pytest.mark.parametrize('regime',REGIMES)
def test_decomposition_only_intended_fields(regime):
    p=load_profiles();c,w,cs=regime_inputs(regime,1,p)
    base=configuration('MEDIUM');original=generate_workload(base,1);real=calibrated_config(p)
    e,v,cold=REGIMES[regime]
    allowed={'preprocess_ms','inference_ms','postprocess_ms'} if e else set()
    if cold:allowed.add('cold_start_slots')
    for k,x in asdict(c).items():assert x==getattr(real if k in allowed else base,k)
    real_cs=configs_for_services(real,p,w.services)
    for sid,x in cs.items():
        for k,value in asdict(x).items():assert value==getattr(real_cs[sid] if k in allowed else base,k)
    for s in w.services:
        a,b=asdict(s),asdict(original.services[s.service_id]);a.pop('gpu_vram_gb');b.pop('gpu_vram_gb');assert a==b
        if not v:assert s.gpu_vram_gb==original.services[s.service_id].gpu_vram_gb
    assert w.requests==original.requests and w.traffic==original.traffic and w.initial==original.initial
    if regime=='D7':assert digest(w.to_dict())==digest(hardware_workload(p,1).to_dict()) and c==real

@pytest.mark.parametrize('cls,plain,policy',[(ObservedBaseline,HardwareBaseline,'sla_aware'),(ObservedJoint,HardwareJoint,'joint_sla')])
def test_observer_no_events_no_future_leakage_and_request_accounting(w,cls,plain,policy):
    c=replace(calibrated_config(load_profiles()),slots=4)
    short=replace(w,requests=tuple(r for r in w.requests if r.arrival_slot<4),traffic=tuple(x for x in w.traffic if x['slot']<4))
    cs=configs_for_services(c,load_profiles(),short.services)
    engine=cls(c,short,policy,cs);engine.prepare_timing();snap=engine.snapshot()
    other=cls(c,replace(short,requests=tuple(replace(r,work_factor=20.) for r in short.requests)),policy,cs);other.prepare_timing();second=other.snapshot()
    for k in ('rates','latency_ms','queue_lengths','oldest_wait_ms'):assert np.array_equal(snap[k],second[k])
    assert not {'requests','traffic','future_rates','burst_plan'}&set(snap)
    # Separate engine: the manual snapshot above is only a leakage probe.
    result=cls(c,short,policy,cs).run();expected=plain(c,short,policy,cs).run()
    for k in ('outcomes','actions','reservations','lifecycle','nodes'):assert result[k]==expected[k]
    for k in ('slots','routing','routing_attempts'):assert semantic_rows(result[k])==semantic_rows(expected[k])
    assert len(result['pressure_services'])==4*40 and len(result['pressure_nodes'])==4*10
    assert validate_run(c,short,result,cs)['requests_verified']==len(short.requests)
    # Accounting verifier must reject both missing and duplicate outcomes.
    broken=dict(result,outcomes=result['outcomes'][:-1])
    with pytest.raises(AssertionError):validate_run(c,short,broken,cs)
    broken=dict(result,outcomes=result['outcomes']+[result['outcomes'][0]])
    with pytest.raises(AssertionError):validate_run(c,short,broken,cs)

def test_burst_recovery_known_and_censored():
    class C:slots=8;slot_seconds=.1
    class W:traffic=tuple(dict(service_id=0,slot=i,burst=i in (2,3)) for i in range(8))
    sv=[dict(slot=i,service_id=0,active=2,allocated=2,waiting=[0,0,2,4,3,1,0,0][i]) for i in range(8)]
    out=pd.DataFrame([dict(service_id=0,arrival_slot=3,breach=True)])
    ac=[dict(service_id=0,kind='scale_up',time_s=.3)]
    r=burst_recovery(C,W,out,sv,ac,[],{})
    assert r.iloc[0].recovery_slot==5 and r.iloc[0].recovery_after_burst_slots==1
    assert np.isclose(r.iloc[0].first_scaleout_delay_slots,1) and r.iloc[0].queue_growth==4
    for s in sv:s['waiting']=8
    sv[1]['waiting']=0
    r=burst_recovery(C,W,out,sv,[],[],{})
    assert r.iloc[0].recovery_censored and r.iloc[0].scaleout_censored

def test_crossover_calculation():
    from hardware_pressure.analysis import paired_tables
    rows=[dict(load_multiplier=m,seed=s,policy=p,sla_breach_rate=(.2 if p=='sla_aware' else .3 if m==.5 else .1),mean_request_latency_ms=1.,p95_latency_ms=2.,p99_latency_ms=3.) for m in (.5,2.) for s in range(1,31) for p in ('sla_aware','joint_sla')]
    tests,diffs=paired_tables(pd.DataFrame(rows))
    f=tests[tests.metric=='sla_breach_rate'].set_index('load_multiplier')
    assert np.isclose(f.loc[.5,'delta_joint_minus_sla'],.1) and np.isclose(f.loc[2.,'delta_joint_minus_sla'],-.1)
    assert f.loc[.5,'losses']==30 and f.loc[2.,'wins']==30 and len(diffs)==240

def test_crossover_brackets_allow_unresolved_intermediate_load():
    from hardware_pressure.analysis import envelope
    f=pd.DataFrame([dict(metric='sla_breach_rate',load_multiplier=m,delta_joint_minus_sla=d,delta_ci95_lower=lo,delta_ci95_upper=hi,p_value_holm=p,supported_direction=side) for m,d,lo,hi,p,side in [(1.,.1,.05,.15,.01,'SLA-aware'),(1.25,-.01,-.05,.03,.4,'unresolved'),(1.5,-.1,-.15,-.05,.01,'JointSLA')]])
    _,status=envelope(f)
    assert status['observed_mean_sign_crossing_intervals']==[[1.,1.25]]
    assert status['supported_crossing_intervals']==[[1.,1.5]] and status['supported_crossover']
