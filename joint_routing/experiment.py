"""New routing experiments with read-only verified paper baselines."""
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json,write_gzip
from dynamic_placement.workload import generate_workload
from dynamic_placement.scenario_model import traffic_hash_payload
from dynamic_placement.metrics import calculate_metrics,validate_run
from paper_evaluation.accounting import augment_metrics,POLICIES as OLD_POLICIES
from paper_evaluation.experiments import ROOT,engine_hashes,tag
from .router import NEW_POLICIES,Settings
from .simulator import RoutedSimulator

ALL_POLICIES=(*OLD_POLICIES,*NEW_POLICIES)


def protected_hashes():
    paths=[*(ROOT/"results/paper_30seeds").rglob("*"),*(ROOT/"paper_evaluation").glob("*.py"),
           ROOT/"run_paper_experiments.py",ROOT/"requirements-paper.txt"]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def source_hashes():
    return {p.relative_to(ROOT).as_posix():digest(p.read_text(encoding="utf-8"))
            for p in sorted([*(ROOT/"joint_routing"/name for name in ("__init__.py","router.py","controller.py","simulator.py","experiment.py")),ROOT/"run_joint_routing.py"])}


def baseline(config,seeds):
    folder=ROOT/"results/paper_30seeds"
    protocol=json.loads((folder/"simulation_protocol.json").read_text(encoding="utf-8"))
    assert protocol["source_hashes"]==engine_hashes()
    assert protocol["config_hash"]==digest(asdict(config)) and protocol["seeds"]==list(seeds)
    manifest=json.loads((folder/"artifact_hashes.json").read_text(encoding="utf-8"))
    for path,fingerprint in manifest.items():
        assert hashlib.sha256((folder/path).read_bytes()).hexdigest()==fingerprint,path
    return pd.read_csv(folder/"raw_policy_results.csv")


def extra_metrics(result,outcomes):
    routing=pd.DataFrame(result["routing"])
    attempts=pd.DataFrame(result["routing_attempts"])
    first=routing.sort_values("time_s",kind="stable").drop_duplicates("request_id")
    mean_imbalance=[]
    for sid,group in outcomes.groupby("service_id"):
        allocated=[rid for rid,service in result["replica_services"].items() if service==sid]
        counts=group.replica_id.value_counts().reindex(allocated,fill_value=0).to_numpy(dtype=float)
        if len(counts):
            mean_imbalance.append(float(counts.std()/counts.mean()))
    snapshot_times=pd.DataFrame(result["control_snapshot_times"]).set_index("slot").runtime_ms
    total=pd.DataFrame(result["slots"]).set_index("slot").decision_runtime_ms+snapshot_times
    return dict(controller_total_instrumented_mean_ms=float(total.mean()),controller_total_instrumented_p95_ms=float(total.quantile(.95)),
                controller_snapshot_mean_ms=float(snapshot_times.mean()),
                controller_decision_mean_ms=float(pd.DataFrame(result["slots"]).decision_runtime_ms.mean()),
                controller_decision_p95_ms=float(pd.DataFrame(result["slots"]).decision_runtime_ms.quantile(.95)),
                request_routing_decision_mean_ms=float(attempts.runtime_ms.mean()),
                request_routing_decision_p95_ms=float(attempts.runtime_ms.quantile(.95)),
                routing_computation_per_request_ms=float(attempts.runtime_ms.sum()/len(outcomes)),
                routing_attempts=len(attempts),routing_assignments=len(routing),
                routing_no_eligible_attempts=int((~attempts.success).sum()),
                routed_away_from_lowest_network_fraction=float(first.routed_away_from_lowest_network.mean()),
                queue_changed_choice_fraction=float(first.queue_changed_choice.mean()),
                multi_eligible_fraction=float((first.eligible_count>1).mean()),
                mean_per_service_replica_request_cv=float(np.mean(mean_imbalance)))


