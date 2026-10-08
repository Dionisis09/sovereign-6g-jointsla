"""Isolated executions of unchanged engines on archived, paired input tapes.

This is the only dashboard module authorized to execute simulations and write
run artifacts. It never invokes historical experiment drivers or generators.
"""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import uuid
import numpy as np
import pandas as pd
from dashboard.data_loader import ROOT

LIVE_ROOT=ROOT/'dashboard'/'.cache'/'live_runs'
POLICIES=('sla_aware','joint_sla_v1','joint_sla_v2')
PRIMARY=('sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms',
         'Gold_breach_rate','Silver_breach_rate','Bronze_breach_rate','average_replicas','total_actions','cold_starts')

def check_selection(load,seeds,policies):
    if load not in (1.,2.):raise ValueError('Use the archived 1× or 2× scenario')
    if not 1<=len(seeds)<=3 or len(set(seeds))!=len(seeds) or any(type(s) is not int or s not in range(31,61) for s in seeds):
        raise ValueError('Select one to three distinct archived seeds 31–60')
    if not policies or len(set(policies))!=len(policies) or any(p not in POLICIES for p in policies):
        raise ValueError('Unknown or duplicate policy')

def restore(load,seed):
    """Deserialize archived records without generating any new arrivals."""
    from dynamic_placement.config import Config
    from dynamic_placement.workload import Workload, Service, Request
    from placement_experiment.data_generation import Scenario,EdgeServer,Application
    directory=ROOT/'results'/'jointsla_v2_heldout'/'inputs'/f'load_{load:.2f}'
    tape=directory/f'seed_{seed:03d}.json.gz'
    configfile=directory/f'seed_{seed:03d}_config.json'
    with gzip.open(tape,'rt',encoding='utf-8') as handle:data=json.load(handle)
    record=json.loads(configfile.read_text(encoding='utf-8'))
    network=np.asarray(data['scenario']['network_latency_ms'],dtype=float);network.setflags(write=False)
    s=data['scenario']
    scenario=Scenario(s['seed'],tuple(EdgeServer(**x) for x in s['nodes']),tuple(Application(**x) for x in s['applications']),network)
    workload=Workload(data['seed'],scenario,tuple(Service(**x) for x in data['services']),tuple(data['gpu_units']),
                      {int(k):v for k,v in data['initial'].items()},tuple(Request(**x) for x in data['requests']),tuple(data['traffic']))
    configs={int(k):Config(**v) for k,v in record['service_configs'].items()}
    return Config(**record['config']),workload,configs,record,[tape,configfile]

def execute(load,seeds,policies,progress=None):
    """Fresh engine runs and physical/accounting audits; immutable input replay.

    Metrics are per-run observations, not a new statistical paper analysis.
    Every output directory is unique and restricted to the live workspace.
    """
    check_selection(load,seeds,policies)
    from catalyst.reused import digest
    from dynamic_placement.metrics import calculate_metrics
    from paper_evaluation.accounting import augment_metrics
    from hardware_grounded.audit import validate_run
    from hardware_pressure.observer import ObservedBaseline,ObservedJoint
    from joint_sla_v2.simulator import V2Simulator
    from joint_routing.router import Settings
    from scalability.experiment import export_run
    livebase=LIVE_ROOT.resolve()
    if livebase != (ROOT/'dashboard'/'.cache'/'live_runs').resolve():raise ValueError('Live outputs must stay in dashboard/.cache/live_runs')
    runid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]
    output=(livebase/runid).resolve()
    if not output.is_relative_to(livebase):raise ValueError('Invalid live output target')
    output.mkdir(parents=True,exist_ok=False)
    rows=[];checks=[];comparisons=[];inputs={}
    historic=pd.read_csv(ROOT/'results'/'jointsla_v2_heldout'/'raw_results.csv')
    frozen=json.loads((ROOT/'results'/'jointsla_v2_heldout'/'freeze_manifest.json').read_text(encoding='utf-8'))
    for path,expected in frozen['source_hashes'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:raise RuntimeError('Frozen source integrity failed: '+path)
    total=len(seeds)*len(policies)
    for seed in seeds:
        config,workload,service_configs,record,files=restore(load,seed)
        wh=digest(workload.to_dict())
        if wh!=record['workload_hash']:raise RuntimeError('Archived workload hash mismatch')
        inputs.update({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
        for policy in policies:
            engine={'sla_aware':ObservedBaseline,'joint_sla_v1':ObservedJoint,'joint_sla_v2':V2Simulator}[policy]
            result=engine(config,workload,'sla_aware' if policy=='sla_aware' else 'joint_sla',service_configs,Settings()).run()
            audit=validate_run(config,workload,result,service_configs)
            legacy,slots,nodes,outcomes=calculate_metrics(config,workload,result)
            metrics=augment_metrics(config,workload,result,legacy,outcomes,slots,nodes)
            metrics['average_vram_residency_gib']=metrics['vram_gb_seconds']/(config.slots*config.slot_seconds)
            folder=output/f'seed_{seed:03d}'/policy
            export_run(folder,result,slots,nodes,outcomes)
            exported=pd.read_csv(folder/'request_outcomes.csv.gz')
            pd.testing.assert_frame_equal(exported,outcomes,check_dtype=False,check_exact=False,rtol=1e-9,atol=1e-7)
            if len(exported)!=len(workload.requests) or exported.request_id.duplicated().any():raise RuntimeError('Export accounting failed')
            reference=historic[(historic.load_multiplier==load)&(historic.seed==seed)&(historic.policy==policy)].iloc[0]
            matches={m:bool(np.isclose(metrics[m],reference[m],rtol=1e-9,atol=1e-7)) for m in PRIMARY}
            comparisons.append(dict(seed=seed,policy=policy,**matches,all_primary_match=all(matches.values())))
            rows.append(dict(load_multiplier=load,seed=seed,policy=policy,workload_hash=wh,traffic_hash=record['traffic_hash'],**metrics))
            checks.append(dict(seed=seed,policy=policy,exported_requests_verified=len(exported),primary_matches_frozen=all(matches.values()),physical_audit=audit))
            if digest(workload.to_dict())!=wh:raise RuntimeError('Engine mutated archived inputs')
            if progress:progress(len(rows)/total,f'Seed {seed} · {policy} · {len(exported):,} request outcomes verified')
    for path,expected in inputs.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:raise RuntimeError('Archived source changed during replay')
    raw=pd.DataFrame(rows);raw.to_csv(output/'live_results.csv',index=False)
    pd.DataFrame(comparisons).to_csv(output/'frozen_comparison.csv',index=False)
    manifest=dict(run_id=runid,type='isolated live replay',load_multiplier=load,seeds=seeds,policies=policies,
                  input_sha256=inputs,frozen_source_hashes=frozen['source_hashes'],checks=checks,
                  new_seeds_generated=False,parameter_tuning=False,paper_statistics_updated=False,
                  all_primary_match=all(c['all_primary_match'] for c in comparisons))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,default=str),encoding='utf-8')
    return str(output),raw,manifest
