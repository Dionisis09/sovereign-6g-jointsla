"""Profile units, no RNG/traffic leakage, and unchanged physical semantics."""
from dataclasses import replace
import json
import numpy as np
import pytest
from hardware_grounded.calibration import (load_profiles,calibrated_config,hardware_workload,configs_for_services,
    model_class,ms_to_seconds,mib_to_gib,cold_slots,CLASS_MODELS,arrival_hash)
from hardware_grounded.physics import HardwareBaseline,HardwareJoint
from hardware_grounded.audit import validate_run
from dynamic_placement.workload import generate_workload
from scalability.configuration import configuration
from scalability.measurement import MeasuredBaseline
from controller_optimization.optimized import OptimizedMeasured
from controller_optimization.reference import semantic_rows
from catalyst.reused import digest


@pytest.fixture
def profiles():return load_profiles()


def test_profile_catalog_and_serialization(profiles):
    assert set(profiles['models'])==set(CLASS_MODELS.values())
    assert json.dumps(profiles,sort_keys=True)==json.dumps(json.loads(json.dumps(profiles)),sort_keys=True)


@pytest.mark.parametrize('field',['cpu_pre_ms','gpu_inference_ms','cpu_post_ms','input_upload_ms','vram_mb','cold_start_ms'])
def test_reject_invalid_profile_field(profiles,tmp_path,field):
    profiles['models']['mobilenet'][field]=-1
    path=tmp_path/'profiles.json';path.write_text(json.dumps(profiles))
    with pytest.raises(ValueError):load_profiles(path)


def test_reject_missing_stage(profiles,tmp_path):
    del profiles['models']['mobilenet']['stage_statistics']['cpu_pre']
    path=tmp_path/'profiles.json';path.write_text(json.dumps(profiles))
    with pytest.raises(ValueError):load_profiles(path)


def test_exact_units():
    assert ms_to_seconds(100)==.1 and mib_to_gib(1024)==1
    assert cold_slots(100,.1)==1 and cold_slots(100.001,.1)==2


def test_deterministic_distribution():
    classes=[model_class(s) for s in range(40)]
    assert [classes.count(c) for c in ('LIGHT','MEDIUM','HEAVY')]==[16,16,8]
    assert all({model_class(s) for s in range(t,40,3)}==set(CLASS_MODELS) for t in range(3))


def test_workload_tape_and_rng_unchanged(profiles):
    a=hardware_workload(profiles,1);b=hardware_workload(profiles,1);original=generate_workload(configuration('MEDIUM'),1)
    assert digest(a.to_dict())==digest(b.to_dict()) and arrival_hash(a)==arrival_hash(original)
    assert a.requests==original.requests and a.traffic==original.traffic and a.initial==original.initial
    assert all(s.deadline_ms==original.services[s.service_id].deadline_ms and s.cpu_cores==original.services[s.service_id].cpu_cores for s in a.services)


def short_workload(profiles):
    c=replace(calibrated_config(profiles),slots=5);w=hardware_workload(profiles,1)
    return c,replace(w,requests=tuple(r for r in w.requests if r.arrival_s<.5),traffic=tuple(r for r in w.traffic if r['slot']<5))


@pytest.mark.parametrize('cls,legacy,policy',[(HardwareBaseline,MeasuredBaseline,'sla_aware'),(HardwareJoint,OptimizedMeasured,'joint_sla')])
def test_adapter_uniform_profile_exact_equivalence(profiles,cls,legacy,policy):
    c,w=short_workload(profiles);expected=legacy(c,w,policy).run();actual=cls(c,w,policy,{s.service_id:c for s in w.services}).run()
    for key in ('outcomes','actions','reservations','lifecycle','nodes','deployment_audit'):
        assert actual[key]==expected[key],key
    for key in ('slots','routing','routing_attempts'):
        assert semantic_rows(actual[key])==semantic_rows(expected[key]),key


@pytest.mark.parametrize('cls,policy',[(HardwareBaseline,'sla_aware'),(HardwareJoint,'joint_sla')])
def test_calibrated_request_accounting_and_no_future_leakage(profiles,cls,policy):
    c,w=short_workload(profiles);cs=configs_for_services(c,profiles,w.services);before=digest(w.to_dict())
    engine=cls(c,w,policy,cs);engine.prepare_timing();snapshot=engine.snapshot()
    altered=replace(w,requests=tuple(replace(r,work_factor=r.work_factor*2) for r in w.requests))
    other=cls(c,altered,policy,cs);other.prepare_timing();second=other.snapshot()
    for field in ('rates','latency_ms','queue_lengths','oldest_wait_ms'):
        assert np.array_equal(snapshot[field],second[field])
    assert not {'requests','traffic','future_rates','burst_plan'}&set(snapshot)
    result=engine.run();check=validate_run(c,w,result,cs)
    assert check['requests_verified']==len(w.requests) and digest(w.to_dict())==before


@pytest.mark.parametrize('sid,expected',[(0,1),(2,2),(4,5)])
def test_real_cold_mapping_and_memory(profiles,sid,expected):
    c,w=short_workload(profiles);cs=configs_for_services(c,profiles,w.services)
    assert cs[sid].cold_start_slots==expected
    p=profiles['models'][CLASS_MODELS[model_class(sid)]]
    assert w.services[sid].gpu_vram_gb==p['vram_mb']/1024
    engine=HardwareBaseline(c,w,'sla_aware',cs)
    target=int(np.argmin(engine.reserved[:,0]));replica=engine.add_replica(sid,target)
    engine.env.run(until=expected*c.slot_seconds+1e-8)
    assert replica.ready
    event=next(e for e in engine.lifecycle_events if e['replica_id']==replica.replica_id)
    assert event['ready_s']==expected*c.slot_seconds
