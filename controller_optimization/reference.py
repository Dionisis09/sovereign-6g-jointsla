"""Freeze existing artifacts and capture exact, untimed observable traces."""
import cProfile
import hashlib
import json
import pstats
from pathlib import Path
import numpy as np
import pandas as pd
from catalyst.reused import digest, write_json, write_gzip
from dynamic_placement.metrics import calculate_metrics, validate_run
from dynamic_placement.scenario_model import traffic_hash_payload
from dynamic_placement.workload import generate_workload
from scalability.configuration import ROOT, SCALES, configuration
from scalability.measurement import MeasuredRouted

OUTPUT=ROOT/"results/controller_optimization"
GOLDEN={"SMALL":(1,7,22),"MEDIUM":(1,4,16),"LARGE":(1,12,22)}


def freeze_optimized():
    """Reject mixing results from different optimized implementations/configs."""
    from dataclasses import asdict
    from joint_routing.router import Settings
    current=dict(optimized_sha256=hashlib.sha256((ROOT/"controller_optimization/optimized.py").read_bytes()).hexdigest(),
                 configurations={s:asdict(configuration(s)) for s in SCALES},settings=asdict(Settings()),
                 benchmark_repetitions=7,controller_mean_limit_ms=10.,controller_p95_limit_ms=100.,routing_p95_limit_ms=1.)
    path=OUTPUT/"optimization_protocol.json"
    if path.exists():assert json.loads(path.read_text())==current,"optimized implementation/config changed; use a separate experiment"
    else:write_json(path,current)
    return current


def freeze():
    """Only this new output tree may be written; record all pre-existing baselines."""
    OUTPUT.mkdir(parents=True,exist_ok=True)
    path=OUTPUT/"frozen_baseline_hashes.json"
    if not path.exists():
        files=[]
        for name in ("dynamic_placement","placement_experiment","paper_evaluation","joint_routing","scalability","tests"):
            files.extend(p for p in (ROOT/name).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        for name in ("results/paper_30seeds","results/joint_routing_30seeds","results/scalability_30seeds"):
            files.extend(p for p in (ROOT/name).rglob("*") if p.is_file())
        files.extend(ROOT/n for n in ("run_paper_experiments.py","run_joint_routing.py","run_scalability_experiments.py",
                     "requirements.txt","requirements-paper.txt","catalyst/reused.py"))
        write_json(path,{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))})
    verify_protected()


def verify_protected():
    hashes=json.loads((OUTPUT/"frozen_baseline_hashes.json").read_text())
    for name,value in hashes.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value,name
    return len(hashes)


def plain(value):
    """Canonical JSON, retaining exact Python floats and sequence order."""
    if isinstance(value,np.ndarray):return plain(value.tolist())
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    if hasattr(value,"__dataclass_fields__"):
        from dataclasses import asdict
        return plain(asdict(value))
    return value


def semantic_rows(rows):
    return [{k:plain(v) for k,v in r.items() if k not in ("runtime_ms","decision_runtime_ms")} for r in rows]


def traces(result,snapshots):
    """Timing is the sole excluded observable; raw ordering and floats retained."""
    diagnostics={k:v for k,v in result["diagnostics"].items() if k!="total_simulation_runtime_ms"}
    return plain(dict(actions=result["actions"],routing=semantic_rows(result["routing"]),
                outcomes=result["outcomes"],replica_states=snapshots,
                slots=semantic_rows(result["slots"]),nodes=result["nodes"],
                reservations=result["reservations"],lifecycle=result["lifecycle"],
                deployment_audit=result["deployment_audit"],routing_attempts=semantic_rows(result["routing_attempts"]),
                replica_services=result["replica_services"],diagnostics=diagnostics))


class Capture:
    """Observe exactly the existing 200 snapshots; no extra simulator events."""
    def snapshot(self):
        snap=super().snapshot()
        self.captured_snapshots.append(plain(snap))
        return snap


class GoldenLegacy(Capture,MeasuredRouted):
    def __init__(self,*args,**kwargs):
        self.captured_snapshots=[]
        super().__init__(*args,**kwargs)


