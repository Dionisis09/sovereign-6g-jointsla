"""Paired pilot/main replays; immutable baseline verification and per-run exports."""
import gc,json,time
from dataclasses import replace
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json,write_gzip
from dynamic_placement.workload import generate_workload
from dynamic_placement.scenario_model import traffic_hash_payload
from dynamic_placement.metrics import calculate_metrics,validate_run
from paper_evaluation.accounting import augment_metrics
from joint_routing.experiment import extra_metrics
from scalability.configuration import ROOT,SCALES,configuration
from scalability.measurement import MeasuredBaseline,MemoryMonitor,normalized_metrics
from scalability.experiment import export_run,baseline_metrics
from controller_optimization.validation import exact_export_comparison
from controller_optimization.reference import plain
from .protocol import OUTPUT,POLICIES,configure,verify_protected,source_hashes
from .simulator import MJO,FairJoint


def run_one(scale,seed,policy,folder):
    c=configuration(scale);w=generate_workload(c,seed)
    with MemoryMonitor() as memory:
        if policy=="mjo":engine=MJO(c,w)
        elif policy=="joint_sla":engine=FairJoint(c,w,"joint_sla")
        else:engine=MeasuredBaseline(c,w,"sla_aware")
        result=engine.run()
    validate_run(c,w,result)
    legacy,slots,nodes,outcomes=calculate_metrics(c,w,result)
    metrics=augment_metrics(c,w,result,legacy,outcomes,slots,nodes)
    if policy=="sla_aware":metrics.update(baseline_metrics(result))
    else:metrics.update(extra_metrics(result,outcomes))
    # Every primary-policy route callback uses its native batch scope; true
    # process CPU per offered request provides a common normalized denominator.
    metrics.update(normalized_metrics(metrics,c,result["timing"],len(result["routing"])))
    metrics["controller_decision_median_ms"]=float(slots.decision_runtime_ms.median())
    snapshot=pd.DataFrame(result["control_snapshot_times"]).set_index("slot").runtime_ms
    full=slots.set_index("slot").decision_runtime_ms+snapshot
    metrics["controller_full_median_ms"]=float(full.median())
    metrics["controller_ms_per_1000_requests"]=metrics["controller_cpu_ms_per_request"]*1000
    metrics["sampled_peak_process_rss_mib"]=memory.peak
    for tier in ("Gold","Silver","Bronze"):
        f=outcomes[outcomes.tier==tier];metrics[tier+"_mean_latency_ms"]=float(f.latency_ms.mean())
        metrics[tier+"_p95_latency_ms"]=float(f.latency_ms.quantile(.95))
    if policy!="mjo":
        frozen=ROOT/f"results/scalability_30seeds/runs/{scale}/seed_{seed:03d}/{policy}"
        exact_export_comparison(frozen,result,slots,nodes,outcomes)
    # Validate every committed request route against current eligible candidates.
    for row in result["routing"]:
        candidates=json.loads(row["candidates_json"])
        selected=next(x for x in candidates if x["id"]==row["replica_id"])
        assert selected["node"]==row["node"] and selected["ready"] and selected["capacity_feasible"] and not selected["pending"] and not selected["retiring"]
        # SimPy cumulative event arithmetic can differ from the pre-generated
        # timestamp in the last bit (also present in frozen JointSLA exports).
        assert row["arrival_s"]<=row["time_s"]+1e-12
    if policy=="mjo":
        last={row["request_id"]:row["replica_id"] for row in result["routing"]}
        assert all(last[row["request_id"]]==row["replica_id"] for row in result["outcomes"])
        assert result["diagnostics"]["rejected_actions"]==0,"optimizer proposed an invalid action"
    events=pd.DataFrame(result.get("solver",[]))
    for status in ("optimal","feasible","timeout","infeasible"):
        metrics["solver_"+status+"_calls"]=int(events.status.eq(status).sum()) if len(events) else 0
    metrics["solver_calls"]=len(events);metrics["solver_fallback_calls"]=int(events.fallback.sum()) if len(events) else 0
    for stat in ("mean","median","p95"):
        value=(events.runtime_ms.quantile(.95) if stat=="p95" else getattr(events.runtime_ms,stat)()) if len(events) else 0.
        metrics["solver_"+stat+"_ms"]=float(value)
    metrics["solver_total_ms"]=float(events.runtime_ms.sum()) if len(events) else 0.
    metrics["routing_batches"]=len(result.get("routing_batches",[]))
    metrics["routing_batch_assignment_operations"]=sum(len(json.loads(r["requests_json"])) for r in result.get("routing_batches",[]))
    metrics["routing_batch_wall_ms"]=sum(r["runtime_ms"] for r in result.get("routing_batches",[]))
    # Node-specific profiles are exported below. Cross-scale tables must not
    # manufacture missing-node measurements or pad them with zero utilization.
    metrics={k:v for k,v in metrics.items() if "_utilization_node_" not in k}
    export_run(folder,result,slots,nodes,outcomes)
    for name in ("solver","routing_batches"):
        f=pd.DataFrame(result.get(name,[]));f=f if len(f) else pd.DataFrame(columns=["empty"])
        f.to_csv(folder/f"{name}.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    row=dict(scale=scale,seed=seed,policy=policy,traffic_hash=digest(traffic_hash_payload(w)),workload_hash=digest(w.to_dict()),**metrics)
    signature=digest(plain(dict(outcomes=result["outcomes"],actions=result["actions"],routing=[{k:v for k,v in r.items() if k!="runtime_ms"} for r in result["routing"]],nodes=result["nodes"])))
    print(f"{scale} seed {seed:02d} {policy}: {len(outcomes):,} requests, {metrics['wall_clock_seconds']:.2f}s, controller {metrics['controller_total_instrumented_mean_ms']:.2f}ms",flush=True)
    del engine,result;gc.collect()
    return row,signature


def pilot(force=False):
    configure();path=OUTPUT/"pilot_results.csv"
    if path.exists() and (OUTPUT/"pilot_validation.json").exists() and not force:
        state=json.loads((OUTPUT/"pilot_validation.json").read_text())
        assert state["successful"] and state["source_hashes"]==source_hashes()
        return pd.read_csv(path)
    rows=[];deterministic=[];started=time.perf_counter();frozen_sources=source_hashes()
    for scale in SCALES:
        for seed in (1,2,3):
            for policy in POLICIES:
                row,signature=run_one(scale,seed,policy,OUTPUT/f"pilot/runs/{scale}/seed_{seed:03d}/{policy}")
                rows.append(row);pd.DataFrame(rows).to_csv(path,index=False)
                if policy=="mjo":
                    # A second full run tests decisions/outcomes, not only totals.
                    repeated,sig=run_one(scale,seed,policy,OUTPUT/f"pilot/determinism/{scale}/seed_{seed:03d}")
                    assert sig==signature,(scale,seed,"MJO nondeterminism")
                    deterministic.append(dict(scale=scale,seed=seed,hash_equal=True,trace_hash=signature))
    raw=pd.DataFrame(rows)
    assert raw.wall_clock_seconds.le(600).all() and raw.sampled_peak_process_rss_mib.le(4096).all()
    assert np.isfinite(raw.select_dtypes(include="number").to_numpy()).all()
    assert raw.total_requests.eq(raw.completed_requests+raw.dropped_requests+raw.unplaced_requests).all()
    assert raw.groupby(["scale","seed"]).traffic_hash.nunique().eq(1).all()
    estimates={scale:float(raw[(raw.scale==scale)&raw.policy.isin(("joint_sla","mjo"))].groupby("seed").wall_clock_seconds.sum().mean()*30) for scale in SCALES}
    assert source_hashes()==frozen_sources,"simulation sources changed during pilot"
    verify_protected()
    write_json(OUTPUT/"pilot_validation.json",dict(successful=True,deterministic=deterministic,
       completed_runs=36,wall_seconds=time.perf_counter()-started,estimated_full_seconds=estimates,
       estimated_total_seconds=sum(estimates.values()),source_hashes=source_hashes(),
       failures=int(raw.solver_timeout_calls.sum()+raw.solver_infeasible_calls.sum()),maximum_rss_mib=float(raw.sampled_peak_process_rss_mib.max())))
    return raw


def run(force=False,reuse=False):
    config=configure();path=OUTPUT/"raw_results.csv"
    if reuse:
        assert json.loads((OUTPUT/"simulation_protocol.json").read_text())["source_hashes"]==source_hashes()
        return pd.read_csv(path,float_precision="round_trip")
    if path.exists() and not force:raise ValueError("outputs exist; use --reuse-results or --force")
    status=json.loads((OUTPUT/"pilot_validation.json").read_text())
    assert status["successful"] and status["source_hashes"]==source_hashes(),"successful matching pilot required"
    for scale,value in status["estimated_full_seconds"].items():print(f"Estimated {scale}: {value/60:.2f} minutes",flush=True)
    print(f"Estimated total: {status['estimated_total_seconds']/60:.2f} minutes",flush=True)
    if status["estimated_total_seconds"]>config["full_estimated_runtime_limit_seconds"]:raise RuntimeError("four-hour estimate guard: diagnostic report needed; no automatic protocol weakening")
    write_json(OUTPUT/"simulation_protocol.json",dict(source_hashes=source_hashes(),baseline_configuration=config,paired_seeds=list(range(1,31)),new_runs=180,reused_sla_aware_runs=90))
    rows=[];started=time.perf_counter()
    old=pd.read_csv(ROOT/"results/scalability_30seeds/raw_results.csv",float_precision="round_trip")
    old=old[old.policy=="sla_aware"].copy()
    # Derive newly requested tier/timing fields from verified historical exports.
    # Solver fields are structural zeros: SLA-aware does not invoke our solver.
    for idx,oldrow in old.iterrows():
        folder=ROOT/f"results/scalability_30seeds/runs/{oldrow.scale}/seed_{int(oldrow.seed):03d}/sla_aware"
        outcomes=pd.read_csv(folder/"request_outcomes.csv.gz",float_precision="round_trip")
        slots=pd.read_csv(folder/"slot_trajectories.csv.gz",float_precision="round_trip").set_index("slot")
        snap=pd.read_csv(folder/"control_snapshot_times.csv.gz",float_precision="round_trip").set_index("slot")
        for tier in ("Gold","Silver","Bronze"):
            f=outcomes[outcomes.tier==tier]
            old.loc[idx,tier+"_mean_latency_ms"]=float(f.latency_ms.mean())
            old.loc[idx,tier+"_p95_latency_ms"]=float(f.latency_ms.quantile(.95))
        old.loc[idx,"controller_decision_median_ms"]=float(slots.decision_runtime_ms.median())
        old.loc[idx,"controller_full_median_ms"]=float((slots.decision_runtime_ms+snap.runtime_ms).median())
        old.loc[idx,"controller_ms_per_1000_requests"]=oldrow.controller_cpu_ms_per_request*1000
    for scale in SCALES:
        for seed in range(1,31):
            for policy in ("joint_sla","mjo"):
                row,_=run_one(scale,seed,policy,OUTPUT/f"runs/{scale}/seed_{seed:03d}/{policy}")
                rows.append(row);pd.DataFrame(rows).to_csv(OUTPUT/"progress_results.csv",index=False)
    new=pd.DataFrame(rows)
    for row in new.itertuples():
        reference=old[(old.scale==row.scale)&(old.seed==row.seed)].iloc[0]
        assert row.traffic_hash==reference.traffic_hash and row.workload_hash==reference.workload_hash
    # Reuse scientific SLA-aware metrics; fresh pilot timings are clearly marked
    # and never substituted for 30-seed measurements.
    for col in new:
        if col not in old:old[col]=0.
    old["timing_source"]="verified historical";new["timing_source"]="fresh fair wrappers"
    raw=pd.concat([old[new.columns],new],ignore_index=True,sort=False)
    raw.to_csv(path,index=False)
    write_json(OUTPUT/"execution.json",dict(new_runs=180,reused_runs=90,full_wall_seconds=time.perf_counter()-started,
          requests_verified=int(new.total_requests.sum()),source_hashes=source_hashes()))
    assert json.loads((OUTPUT/"simulation_protocol.json").read_text())["source_hashes"]==source_hashes()
    verify_protected()
    return raw
