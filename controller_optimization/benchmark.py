"""Repeated, unprofiled, alternating-order replay benchmark; no file I/O in timers."""
import gc
import tracemalloc
import platform
from time import perf_counter_ns
import numpy as np
import pandas as pd
from catalyst.reused import write_json
from dynamic_placement.workload import generate_workload
from scalability.configuration import SCALES,configuration
from scalability.measurement import MeasuredRouted,MemoryMonitor
from .reference import OUTPUT,verify_protected,freeze_optimized
from .optimized import OptimizedMeasured

REPETITIONS=7


def samples(result,scale,implementation,repetition):
    snap={r["slot"]:r["runtime_ms"] for r in result["control_snapshot_times"]}
    rows=[]
    for row in result["slots"]:
        t=result["timing"]["control_cpu_times"][row["slot"]]
        rows.append(dict(scale=scale,implementation=implementation,repetition=repetition,slot=row["slot"],
             snapshot_ms=snap[row["slot"]],policy_apply_ms=row["decision_runtime_ms"],
             full_controller_ms=snap[row["slot"]]+row["decision_runtime_ms"],
             snapshot_cpu_ms=t["snapshot_cpu_ms"],policy_cpu_ms=t["policy_cpu_ms"],apply_cpu_ms=t["apply_cpu_ms"]))
    return rows


def benchmark():
    freeze_optimized()
    g=pd.read_csv(OUTPUT/"equivalence_validation.csv")
    assert len(g)==9 and g["pass"].all(),"exact golden equivalence required before benchmark"
    rows=[];routing=[];runs=[]
    classes={"legacy":MeasuredRouted,"optimized":OptimizedMeasured}
    for scale in SCALES:
        c=configuration(scale);w=generate_workload(c,1)
        for name,engine_class in classes.items():
            engine=engine_class(c,w,"joint_sla");engine.run();del engine;gc.collect()
            print(f"Benchmark warm-up: {scale} {name}",flush=True)
        for repetition in range(REPETITIONS):
            order=("legacy","optimized") if repetition%2==0 else ("optimized","legacy")
            for name in order:
                gc.collect()
                with MemoryMonitor() as memory:
                    init=perf_counter_ns();engine=classes[name](c,w,"joint_sla");initialization_ms=(perf_counter_ns()-init)/1e6
                    result=engine.run()
                rows.extend(samples(result,scale,name,repetition))
                routing.extend(dict(scale=scale,implementation=name,repetition=repetition,runtime_ms=r["runtime_ms"])
                               for r in result["routing_attempts"])
                runs.append(dict(scale=scale,implementation=name,repetition=repetition,
                     wall_clock_seconds=result["timing"]["wall_clock_seconds"],initialization_ms=initialization_ms,
                     sampled_peak_process_rss_mib=memory.peak,initial_process_rss_mib=memory.initial,
                     requests=len(result["outcomes"])))
                print(f"Benchmark: {scale} repetition {repetition+1}/{REPETITIONS} {name} complete",flush=True)
                del result,engine
    frame=pd.DataFrame(rows);route=pd.DataFrame(routing);runframe=pd.DataFrame(runs)
    frame.to_csv(OUTPUT/"controller_benchmark_invocations.csv",index=False)
    route.to_csv(OUTPUT/"routing_benchmark_attempts.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    runframe.to_csv(OUTPUT/"benchmark_runs.csv",index=False)
    pairs=[]
    for scale in SCALES:
        row=dict(scale=scale)
        for name in classes:
            f=frame[(frame.scale==scale)&(frame.implementation==name)]
            r=route[(route.scale==scale)&(route.implementation==name)]
            for label,column in (("full_controller","full_controller_ms"),("snapshot","snapshot_ms"),("policy_apply","policy_apply_ms")):
                for stat,value in (("mean",f[column].mean()),("median",f[column].median()),("p95",f[column].quantile(.95))):
                    row[f"{name}_{label}_{stat}_ms"]=float(value)
            row[f"{name}_routing_mean_ms"]=float(r.runtime_ms.mean())
            row[f"{name}_routing_p95_ms"]=float(r.runtime_ms.quantile(.95))
            row[f"{name}_controller_invocations"]=len(f)
        for label in ("full_controller","snapshot"):
            a,b=row[f"legacy_{label}_mean_ms"],row[f"optimized_{label}_mean_ms"]
            row[f"speedup_{label}"]=a/b
            row[f"percent_reduction_{label}"]=100*(1-b/a)
        pairs.append(row)
    pd.DataFrame(pairs).to_csv(OUTPUT/"controller_performance_before_after.csv",index=False)
    write_json(OUTPUT/"benchmark_protocol.json",dict(warmup_full_runs_per_scale_implementation=1,
        repetitions=REPETITIONS,slots_per_replay=100,seed=1,invocations_per_scale_implementation=700,
        order="alternating legacy/optimized",timers="perf_counter_ns; snapshot + policy/application",
        includes="live snapshot observation, unchanged policy computation and actual action application",
        excludes="constructor, workload generation, cProfile, trace capture, CSV/JSON output and plots",
        full_controller_scope="one control invocation; request routing measured separately; no double counting",
        aggregation="pooled 700 invocations per scale/implementation; mean, median and linear p95",
        cpu="process_time_ns; Windows quantization; CPU phases not substituted for wall breakdown",
        python=platform.python_version(),platform=platform.platform()))
    verify_protected()


def memory_profile():
    """Optional traced Python memory: initial control snapshot, measured separately."""
    rows=[]
    for scale in SCALES:
        c=configuration(scale);w=generate_workload(c,1);row=dict(scale=scale)
        for name,klass in (("legacy",MeasuredRouted),("optimized",OptimizedMeasured)):
            gc.collect();tracemalloc.start()
            engine=klass(c,w,"joint_sla");engine.prepare_timing()
            retained,_=tracemalloc.get_traced_memory();tracemalloc.reset_peak()
            snapshot=engine.snapshot();current,peak=tracemalloc.get_traced_memory()
            row[f"{name}_peak_mb"]=peak/1e6
            row[f"{name}_retained_before_snapshot_mb"]=retained/1e6
            row[f"{name}_snapshot_extra_peak_mb"]=(peak-retained)/1e6
            del snapshot,engine;tracemalloc.stop()
        row["scope"]="initial control snapshot including constructor-retained Python state; decimal MB; separate from timing"
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUTPUT/"memory_profile.csv",index=False)


