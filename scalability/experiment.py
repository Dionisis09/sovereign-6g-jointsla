"""Sequential, per-run exports preserve memory and both verified result trees."""
from dataclasses import asdict
import gc
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json,write_gzip
from dynamic_placement.workload import generate_workload
from dynamic_placement.metrics import calculate_metrics,validate_run
from paper_evaluation.accounting import augment_metrics
from joint_routing.experiment import extra_metrics
from joint_routing.router import Settings
from .configuration import ROOT,SCALES,POLICIES,configuration,workload_summary,preflight
from .measurement import MeasuredBaseline,MeasuredRouted,MemoryMonitor,normalized_metrics


def protected_hashes():
    files=[]
    for folder in ("dynamic_placement","placement_experiment","paper_evaluation","joint_routing","tests"):
        files.extend((ROOT/folder).glob("*.py"))
    for folder in ("results/paper_30seeds","results/joint_routing_30seeds"):
        files.extend(p for p in (ROOT/folder).rglob("*") if p.is_file())
    files.extend(ROOT/p for p in ("dynamic_placement/config.json","joint_routing/README.md","joint_routing/DELIVERY.md",
                                  "requirements.txt","requirements-paper.txt","run_paper_experiments.py","run_joint_routing.py","catalyst/reused.py"))
    files=[p for p in files if p.name not in ("test_scalability.py",)]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}


def sources():
    paths=[*(ROOT/"scalability"/n for n in ("__init__.py","configuration.py","measurement.py","experiment.py","README.md")),ROOT/"run_scalability_experiments.py"]
    return {p.relative_to(ROOT).as_posix():digest(p.read_text(encoding="utf-8")) for p in paths}


def safe_output(output):
    resolved=output.resolve()
    for name in ("results/paper_30seeds","results/joint_routing_30seeds","dynamic_placement","joint_routing","paper_evaluation"):
        protected=(ROOT/name).resolve()
        if resolved==protected or protected in resolved.parents or resolved in protected.parents:
            raise ValueError("output overlaps protected baseline: "+str(resolved))
    return resolved


def freeze(output,seeds):
    path=output/"simulation_protocol.json"
    current=dict(seeds=list(seeds),scales={s:asdict(configuration(s)) for s in SCALES},policies=list(POLICIES),settings=asdict(Settings()),
                 source_hashes=sources(),protected_hashes=protected_hashes(),
                 hypotheses="H1/H2 all scales; H3 supported SLA+p95 in >=2 scales and LARGE nonnegative means with <=15 losses; H4 controller mean<=10ms, controller p95<=100ms, routing p95<=1ms all scales; H5 replica<=5%, VRAM<=2pp, normalized actions<=5% upper bounds all scales",
                 main_holm_family_size=12,secondary_holm_family_size=12,bootstrap_resamples=10000,
                 fixed_action_budget=2,pilot_runtime_limit_seconds=600,pilot_sampled_rss_limit_mib=4096,pilot_drain_limit_seconds=120)
    if path.exists():
        old=json.loads(path.read_text(encoding="utf-8"));assert old==current,"frozen sources/config/protected artifacts changed"
    else:write_json(path,current)
    return current


