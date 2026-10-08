"""Exact golden traces and full replay against read-only verified exports."""
import gc
import gzip
import json
import hashlib
from io import StringIO
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json
from dynamic_placement.metrics import calculate_metrics,validate_run
from dynamic_placement.scenario_model import traffic_hash_payload
from dynamic_placement.workload import generate_workload
from paper_evaluation.accounting import augment_metrics
from joint_routing.experiment import extra_metrics
from scalability.configuration import ROOT,SCALES,configuration
from scalability.experiment import export_run
from scalability.measurement import MemoryMonitor
from scalability.measurement import MeasuredRouted
from .reference import OUTPUT,GOLDEN,Capture,traces,verify_protected,freeze_optimized
from .optimized import OptimizedMeasured


class GoldenOptimized(Capture,OptimizedMeasured):
    def __init__(self,*args,**kwargs):
        self.captured_snapshots=[]
        super().__init__(*args,**kwargs)


def golden_equivalence():
    freeze_optimized()
    reference=pd.read_csv(OUTPUT/"golden_reference.csv").set_index(["scale","seed"])
    rows=[]
    for scale,seeds in GOLDEN.items():
        c=configuration(scale)
        for seed in seeds:
            w=generate_workload(c,seed);engine=GoldenOptimized(c,w,"joint_sla");result=engine.run()
            validate_run(c,w,result)
            with gzip.open(OUTPUT/"golden"/scale/f"seed_{seed:03d}.json.gz","rt") as stream:old=json.load(stream)
            new=traces(result,engine.captured_snapshots)
            row=dict(scale=scale,seed=seed,traffic_hash_equal=digest(traffic_hash_payload(w))==reference.loc[(scale,seed),"traffic_hash"])
            for key,label in (("actions","action"),("routing","routing"),("outcomes","request_outcome"),("replica_states","replica_state")):
                row[f"{label}_hash_equal"]=digest(old[key])==digest(new[key])
                row[f"legacy_{label}_hash"]=digest(old[key]);row[f"optimized_{label}_hash"]=digest(new[key])
            row["all_observable_fields_equal"]=old==new
            row["requests_verified"]=len(result["outcomes"])
            row["pass"]=bool(row["all_observable_fields_equal"] and all(v for k,v in row.items() if k.endswith("_equal")))
            assert row["pass"],f"INVALID optimization: {scale} seed {seed} differs"
            rows.append(row);pd.DataFrame(rows).to_csv(OUTPUT/"equivalence_validation.csv",index=False)
            print(f"Golden exact: {scale} seed {seed} PASS",flush=True)
            del old,new,engine,result;gc.collect()
    verify_protected()
    return rows


FRAME_FIELDS={"request_outcomes":"outcomes","routing_decisions":"routing","slot_trajectories":"slots",
              "node_trajectories":"nodes","actions":"actions","reservation_events":"reservations",
              "lifecycle_events":"lifecycle","deployment_audit":"deployment_audit","routing_attempts":"routing_attempts"}
RESEARCH_METRICS=("sla_breach_rate","mean_request_latency_ms","median_latency_ms","p95_latency_ms","p99_latency_ms",
    "Gold_breach_rate","Silver_breach_rate","Bronze_breach_rate","average_replicas","peak_replicas",
    "average_cpu_utilization","average_gpu_utilization","mean_gpu_vram_reserved_pct","vram_gb_seconds",
    "cold_starts","scale_outs","scale_ins","migrations","total_actions","replica_seconds",
    "completed_requests","total_requests","dropped_requests","sla_breaches")


def exact_export_comparison(folder,result,slots,nodes,outcomes):
    """Round-trip parsing prevents decimal-reader approximation; no tolerances."""
    frames={name:pd.DataFrame(result[field]) for name,field in FRAME_FIELDS.items()}
    frames.update(request_outcomes=outcomes,slot_trajectories=slots,node_trajectories=nodes)
    hashes={}
    for name,frame in frames.items():
        old=pd.read_csv(folder/f"{name}.csv.gz",float_precision="round_trip")
        if frame.empty:frame=pd.DataFrame(columns=["empty"])
        for timer in ("runtime_ms","decision_runtime_ms"):
            old=old.drop(columns=[timer],errors="ignore");frame=frame.drop(columns=[timer],errors="ignore")
        pd.testing.assert_frame_equal(old,frame,check_exact=True,check_dtype=True)
        # Both canonical frames include identical columns, ordering and floats.
        serialized=frame.to_csv(index=False).encode()
        hashes[name]=hashlib.sha256(serialized).hexdigest()
    return hashes


