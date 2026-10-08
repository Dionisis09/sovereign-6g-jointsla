"""Verify exported exact traces, timings, figures and protected-byte manifests."""
import gzip
import hashlib
import json
from io import StringIO
import numpy as np
import pandas as pd
from PIL import Image
from catalyst.reused import digest,write_json
from paper_evaluation.accounting import request_metrics
from scalability.configuration import ROOT,SCALES
from .reference import OUTPUT,GOLDEN,freeze_optimized,verify_protected
from .validation import RESEARCH_METRICS
from .presentation import HEADINGS,FIGURES


def verify():
    protected=verify_protected();freeze_optimized()
    g=pd.read_csv(OUTPUT/"equivalence_validation.csv")
    assert set(zip(g.scale,g.seed))=={(s,seed) for s,seeds in GOLDEN.items() for seed in seeds} and len(g)==9
    assert g["pass"].all() and g.filter(regex="_equal$").all().all()
    reference=pd.read_csv(OUTPUT/"golden_reference.csv").set_index(["scale","seed"])
    for row in g.itertuples():
        with gzip.open(OUTPUT/f"golden/{row.scale}/seed_{row.seed:03d}.json.gz","rt") as stream:trace=json.load(stream)
        assert digest(trace)==reference.loc[(row.scale,row.seed),"trace_hash"]
        for key,label in (("actions","action"),("routing","routing"),("outcomes","request_outcome"),("replica_states","replica_state")):
            assert digest(trace[key])==getattr(row,f"legacy_{label}_hash")==getattr(row,f"optimized_{label}_hash")
    full=pd.read_csv(OUTPUT/"full_30seed_equivalence.csv")
    assert len(full)==90 and set(zip(full.scale,full.seed))=={(s,seed) for s in SCALES for seed in range(1,31)}
    assert full["pass"].all() and full.filter(regex="_equal$").all().all()
    research=pd.read_csv(OUTPUT/"optimized_research_metrics.csv",float_precision="round_trip").set_index(["scale","seed"])
    frozen=pd.read_csv(ROOT/"results/scalability_30seeds/raw_results.csv",float_precision="round_trip").set_index(["scale","seed","policy"])
    differences=pd.read_csv(OUTPUT/"metric_representation_differences.csv",float_precision="round_trip")
    assert not differences.duplicated(["scale","seed","metric"]).any()
    differences=differences.set_index(["scale","seed","metric"])
    mismatches=0;requests=0;assignments=0
    for row in full.itertuples():
        new=OUTPUT/f"optimized_runs/{row.scale}/seed_{row.seed:03d}"
        old=ROOT/f"results/scalability_30seeds/runs/{row.scale}/seed_{row.seed:03d}/joint_sla"
        for name in ("request_outcomes","routing_decisions","slot_trajectories","node_trajectories","actions",
                     "reservation_events","lifecycle_events","deployment_audit","routing_attempts"):
            a=pd.read_csv(old/f"{name}.csv.gz",float_precision="round_trip")
            b=pd.read_csv(new/f"{name}.csv.gz",float_precision="round_trip")
            for timer in ("runtime_ms","decision_runtime_ms"):
                a=a.drop(columns=[timer],errors="ignore");b=b.drop(columns=[timer],errors="ignore")
            pd.testing.assert_frame_equal(a,b,check_exact=True,check_dtype=True)
            assert hashlib.sha256(b.to_csv(index=False).encode()).hexdigest()==getattr(row,name+"_hash")
            if name=="request_outcomes":
                assert len(b)==row.requests_verified and not b.request_id.duplicated().any()
                requests+=len(b)
                computed=request_metrics(b)
                for metric in ("sla_breach_rate","mean_request_latency_ms","median_latency_ms","p95_latency_ms","p99_latency_ms",
                               "Gold_breach_rate","Silver_breach_rate","Bronze_breach_rate","sla_breaches","completed_requests"):
                    assert computed[metric]==research.loc[(row.scale,row.seed),metric]
            if name=="routing_decisions":assignments+=len(b)
        for metric in RESEARCH_METRICS:
            value=research.loc[(row.scale,row.seed),metric];historic=frozen.loc[(row.scale,row.seed,"joint_sla"),metric]
            if value!=historic:
                mismatch=differences.loc[(row.scale,row.seed,metric)];mismatches+=1
                assert value==mismatch.fresh_legacy_value==mismatch.optimized_value
                assert historic==mismatch.frozen_summary_value
                parsed=value
                for _ in range(int(mismatch.default_csv_roundtrips_reproducing_difference)):
                    parsed=pd.read_csv(StringIO(pd.DataFrame({"value":[parsed]}).to_csv(index=False))).value.iloc[0]
                assert parsed==historic
        print(f"Audit exact exports: {row.scale} seed {row.seed:02d}/30",flush=True)
    assert mismatches==len(differences)
    perf=pd.read_csv(OUTPUT/"controller_performance_before_after.csv",float_precision="round_trip").set_index("scale")
    inv=pd.read_csv(OUTPUT/"controller_benchmark_invocations.csv",float_precision="round_trip")
    routing=pd.read_csv(OUTPUT/"routing_benchmark_attempts.csv.gz",float_precision="round_trip")
    assert len(inv)==4200 and inv.full_controller_ms.gt(0).all()
    for scale in SCALES:
        for mode in ("legacy","optimized"):
            f=inv[(inv.scale==scale)&(inv.implementation==mode)]
            assert len(f)==700 and f.groupby("repetition").size().eq(100).all()
            assert np.array_equal(f.full_controller_ms.to_numpy(),(f.snapshot_ms+f.policy_apply_ms).to_numpy())
            for label,col in (("full_controller","full_controller_ms"),("snapshot","snapshot_ms"),("policy_apply","policy_apply_ms")):
                for stat,value in (("mean",f[col].mean()),("median",f[col].median()),("p95",f[col].quantile(.95))):
                    assert value==perf.loc[scale,f"{mode}_{label}_{stat}_ms"]
            r=routing[(routing.scale==scale)&(routing.implementation==mode)]
            assert r.runtime_ms.mean()==perf.loc[scale,f"{mode}_routing_mean_ms"]
            assert r.runtime_ms.quantile(.95)==perf.loc[scale,f"{mode}_routing_p95_ms"]
        for label in ("full_controller","snapshot"):
            a=perf.loc[scale,f"legacy_{label}_mean_ms"];b=perf.loc[scale,f"optimized_{label}_mean_ms"]
            assert a/b==perf.loc[scale,f"speedup_{label}"] and 100*(1-b/a)==perf.loc[scale,f"percent_reduction_{label}"]
    times=pd.read_csv(OUTPUT/"optimized_full_validation_timings.csv",float_precision="round_trip")
    h4=pd.read_csv(OUTPUT/"h4_reassessment.csv",float_precision="round_trip").set_index("scale")
    for scale in SCALES:
        f=times[times.scale==scale];expected=[]
        for row in f.itertuples():
            p=OUTPUT/f"optimized_runs/{scale}/seed_{row.seed:03d}"
            slot=pd.read_csv(p/"slot_trajectories.csv.gz",float_precision="round_trip").decision_runtime_ms
            snap=pd.read_csv(p/"control_snapshot_times.csv.gz",float_precision="round_trip").runtime_ms
            total=slot+snap
            assert total.mean()==row.controller_total_instrumented_mean_ms and total.quantile(.95)==row.controller_total_instrumented_p95_ms
        mean=f.controller_total_instrumented_mean_ms.mean();tail=f.controller_total_instrumented_p95_ms.mean();route=f.request_routing_decision_p95_ms.mean()
        assert mean==h4.loc[scale,"full_30seed_controller_mean_ms"] and tail==h4.loc[scale,"full_30seed_mean_controller_p95_ms"]
        assert route==h4.loc[scale,"full_30seed_mean_routing_p95_ms"]
        assert bool(h4.loc[scale,"supported"])==bool(mean<10 and tail<=100 and route<=1 and perf.loc[scale,"optimized_full_controller_mean_ms"]<10)
    state=json.loads((OUTPUT/"h4_reassessment.json").read_text())
    assert state["H4"]==("SUPPORTED" if h4.supported.all() else "NOT SUPPORTED")
    report=(OUTPUT/"report.md").read_text(encoding="utf-8")
    assert all("# "+heading in report for heading in HEADINGS) and state["H4"] in report
    for name in FIGURES:
        for extension in ("png","svg","pdf"):assert (OUTPUT/f"figures/{name}.{extension}").stat().st_size>1000
        with Image.open(OUTPUT/f"figures/{name}.png") as img:assert all(d>=299 for d in img.info["dpi"])
    protected=verify_protected()
    status=dict(golden_runs=9,full_optimized_runs=90,fresh_legacy_reference_runs=90,
                requests_verified=requests,routing_decisions_verified=assignments,exact_audit_families=9,
                tolerance_used=False,summary_parser_differences_reproduced=mismatches,
                protected_files_unchanged=protected,H4=state["H4"],figures_verified=5,benchmark_invocations_verified=len(inv))
    write_json(OUTPUT/"final_audit.json",status)
    write_json(OUTPUT/"delivery_source_hashes.json",{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in [*(ROOT/"controller_optimization").glob("*.py"),ROOT/"run_controller_optimization.py",ROOT/"tools/verify_controller_optimization.py",ROOT/"tests/test_controller_optimization.py"]})
    write_json(OUTPUT/"artifact_hashes.json",{p.relative_to(OUTPUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(OUTPUT.rglob("*")) if p.is_file() and p.name!="artifact_hashes.json"})
    return status