def reassess_h4():
    """Only H4; keep the original 10ms/100ms/1ms screens fixed."""
    timing=pd.read_csv(OUTPUT/"optimized_full_validation_timings.csv",float_precision="round_trip")
    bench=pd.read_csv(OUTPUT/"controller_performance_before_after.csv",float_precision="round_trip").set_index("scale")
    rows=[]
    for scale in SCALES:
        f=timing[timing.scale==scale]
        assert len(f)==30
        mean=f.controller_total_instrumented_mean_ms.mean()
        p95=f.controller_total_instrumented_p95_ms.mean()
        routing=f.request_routing_decision_p95_ms.mean()
        row=dict(scale=scale,full_30seed_controller_mean_ms=mean,
             full_30seed_mean_controller_p95_ms=p95,full_30seed_mean_routing_p95_ms=routing,
             benchmark_controller_mean_ms=bench.loc[scale,"optimized_full_controller_mean_ms"],
             limit_controller_mean_ms=10.,limit_controller_p95_ms=100.,limit_routing_p95_ms=1.,
             reached_under_10ms=bool(mean<10),
             supported=bool(mean<10 and p95<=100 and routing<=1 and bench.loc[scale,"optimized_full_controller_mean_ms"]<10))
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUTPUT/"h4_reassessment.csv",index=False)
    write_json(OUTPUT/"h4_reassessment.json",dict(H4="SUPPORTED" if all(r["supported"] for r in rows) else "NOT SUPPORTED",
         timing_only_reassessment=True,H1_H2_H3_H5="unchanged verified conclusions; not re-evaluated",
         no_post_outcome_threshold_changes=True))
    return rows
