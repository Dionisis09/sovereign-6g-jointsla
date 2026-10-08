"""Phase gate before generation, one candidate, immutable source/config freeze."""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import json,subprocess
from hardware_grounded.environment import ROOT,write_json
from hardware_grounded.integrity import sha
from .policy import Parameters

DEV=ROOT/'results/jointsla_v2_development'
FINAL=ROOT/'results/jointsla_v2_heldout'
POLICIES=('sla_aware','joint_sla_v1','joint_sla_v2')
SEEDS={'development':tuple(range(101,106)),'heldout':tuple(range(31,61))}
LOADS={'development':(.5,1.,2.),'heldout':(1.,2.)}

def now():return datetime.now(timezone.utc).isoformat()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def verify_protected():
    protected=read(DEV/'protected_hashes.json')
    changed=[p for p,h in protected.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    if changed:raise RuntimeError('Protected historical files changed: '+str(changed))
    return dict(protected_files=len(protected),changed_files=changed)

def source_hashes():
    paths=sorted((ROOT/'joint_sla_v2').glob('*.py'))+list((ROOT/'joint_sla_v2').glob('*.md'))
    paths += [ROOT/'run_jointsla_v2.py',ROOT/'tests/test_joint_sla_v2.py']
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths}

def verify_freeze(folder=FINAL):
    manifest=read(folder/'freeze_manifest.json')
    if 'protected_manifest_sha256' in manifest and sha(DEV/'protected_hashes.json')!=manifest['protected_manifest_sha256']:raise RuntimeError('Protected manifest modified')
    if sha(folder/'frozen_config.json')!=manifest['config_sha256']:raise RuntimeError('Frozen config modified')
    if sha(folder/'jointsla_v2_frozen_config.json')!=manifest['config_sha256']:raise RuntimeError('Named frozen config modified')
    if sha(folder/'joint_sla_v2_frozen_config.json')!=manifest['config_sha256']:raise RuntimeError('Alternate named frozen config modified')
    if sha(folder/'algorithm_description.md')!=manifest['algorithm_description_sha256']:raise RuntimeError('Frozen algorithm description modified')
    for p,h in manifest['source_hashes'].items():
        if not (ROOT/p).is_file() or sha(ROOT/p)!=h:raise RuntimeError('Frozen source modified: '+p)
    if read(folder/'frozen_config.json')['parameters']!=asdict(Parameters()):raise RuntimeError('Parameters differ from freeze')
    return manifest

def seed_gate(phase,seed,folder=FINAL):
    """Must run BEFORE regime_inputs or any workload generator."""
    if phase not in SEEDS or seed not in SEEDS[phase]:raise ValueError('Seed not allowed in phase')
    if phase=='heldout':return verify_freeze(folder)
    return None

def generate(phase,seed,load):
    manifest=seed_gate(phase,seed)
    if load not in LOADS[phase]:raise ValueError('Load not registered')
    from hardware_pressure.design import regime_inputs,scale_traffic
    folder=DEV if phase=='development' else FINAL
    folder.mkdir(parents=True,exist_ok=True)
    entry=dict(timestamp=now(),phase=phase,seed=seed,load_multiplier=load,
        freeze_config_sha256=manifest['config_sha256'] if manifest else None)
    with (folder/'generation_ledger.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(entry)+'\n')
    c,w,cs=regime_inputs('D7',seed)
    return c,scale_traffic(w,load,c),cs

def freeze():
    if (FINAL/'freeze_manifest.json').exists():return verify_freeze()
    validation=read(DEV/'engineering_acceptance.json')
    if not validation['passed']:raise RuntimeError('Development engineering gate not passed')
    ledger=[json.loads(s) for s in (DEV/'generation_ledger.jsonl').read_text().splitlines()]
    assert all(x['seed'] in SEEDS['development'] and x['phase']=='development' for x in ledger)
    assert not (FINAL/'generation_ledger.jsonl').exists(),'Held-out generated before freeze'
    protected=verify_protected();FINAL.mkdir(parents=True,exist_ok=True)
    config=dict(parameters=asdict(Parameters()),candidate_configurations=1,history_window='max class cold_start_slots = 5',
        development_seeds=list(SEEDS['development']),heldout_seeds=list(SEEDS['heldout']),
        development_loads=list(LOADS['development']),heldout_loads=list(LOADS['heldout']),policies=list(POLICIES),
        action_budget=2,max_replicas=3,bootstrap_resamples=10000,bootstrap_seed=73001,
        primary_family_size=6,secondary_family_size=14,plan_sha256=sha(ROOT/'joint_sla_v2/PLAN.md'))
    config['hardware_profile_sha256']=sha(ROOT/'results/hardware_grounded/hardware_profiles.json')
    config['hardware_grounded_config']=read(DEV/'inputs/load_1.00/seed_101_config.json')['config']
    write_json(FINAL/'frozen_config.json',config);write_json(FINAL/'jointsla_v2_frozen_config.json',config)
    write_json(FINAL/'joint_sla_v2_frozen_config.json',config)
    description=(ROOT/'joint_sla_v2/PLAN.md').read_text(encoding='utf-8')
    (FINAL/'algorithm_description.md').write_text(description,encoding='utf-8')
    git=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True)
    status=subprocess.run(['git','status','--short'],cwd=ROOT,text=True,capture_output=True)
    manifest=dict(timestamp=now(),config_sha256=sha(FINAL/'frozen_config.json'),source_hashes=source_hashes(),
        parameters=asdict(Parameters()),implementation_commit=git.stdout.strip() if git.returncode==0 else None,
        git_status=status.stdout,protected_history=protected,protected_manifest_sha256=sha(DEV/'protected_hashes.json'),
        development_validation_sha256=sha(DEV/'engineering_acceptance.json'),
        algorithm_description_sha256=sha(FINAL/'algorithm_description.md'),
        statement='Seeds 31–60 were neither generated nor inspected during design/development. One candidate only; no post-hoc changes permitted.')
    write_json(FINAL/'freeze_manifest.json',manifest)
    return verify_freeze()
