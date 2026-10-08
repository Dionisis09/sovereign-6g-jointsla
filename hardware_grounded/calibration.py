"""Physical-unit calibration, separated from frozen scheduling algorithms."""
from dataclasses import asdict,replace
import json,math
import numpy as np
from dynamic_placement.workload import generate_workload
from scalability.configuration import configuration
from catalyst.reused import digest
from .environment import OUTPUT,ROOT,write_json
from .integrity import sha,verify

CLASS_MODELS={'LIGHT':'mobilenet','MEDIUM':'resnet50','HEAVY':'vit_b16'}
CLASS_CYCLE=('LIGHT','LIGHT','MEDIUM','MEDIUM','HEAVY')


def ms_to_seconds(value):return float(value)/1000
def mib_to_gib(value):return float(value)/1024


def cold_slots(value,slot_seconds):
    """Conservative integer-slot quantization, maintaining lifecycle semantics."""
    if not math.isfinite(value) or value<=0 or slot_seconds<=0:raise ValueError('invalid cold time')
    return max(1,math.ceil(value/(slot_seconds*1000)))


def model_class(sid):return CLASS_CYCLE[sid%5]


def load_profiles(path=None):
    value=json.loads((path or OUTPUT/'hardware_profiles.json').read_text(encoding='utf-8'))
    if value['schema_version']!=1 or value['units']!={'timing':'ms','vram':'MiB (2^20 bytes)'}:raise ValueError('profile schema/units')
    if set(value['models'])!=set(CLASS_MODELS.values()):raise ValueError('incomplete model catalog')
    for name,p in value['models'].items():
        if p['batch_size']!=1 or p['dtype']!='float32':raise ValueError('batch/precision mismatch')
        for field in ('cpu_pre_ms','input_upload_ms','gpu_inference_ms','cpu_post_ms','vram_mb','cold_start_ms'):
            if not math.isfinite(p[field]) or p[field]<=0:raise ValueError(name+': '+field)
        if p['cold_start_ms']<=p['gpu_inference_ms']:raise ValueError('cold <= steady')
        if set(('cpu_pre','input_upload','gpu_inference','cpu_post'))-set(p['stage_statistics']):raise ValueError('missing stages')
    return value


def service_config(base,profile):
    return replace(base,preprocess_ms=profile['cpu_pre_ms']+profile['input_upload_ms'],
        inference_ms=profile['gpu_inference_ms'],postprocess_ms=profile['cpu_post_ms'],
        cold_start_slots=cold_slots(profile['cold_start_ms'],base.slot_seconds))


def calibrated_config(profiles):
    """Global controller interface stays global: population mean of model medians."""
    base=configuration('MEDIUM');items=[profiles['models'][CLASS_MODELS[c]] for c in CLASS_CYCLE]
    return replace(base,preprocess_ms=float(np.mean([p['cpu_pre_ms']+p['input_upload_ms'] for p in items])),
        inference_ms=float(np.mean([p['gpu_inference_ms'] for p in items])),postprocess_ms=float(np.mean([p['cpu_post_ms'] for p in items])),
        cold_start_slots=cold_slots(float(np.mean([p['cold_start_ms'] for p in items])),base.slot_seconds))


def hardware_workload(profiles,seed):
    """Generate the original tape first; map physical memory without any RNG call.

    Common initial node assignments, resource capacities, SLA deadlines, payloads,
    arrivals and per-request work factors are preserved verbatim.
    """
    original=generate_workload(configuration('MEDIUM'),seed)
    services=tuple(replace(s,gpu_vram_gb=mib_to_gib(profiles['models'][CLASS_MODELS[model_class(s.service_id)]]['vram_mb'])) for s in original.services)
    apps=tuple(replace(a,gpu_demand=services[a.application_id].gpu_vram_gb) for a in original.scenario.applications)
    workload=replace(original,services=services,scenario=replace(original.scenario,applications=apps))
    assert workload.requests==original.requests and workload.traffic==original.traffic and workload.initial==original.initial
    assert all(s.gpu_vram_gb<=original.services[s.service_id].gpu_vram_gb for s in services),'existing initial placement must remain feasible'
    return workload


def configs_for_services(base,profiles,services):
    return {s.service_id:service_config(base,profiles['models'][CLASS_MODELS[model_class(s.service_id)]]) for s in services}


def arrival_hash(workload):
    return digest(dict(seed=workload.seed,requests=[asdict(r) for r in workload.requests],traffic=workload.traffic))


def freeze():
    """Freeze profiles and all execution parameters before tests or pilot outcomes."""
    profiles=load_profiles();config=calibrated_config(profiles)
    value=dict(regime='DIRECT',scale='MEDIUM',seeds=list(range(1,31)),pilot_seeds=[1,2,3],policies=['sla_aware','joint_sla'],
        config=asdict(config),model_distribution={'LIGHT':.4,'MEDIUM':.4,'HEAVY':.2},assignment='service_id modulo 5 -> LIGHT,LIGHT,MEDIUM,MEDIUM,HEAVY',
        controller_parameterization='unchanged global interface; 40/40/20 weighted means of class median stage times; weighted mean measured cold rounded up to integer slots',
        physical_parameterization='each worker reads its class median stage times and ceil(class median cold / slot); frozen worker delegated unchanged through a config-only view',
        initial_placement='original generator assignments preserved, no recalculated placement',deadlines='original physical-ms deadlines unchanged',
        vram='peak allocated bytes/2^30; conservative independent per-replica reservation, includes framework workspace',
        synthetic_unchanged=['nodes and all capacities','GPU concurrency slots','CPU core demands','bandwidth/payload/network','arrival tape','work-factor jitter','migration downtime/penalty','first-request cold penalty'],
        statistical_family=['sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms'],bootstrap_resamples=10000,
        optional_analyses='not scheduled; direct mapping is dimensionally valid. No pressure-preserving, LARGE or p95 sensitivity results claimed.',
        hypothesis_plan_sha256=sha(ROOT/'hardware_grounded/PLAN.md'),profile_sha256=sha(OUTPUT/'hardware_profiles.json'),
        mapping_sha256=sha(ROOT/'hardware_grounded/SIMULATOR_MAPPING.md'),hardware_info_sha256=sha(OUTPUT/'hardware_info.json'))
    path=OUTPUT/'experiment_freeze.json'
    if path.exists():
        if json.loads(path.read_text())!=value:raise RuntimeError('frozen calibration/config changed')
    else:write_json(path,value)
    verify()
    return value,profiles,config