def export_run(folder,result,slots,nodes,outcomes):
    folder.mkdir(parents=True,exist_ok=True)
    frames=dict(request_outcomes=outcomes,slot_trajectories=slots,node_trajectories=nodes,
                routing_decisions=pd.DataFrame(result["routing"]),routing_attempts=pd.DataFrame(result["routing_attempts"]),
                control_snapshot_times=pd.DataFrame(result["control_snapshot_times"]),actions=pd.DataFrame(result["actions"]),
                reservation_events=pd.DataFrame(result["reservations"]),lifecycle_events=pd.DataFrame(result["lifecycle"]),
                deployment_audit=pd.DataFrame(result["deployment_audit"]))
    cpu=pd.DataFrame(result["timing"]["control_cpu_times"])
    cpu["eligible_replicas_end"]=result["timing"]["eligible_slot_samples"]
    frames["controller_cpu_times"]=cpu
    for name,frame in frames.items():
        if frame.empty:frame=pd.DataFrame(columns=["empty"])
        frame.to_csv(folder/f"{name}.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    write_json(folder/"timing.json",result["timing"])
    write_json(folder/"replica_services.json",result["replica_services"])


def baseline_metrics(result):
    times=pd.DataFrame(result["slots"]).set_index("slot").decision_runtime_ms
    snapshot=pd.DataFrame(result["control_snapshot_times"]).set_index("slot").runtime_ms
    total=times+snapshot
    return dict(controller_decision_mean_ms=float(times.mean()),controller_decision_p95_ms=float(times.quantile(.95)),
                controller_total_instrumented_mean_ms=float(total.mean()),controller_total_instrumented_p95_ms=float(total.quantile(.95)),
                controller_snapshot_mean_ms=float(snapshot.mean()),request_routing_decision_mean_ms=0.,request_routing_decision_p95_ms=0.,
                routing_computation_per_request_ms=0.,routing_attempts=0,routing_assignments=0,routing_no_eligible_attempts=0,
                routed_away_from_lowest_network_fraction=0.,queue_changed_choice_fraction=0.,multi_eligible_fraction=0.,
                mean_per_service_replica_request_cv=0.)


def run(output,seeds,pilot=False,reuse=False,force=False):
    output=safe_output(output);output.mkdir(parents=True,exist_ok=True)
    protocol=freeze(output,seeds)
    if reuse:
        raw=pd.read_csv(output/"raw_results.csv")
        assert len(raw)==len(seeds)*len(SCALES)*len(POLICIES)
        return raw
    if (output/"raw_results.csv").exists() and not force:raise ValueError("use --reuse-results or --force")
    preflight(output)
    write_json(output/"environment.json",dict(python=platform.python_version(),platform=platform.platform(),
               packages={p:importlib.metadata.version(p) for p in ("numpy","pandas","matplotlib","simpy","scipy")}))
    rows=[];checks=[];execution_start=time.perf_counter()
    old=pd.read_csv(ROOT/"results/joint_routing_30seeds/raw_policy_results.csv").set_index(["seed","policy"])
    for scale in SCALES:
        c=configuration(scale)
        (output/"inputs"/scale).mkdir(parents=True,exist_ok=True)
        for seed in seeds:
            w=generate_workload(c,seed);summary=workload_summary(scale,c,w)
            fingerprint,tape=summary["workload_hash"],summary["traffic_hash"]
            write_gzip(output/"inputs"/scale/f"seed_{seed:03d}.json.gz",w.to_dict())
            for policy in POLICIES:
                gc.collect()
                with MemoryMonitor() as memory:
                    engine=MeasuredBaseline(c,w,"sla_aware") if policy=="sla_aware" else MeasuredRouted(c,w,policy,Settings())
                    result=engine.run()
                check=validate_run(c,w,result)
                legacy,slots,nodes,outcomes=calculate_metrics(c,w,result)
                m=augment_metrics(c,w,result,legacy,outcomes,slots,nodes)
                m.update(baseline_metrics(result) if policy=="sla_aware" else extra_metrics(result,outcomes))
                m.update(normalized_metrics(m,c,result["timing"],len(result["routing"])))
                m.update(sampled_peak_process_rss_mib=memory.peak,initial_process_rss_mib=memory.initial,
                         routing_instrumented=policy!="sla_aware",N_nodes=c.node_count,N_services=c.service_count,
                         mean_active_replicas=m["average_eligible_replicas"])
                # Heterogeneous per-node fields remain in node trajectories, not padded wide columns.
                m={k:v for k,v in m.items() if "utilization_node_" not in k}
                assert np.isfinite([v for v in m.values() if isinstance(v,(float,int))]).all()
                if scale=="SMALL":
                    historic=old.loc[(seed,policy)]
                    assert historic.workload_hash==fingerprint and historic.traffic_hash==tape
                    for metric in ("sla_breach_rate","mean_request_latency_ms","median_latency_ms","p95_latency_ms","p99_latency_ms","average_replicas","mean_gpu_vram_reserved_pct","total_actions"):
                        assert np.isclose(m[metric],historic[metric],atol=1e-9,rtol=0),(seed,policy,metric)
                row=dict(scale=scale,seed=seed,policy=policy,workload_hash=fingerprint,traffic_hash=tape,**m)
                rows.append(row);checks.append(dict(scale=scale,seed=seed,policy=policy,**check))
                export_run(output/"runs"/scale/f"seed_{seed:03d}"/policy,result,slots,nodes,outcomes)
                pd.DataFrame(rows).to_csv(output/"progress_results.csv",index=False)
                print(f"{scale} seed {seed:02d} {policy}: {len(w.requests):,} requests, {m['wall_clock_seconds']:.2f}s, RSS {memory.peak:.0f} MiB",flush=True)
                del result,engine,outcomes,nodes,slots
            assert digest(w.to_dict())==fingerprint
    raw=pd.DataFrame(rows)
    for _,g in raw.groupby(["scale","seed"]):
        assert g.workload_hash.nunique()==g.traffic_hash.nunique()==g.total_requests.nunique()==1
    assert raw.groupby(["scale","policy"]).size().eq(len(seeds)).all()
    raw.to_csv(output/"raw_results.csv",index=False)
    write_json(output/"simulation_validation.json",dict(successful_runs=len(raw),requests_checked=int(raw.total_requests.sum()),
               per_run_checks=checks,wall_execution_seconds=time.perf_counter()-execution_start))
    if pilot:
        assert raw.wall_clock_seconds.le(600).all() and raw.sampled_peak_process_rss_mib.le(4096).all() and raw.drain_seconds.le(120).all()
        write_json(output/"pilot_validation.json",dict(successful=True,runs=len(raw),requests_checked=int(raw.total_requests.sum()),
                   maximum_runtime_seconds=float(raw.wall_clock_seconds.max()),maximum_rss_mib=float(raw.sampled_peak_process_rss_mib.max()),
                   maximum_drain_seconds=float(raw.drain_seconds.max()),source_hashes=protocol["source_hashes"]))
    assert protected_hashes()==protocol["protected_hashes"]
    return raw
