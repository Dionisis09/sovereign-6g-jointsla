"""Predeclared objective and hypotheses; protected source/output byte hashes."""
from dataclasses import asdict
import hashlib,json
from pathlib import Path
from catalyst.reused import write_json
from scalability.configuration import ROOT,SCALES,configuration
from .optimization import Weights

OUTPUT=ROOT/"results/strong_baseline_30seeds"
POLICIES=("sla_aware","joint_sla","mjo")
HYPOTHESES={
 "B1":"MJO has supported SLA and p95 improvements over SLA-aware at all three scales; only then qualifies as generally stronger here",
 "B2":"JointSLA is competitive in SLA if all-scale upper paired bootstrap relative deterioration vs MJO <=5%; descriptive noninferiority screen, not an equivalence test",
 "B3":"same <=5% upper paired bootstrap screen for both p95/p99 at all three scales",
 "B4":"JointSLA full-controller mean lower at all scales with positive paired lower CI and Holm p<.05 in separate 3-test overhead family",
 "B5":"MJO upper paired resource-increase CIs vs JointSLA <=5% replicas, <=2pp VRAM, <=5% actions/1000 requests at all scales; otherwise record resource trade-off"
}


def protect():
    OUTPUT.mkdir(parents=True,exist_ok=True);path=OUTPUT/"protected_hashes.json"
    if not path.exists():
        files=[]
        for name in ("dynamic_placement","placement_experiment","paper_evaluation","joint_routing","scalability","controller_optimization","tests"):
            files.extend(p for p in (ROOT/name).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="test_strong_baseline.py")
        for name in ("results/paper_30seeds","results/joint_routing_30seeds","results/scalability_30seeds","results/controller_optimization"):
            files.extend(p for p in (ROOT/name).rglob("*") if p.is_file())
        files.extend(ROOT/n for n in ("run_paper_experiments.py","run_joint_routing.py","run_scalability_experiments.py","run_controller_optimization.py",
                                     "requirements.txt","requirements-paper.txt","catalyst/reused.py","tools/verify_controller_optimization.py"))
        write_json(path,{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))})
    return verify_protected()


def verify_protected():
    hashes=json.loads((OUTPUT/"protected_hashes.json").read_text())
    for name,value in hashes.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value,name
    return len(hashes)


def configure():
    protect()
    current=dict(name="Myopic Joint Optimization",weights=asdict(Weights()),scales={s:asdict(configuration(s)) for s in SCALES},
      information="same causal snapshot fields plus common current lifecycle telemetry; no future workload or hidden work_factor",
      routing="service-specific current arrived backlog; exact min-cost rectangular matching in oldest-first blocks of 64; FIFO within replicas",
      deployment="additive action menu costs evaluated with same assignment; exact budget-two binary selection unless deterministic 50000-pair limit",
      constraints="one action/service, two actions/slot; positive simultaneous reservations; no credit for later source/scale-in releases; unchanged physical capacity/lifecycle guards",
      fallback="deployment no-op; routing previous queued state retained and new arrivals remain pending; never JointSLA fallback",
      weights_rationale="latency/lateness normalized by deadline with weights 1; resource .35 and lifecycle .25 reuse existing headroom/overhead coefficients; congestion .25 fixed before pilot",
      margin_rationale="5% relative operational screen reuses frozen p99 noninferiority tolerance; applies to SLA/tails for uniform trade-off screening, not a calibrated SLA acceptance guarantee",
      hypotheses=HYPOTHESES,primary_holm_family=12,secondary_holm_family=12,overhead_holm_family=3,
      bootstrap_resamples=10000,full_seeds=list(range(1,31)),pilot_seeds=[1,2,3],
      pilot_runtime_limit_per_run_seconds=600,pilot_rss_limit_mib=4096,full_estimated_runtime_limit_seconds=14400)
    path=OUTPUT/"baseline_configuration.json"
    if path.exists():assert json.loads(path.read_text())==current,"predeclared configuration changed"
    else:write_json(path,current)
    return current


def source_hashes():
    paths=[*(ROOT/"strong_baseline"/n for n in ("__init__.py","optimization.py","simulator.py","protocol.py","experiment.py")),ROOT/"run_strong_baseline.py"]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