def function_profile(prof,scale):
    stats=pstats.Stats(prof)
    # Exclusive Python time in controller/state/routing functions. Simulation
    # resource scheduling and trace/file serialization are not the denominator.
    selected=[]
    for (file,line,name),(primitive,calls,total,cumulative,callers) in stats.stats.items():
        normalized=file.replace("\\","/")
        controlled=("joint_routing/" in normalized or "controller_optimization/optimized.py" in normalized
                    or ("dynamic_placement/simulator.py" in normalized and name=="snapshot")
                    or "dynamic_placement/policies.py" in normalized)
        if controlled:selected.append((normalized,line,name,calls,total,cumulative))
    denominator=sum(row[4] for row in selected)
    return [dict(scale=scale,function=f"{Path(f).name}:{line}:{name}",calls=calls,
                 total_time_ms=total*1000,mean_time_ms=total*1000/calls,
                 percent_controller_time=total/denominator*100,cumulative_time_ms=cumulative*1000,
                 time_scope="exclusive; percentage of selected controller functions")
            for f,line,name,calls,total,cumulative in selected]


def profile(engine_class,phase):
    """cProfile attribution only; absolute budget uses unprofiled runs."""
    rows=[]
    for scale in SCALES:
        c=configuration(scale);w=generate_workload(c,1);engine=engine_class(c,w,"joint_sla")
        prof=cProfile.Profile();prof.enable();result=engine.run();prof.disable()
        validate_run(c,w,result)
        prof.dump_stats(str(OUTPUT/f"profile_{phase}_{scale.lower()}.pstats"))
        rows.extend(function_profile(prof,scale))
        print(f"Profile {phase}: {scale} complete",flush=True)
    frame=pd.DataFrame(rows).sort_values(["scale","total_time_ms"],ascending=[True,False])
    frame.to_csv(OUTPUT/f"profile_{phase}.csv",index=False)
    text=[f"# Controller profile {phase}","",
          "Seed 1, all 100 slots. cProfile perturbs runtime; these values attribute cost and are not budget measurements.",
          "Exclusive function times and a selected-controller exclusive denominator avoid double-counting inclusive time.",
          "Cumulative times retain child NumPy, sorting, copying and allocation costs. The pstats files retain all calls.",""]
    for scale in SCALES:
        text.extend([f"## {scale}","","| Function | Calls | Exclusive ms | Cumulative ms | Controller % |",
                     "|---|---:|---:|---:|---:|"])
        for r in frame[frame.scale==scale].head(15).itertuples():
            text.append(f"| {r.function} | {r.calls} | {r.total_time_ms:.3f} | {r.cumulative_time_ms:.3f} | {r.percent_controller_time:.2f} |")
        text.append("")
    (OUTPUT/f"profile_{phase}.md").write_text("\n".join(text),encoding="utf-8")


def golden_reference():
    rows=[]
    for scale,seeds in GOLDEN.items():
        c=configuration(scale)
        for seed in seeds:
            w=generate_workload(c,seed);engine=GoldenLegacy(c,w,"joint_sla");result=engine.run()
            validate_run(c,w,result)
            trace=traces(result,engine.captured_snapshots)
            (OUTPUT/"golden"/scale).mkdir(parents=True,exist_ok=True)
            write_gzip(OUTPUT/"golden"/scale/f"seed_{seed:03d}.json.gz",trace)
            rows.append(dict(scale=scale,seed=seed,traffic_hash=digest(traffic_hash_payload(w)),
                             workload_hash=digest(w.to_dict()),trace_hash=digest(trace)))
            print(f"Golden legacy: {scale} seed {seed} ({len(result['outcomes']):,} outcomes)",flush=True)
    pd.DataFrame(rows).to_csv(OUTPUT/"golden_reference.csv",index=False)
    verify_protected()


def prepare_reference():
    freeze()
    if not (OUTPUT/"profile_before.csv").exists():profile(MeasuredRouted,"before")
    if not (OUTPUT/"golden_reference.csv").exists():golden_reference()