def run(config,seeds,output,settings,reuse=False,force=False):
    output.mkdir(parents=True,exist_ok=True)
    protected=protected_hashes()
    old=baseline(config,seeds)
    if reuse:
        protocol=json.loads((output/"protocol.json").read_text(encoding="utf-8"))
        assert protocol["engine_sources"]==engine_hashes() and protocol["new_sources"]==source_hashes()
        assert protocol["protected_baseline_hashes"]==protected
        assert protocol["config"]==asdict(config) and protocol["settings"]==asdict(settings)
        return pd.read_csv(output/"raw_policy_results.csv")
    if (output/"raw_policy_results.csv").exists() and not force:
        raise ValueError("outputs exist; use --reuse-results or --force")
    write_json(output/"protocol.json",dict(config=asdict(config),settings=asdict(settings),seeds=list(seeds),
               engine_sources=engine_hashes(),new_sources=source_hashes(),protected_baseline_hashes=protected,
               baseline_runs_reused=120,new_runs_planned=150,policies=list(ALL_POLICIES),
               primary_comparisons="JointSLA vs SLA-aware, RR, ShortestQueue; four metrics; Holm family=12",
               exploratory_ablation_family=8,bootstrap_resamples=10000,
               hypotheses="H1/H2 Holm p<.05 and positive paired lower CI; H3 p99 relative CI lower>=-5%; H4 H1/H2 plus upper replica increase<=5% and VRAM<=2pp; H5 controller mean<=10ms, routing p95<=1ms",
               predeclared_document_hash=digest((ROOT/"joint_routing/README.md").read_text(encoding="utf-8"))))
    (output/"inputs").mkdir(exist_ok=True)
    frames={name:[] for name in ("slots","nodes","actions","reservations","lifecycle","deployment_audit","routing_attempts","control_snapshot_times")}
    rows=[];checks=[]
    with (gzip.GzipFile(filename=str(output/"request_outcomes.csv.gz"),mode="wb",mtime=0) as requests,
          gzip.GzipFile(filename=str(output/"routing_decisions.csv.gz"),mode="wb",mtime=0) as decisions):
        request_header=decision_header=True
        for seed in seeds:
            workload=generate_workload(config,seed)
            fingerprint=digest(workload.to_dict());traffic=digest(traffic_hash_payload(workload))
            historic=old.loc[old.seed==seed]
            assert historic.workload_hash.eq(fingerprint).all() and historic.traffic_hash.eq(traffic).all()
            write_gzip(output/"inputs"/f"seed_{seed:03d}.json.gz",workload.to_dict())
            for policy in NEW_POLICIES:
                result=RoutedSimulator(config,workload,policy,settings).run()
                check=validate_run(config,workload,result)
                checks.append(dict(seed=seed,policy=policy,**check))
                legacy,slots,nodes,outcomes=calculate_metrics(config,workload,result)
                metrics=augment_metrics(config,workload,result,legacy,outcomes,slots,nodes)
                metrics.update(extra_metrics(result,outcomes))
                rows.append(dict(seed=seed,policy=policy,workload_hash=fingerprint,traffic_hash=traffic,
                                 routing_instrumented=True,**metrics))
                requests.write(tag(outcomes,seed,policy,fingerprint,traffic).to_csv(index=False,header=request_header).encode("utf-8"));request_header=False
                decisions.write(tag(pd.DataFrame(result["routing"]),seed,policy,fingerprint,traffic).to_csv(index=False,header=decision_header).encode("utf-8"));decision_header=False
                for name in frames:
                    if result[name]:
                        frames[name].append(tag(pd.DataFrame(result[name]),seed,policy,fingerprint,traffic))
            assert digest(workload.to_dict())==fingerprint
            print(f"Seed {seed}: five new policies, {len(workload.requests):,} identical requests each",flush=True)
    new=pd.DataFrame(rows)
    new.to_csv(output/"new_policy_results.csv",index=False)
    extra=[c for c in new if c not in old]
    old=old.copy()
    for col in extra:
        old[col]=False if col=="routing_instrumented" else 0.
    old["controller_decision_mean_ms"]=old.decision_runtime_mean_ms
    base_slots=pd.read_csv(ROOT/"results/paper_30seeds/slot_trajectories.csv")
    ctl=base_slots.groupby(["seed","policy"]).decision_runtime_ms.quantile(.95)
    old["controller_decision_p95_ms"]=[ctl.loc[(r.seed,r.policy)] for r in old.itertuples()]
    raw=pd.concat([old,new],ignore_index=True,sort=False)
    assert np.isfinite(raw.select_dtypes(include="number").to_numpy()).all()
    raw.to_csv(output/"raw_policy_results.csv",index=False)
    names=dict(slots="slot_trajectories",nodes="node_trajectories",reservations="reservation_events",lifecycle="lifecycle_events")
    for name,data in frames.items():
        frame=pd.concat(data,ignore_index=True) if data else pd.DataFrame(columns=["seed","policy","kind"])
        frame.to_csv(output/f"{names.get(name,name)}.csv",index=False)
    routing_columns=["seed","policy","routed_away_from_lowest_network_fraction","queue_changed_choice_fraction","multi_eligible_fraction",
                     "mean_per_service_replica_request_cv","routing_attempts","routing_assignments","routing_no_eligible_attempts"]
    new[routing_columns].to_csv(output/"routing_analysis.csv",index=False)
    write_json(output/"simulation_validation.json",dict(new_successful_runs=len(new),combined_runs=len(raw),per_run_checks=checks))
    assert protected_hashes()==protected
    return raw