def full_validation():
    freeze_optimized()
    g=pd.read_csv(OUTPUT/"equivalence_validation.csv")
    assert len(g)==9 and g["pass"].all(),"all golden seeds must pass first"
    old=pd.read_csv(ROOT/"results/scalability_30seeds/raw_results.csv",float_precision="round_trip").set_index(["scale","seed","policy"])
    rows=[];timings=[];metric_rows=[];representations=[]
    for scale in SCALES:
        c=configuration(scale)
        for seed in range(1,31):
            w=generate_workload(c,seed)
            # Fresh unchanged reference additionally proves exact floating
            # computation paths. Frozen summaries have traversed the legacy
            # default CSV parser; raw gzip audit frames remain authoritative.
            original=MeasuredRouted(c,w,"joint_sla").run()
            with MemoryMonitor() as memory:
                engine=OptimizedMeasured(c,w,"joint_sla");result=engine.run()
            validate_run(c,w,result)
            assert traces(original,[])==traces(result,[]),(scale,seed,"fresh legacy trace differs")
            legacy,slots,nodes,outcomes=calculate_metrics(c,w,result)
            metrics=augment_metrics(c,w,result,legacy,outcomes,slots,nodes)
            metrics.update(extra_metrics(result,outcomes))
            old_legacy,old_slots,old_nodes,old_outcomes=calculate_metrics(c,w,original)
            old_metrics=augment_metrics(c,w,original,old_legacy,old_outcomes,old_slots,old_nodes)
            historical=old.loc[(scale,seed,"joint_sla")]
            assert digest(traffic_hash_payload(w))==historical.traffic_hash and digest(w.to_dict())==historical.workload_hash
            for key in RESEARCH_METRICS:
                assert metrics[key]==old_metrics[key],(scale,seed,key,"INVALID changed computation")
                if metrics[key]!=historical[key]:
                    # Accept no tolerance: reproduce the precise old decimal
                    # parser transformation, otherwise reject the optimization.
                    parsed=metrics[key];steps=None
                    for step in range(1,5):
                        parsed=pd.read_csv(StringIO(pd.DataFrame({"value":[parsed]}).to_csv(index=False))).value.iloc[0]
                        if parsed==historical[key]:steps=step;break
                    assert steps is not None,(scale,seed,key,"unexplained frozen summary difference",metrics[key],historical[key])
                    representations.append(dict(scale=scale,seed=seed,metric=key,
                        frozen_summary_value=float(historical[key]),fresh_legacy_value=float(old_metrics[key]),
                        optimized_value=float(metrics[key]),default_csv_roundtrips_reproducing_difference=steps,
                        fresh_legacy_optimized_exact=True,raw_audit_frames_exact=True))
            reference=ROOT/f"results/scalability_30seeds/runs/{scale}/seed_{seed:03d}/joint_sla"
            hashes=exact_export_comparison(reference,result,slots,nodes,outcomes)
            dest=OUTPUT/f"optimized_runs/{scale}/seed_{seed:03d}"
            export_run(dest,result,slots,nodes,outcomes)
            write_json(dest/"semantic_trace_hashes.json",hashes)
            row=dict(scale=scale,seed=seed,traffic_hash_equal=True,action_hash_equal=True,routing_hash_equal=True,
                     request_outcome_hash_equal=True,replica_state_hash_equal=True,resource_state_equal=True,
                     research_metrics_equal=True,requests_verified=len(outcomes),routing_decisions_verified=len(result["routing"]),
                     **{f"{key}_hash":value for key,value in hashes.items()})
            row["pass"]=True;rows.append(row)
            metric_rows.append(dict(scale=scale,seed=seed,**{k:metrics[k] for k in RESEARCH_METRICS}))
            timings.append(dict(scale=scale,seed=seed,**{k:v for k,v in metrics.items() if "controller_" in k or "routing_decision_" in k},
                                wall_clock_seconds=result["timing"]["wall_clock_seconds"],sampled_peak_process_rss_mib=memory.peak,
                                initial_process_rss_mib=memory.initial,total_requests=len(outcomes)))
            pd.DataFrame(rows).to_csv(OUTPUT/"full_30seed_equivalence.csv",index=False)
            pd.DataFrame(timings).to_csv(OUTPUT/"optimized_full_validation_timings.csv",index=False)
            pd.DataFrame(metric_rows).to_csv(OUTPUT/"optimized_research_metrics.csv",index=False)
            pd.DataFrame(representations).to_csv(OUTPUT/"metric_representation_differences.csv",index=False)
            print(f"Full exact: {scale} seed {seed:02d}/30 ({len(outcomes):,} requests) PASS; full mean {metrics['controller_total_instrumented_mean_ms']:.3f}ms",flush=True)
            del engine,result,original,slots,nodes,outcomes,old_slots,old_nodes,old_outcomes;gc.collect()
    protected=verify_protected()
    write_json(OUTPUT/"validation.json",dict(golden_runs=9,full_runs=90,requests_verified=sum(r["requests_verified"] for r in rows),
               routing_decisions_verified=sum(r["routing_decisions_verified"] for r in rows),
               all_exact=True,protected_files_unchanged=protected,tolerance_used=False,timing_only_excluded=True,
               fresh_legacy_replays=90,frozen_summary_parser_representations=len(representations),
               frozen_summary_parser_differences_exactly_reproduced=True))
    return rows
