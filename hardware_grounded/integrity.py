"""Byte-level protection for previously verified experiments and source files."""
import hashlib
import json
from pathlib import Path
from .environment import ROOT, OUTPUT, write_json


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def protect():
    """Snapshot existing code/results once; refuse subsequent alterations."""
    path=OUTPUT/'protected_hashes.json'
    if path.exists():return verify()
    files={}
    for folder in ('paper_30seeds','joint_routing_30seeds','scalability_30seeds','controller_optimization','strong_baseline_30seeds'):
        for file in (ROOT/'results'/folder).rglob('*'):
            if file.is_file():files[file.relative_to(ROOT).as_posix()]=sha(file)
    for file in ROOT.rglob('*.py'):
        relative=file.relative_to(ROOT)
        if any(p in ('.venv','.cache','__pycache__','hardware_grounded','results','.git') for p in relative.parts):continue
        if file.name in ('run_hardware_profiling.py','run_hardware_grounded_experiment.py','test_hardware_grounded.py'):continue
        files[relative.as_posix()]=sha(file)
    write_json(path,files)
    return {'protected_files':len(files),'changed_files':[]}


def verify():
    files=json.loads((OUTPUT/'protected_hashes.json').read_text())
    changed=[name for name,value in files.items() if not (ROOT/name).is_file() or sha(ROOT/name)!=value]
    if changed:raise RuntimeError('Frozen files changed: '+str(changed))
    return {'protected_files':len(files),'changed_files':changed}
