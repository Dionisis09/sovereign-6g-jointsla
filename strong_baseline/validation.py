"""Reconstruct published metrics and inference from exported request/audit data."""
import hashlib,json,platform,importlib.metadata
import numpy as np
import pandas as pd
from PIL import Image
from catalyst.reused import digest,write_json
from dynamic_placement.workload import generate_workload
from dynamic_placement.scenario_model import traffic_hash_payload
from dynamic_placement.metrics import validate_run
from paper_evaluation.validation import reference_ci,reference_signed_rank,linear_quantile
from scalability.configuration import ROOT,SCALES,configuration
from .protocol import OUTPUT,POLICIES,verify_protected,source_hashes


def read(folder,name):
    return pd.read_csv(folder/f"{name}.csv.gz",float_precision="round_trip")


def audit_run(row,w,c):
    """All requests, latency components, physical reservations and lifecycle events."""
    folder=(ROOT/"results/scalability_30seeds" if row.policy=="sla_aware" else OUTPUT)/f"runs/{row.scale}/seed_{row.seed:03d}/{row.policy}"
    frames={n:read(folder,n) for n in ("request_outcomes","slot_trajectories","node_trajectories","actions","reservation_events","lifecycle_events")}
    result={key:([] if "empty" in frames[name] else frames[name].to_dict("records")) for name,key in
            (("request_outcomes","outcomes"),("slot_trajectories","slots"),("node_trajectories","nodes"),("actions","actions"),("reservation_events","reservations"),("lifecycle_events","lifecycle"))}
    for outcome in result["outcomes"]:
        if not outcome["unplaced"]:outcome["node"]=int(outcome["node"])
    validate_run(c,w,result)
    f=frames["request_outcomes"];slots=frames["slot_trajectories"];nodes=frames["node_trajectories"]
    assert len(f)==f.request_id.nunique()==row.total_requests==len(w.requests)
    assert len(f)==row.completed_requests+row.unplaced_requests+row.dropped_requests
    assert row.completed_requests==f.latency_ms.count() and row.sla_breaches==f.breach.sum()
    assert np.isclose(row.sla_breach_rate,f.breach.mean(),rtol=0,atol=1e-13)
    lat=f.latency_ms.dropna().to_numpy()
    assert np.isclose(row.mean_request_latency_ms,lat.mean())
    for metric,p in (("median_latency_ms",.5),("p95_latency_ms",.95),("p99_latency_ms",.99)):
        assert np.isclose(getattr(row,metric),linear_quantile(lat,p),rtol=0,atol=1e-8)
    for tier in ("Gold","Silver","Bronze"):
        tf=f[f.tier==tier];tl=tf.latency_ms.dropna().to_numpy()
        assert len(tf)==getattr(row,tier+"_requests") and tf.breach.sum()==getattr(row,tier+"_breaches")
        assert np.isclose(tf.breach.mean(),getattr(row,tier+"_breach_rate"))
        assert np.isclose(tl.mean(),getattr(row,tier+"_mean_latency_ms"))
        assert np.isclose(linear_quantile(tl,.95),getattr(row,tier+"_p95_latency_ms"))
    assert slots.accepted_actions.sum()==row.total_actions
    assert slots.accepted_actions.le(c.action_budget).all()
    assert len(result["actions"])==row.total_actions
    assert sum(e["kind"]=="cold_start" for e in result["lifecycle"])==row.cold_starts
    assert max(slots.replicas.max(),sum(n is not None for n in w.initial.values()))==row.peak_replicas
    a=frames["actions"]
    if len(result["actions"]):
        assert a.groupby(["slot","service_id"]).size().le(1).all()
        for kind,key in (("scale_up","scale_outs"),("scale_down","scale_ins"),("migrate","migrations")):
            assert a.kind.eq(kind).sum()==getattr(row,key)
    assert np.isclose(row.average_replicas,row.replica_seconds/(c.slots*c.slot_seconds))
    # Integrate reservation leases. Pending migration has two leases for one
    # replica until its source is released at migration_downtime.start_s.
    horizon=c.slots*c.slot_seconds;previous=0.;vram=0.;leases=0;memory_area=lease_area=0.
    for e in result["reservations"]:
        now=min(float(e["time_s"]),horizon);dt=now-previous;assert dt>=-1e-12
        memory_area+=dt*vram;lease_area+=dt*leases;previous=now
        if e["time_s"]>horizon:break
        vram+=e["sign"]*w.services[e["service_id"]].gpu_vram_gb
        leases+=e["sign"]
    memory_area+=(horizon-previous)*vram;lease_area+=(horizon-previous)*leases
    migration_area=0.
    if len(result["actions"]):
        migrations=a[a.kind=="migrate"]
        for rid,group in migrations.groupby("replica_id"):
            begins=sorted(e["start_s"] for e in result["lifecycle"] if e["kind"]=="migration_downtime" and e["replica_id"]==rid)
            commands=sorted(group.time_s);assert len(begins)==len(commands)
            for command,begin in zip(commands,begins):
                assert begin>=command-1e-12
                migration_area+=min(begin,horizon)-min(command,horizon)
    replica_area=lease_area-migration_area
    assert np.isclose(row.vram_gb_seconds,memory_area,rtol=1e-10,atol=1e-8)
    assert np.isclose(row.replica_seconds,replica_area,rtol=1e-10,atol=1e-8)
    assert np.isclose(row.mean_gpu_vram_reserved_pct,nodes.gpu_vram_reserved_fraction.mean()*100)
    for r in ("cpu","gpu","bandwidth"):
        assert np.isclose(getattr(row,"average_"+r+"_utilization"),nodes[r+"_utilization"].mean())
    snapshot=read(folder,"control_snapshot_times").set_index("slot").runtime_ms
    full=slots.set_index("slot").decision_runtime_ms+snapshot
    assert np.isclose(row.controller_total_instrumented_mean_ms,full.mean())
    assert np.isclose(row.controller_full_median_ms,full.median())
    assert np.isclose(row.controller_total_instrumented_p95_ms,full.quantile(.95))
    assert np.isclose(row.controller_ms_per_1000_requests,row.controller_cpu_ms_per_request*1000)
    if row.policy=="joint_sla":
        old=ROOT/f"results/scalability_30seeds/runs/{row.scale}/seed_{row.seed:03d}/joint_sla"
        for name in ("request_outcomes","slot_trajectories","node_trajectories","actions","reservation_events","lifecycle_events","routing_decisions","routing_attempts","deployment_audit"):
            x,y=read(folder,name),read(old,name)
            for timer in ("runtime_ms","decision_runtime_ms"):
                x=x.drop(columns=timer,errors="ignore");y=y.drop(columns=timer,errors="ignore")
            pd.testing.assert_frame_equal(x,y,check_exact=True)
    checked=0
    if row.policy=="mjo":
        assert row.rejected_actions==0
        events=read(folder,"solver")
        assert len(events)==row.solver_calls and events.runtime_ms.ge(0).all()
        assert events.status.isin(("optimal","feasible","timeout","infeasible")).all()
        assert events.fallback.eq(~events.status.isin(("optimal","feasible"))).all()
        for status in ("optimal","feasible","timeout","infeasible"):
            assert events.status.eq(status).sum()==getattr(row,"solver_"+status+"_calls")
        assert events.fallback.sum()==row.solver_fallback_calls
        for key,value in (("mean",events.runtime_ms.mean()),("median",events.runtime_ms.median()),("p95",events.runtime_ms.quantile(.95)),("total",events.runtime_ms.sum())):
            assert np.isclose(getattr(row,"solver_"+key+"_ms"),value)
        batches=read(folder,"routing_batches");last={};operations=0
        for batch in batches.itertuples():
            ids=json.loads(batch.requests_json);dest=json.loads(batch.destinations_json);cs=json.loads(batch.candidates_json)
            assert len(ids)==len(set(ids))==len(dest) and batch.status=="optimal"
            assert ids==sorted(ids,key=lambda rid:(w.requests[rid].arrival_s,rid))
            candidates={r["id"]:r for r in cs};counts={rid:0 for rid in candidates};cost=0.
            s=w.services[batch.service_id]
            for rid,target in zip(ids,dest):
                r=w.requests[rid];candidate=candidates[target]
                assert r.service_id==batch.service_id and r.arrival_s<=batch.time_s+1e-12
                assert candidate["ready"] and candidate["capacity_feasible"] and not candidate["pending"] and not candidate["retiring"]
                queue=(candidate["queue_length"]+counts[target])*candidate["cycle_ms"]+candidate["remaining_busy_ms"]
                duration=sum(candidate[k] for k in ("network_ms","compute_ms","resource_wait_ms","penalty_ms"))
                norm=(max(0.,(batch.time_s-r.arrival_s)*1000)+queue+duration)/s.deadline_ms
                # Independent scalar reconstruction of the predeclared objective.
                cost+=s.priority*(max(0.,norm-1.)+norm)+.25*queue/s.deadline_ms
                counts[target]+=1;last[rid]=target
            assert np.isclose(cost,batch.objective,atol=1e-8,rtol=1e-10),(row.scale,row.seed,cost,batch.objective)
            checked+=1;operations+=len(ids)
        assert operations==row.routing_batch_assignment_operations
        assert all(last[r.request_id]==r.replica_id for r in f.itertuples())
        assert checked==row.routing_batches
    return len(f),checked


def inference(raw):
    """Bootstrap, ranks, exact/asymptotic p, Holm and signs reconstructed independently."""
    summary=pd.read_csv(OUTPUT/"summary_statistics.csv",float_precision="round_trip")
    for r in summary.itertuples():
        x=raw[(raw.scale==r.scale)&(raw.policy==r.policy)].sort_values("seed")[r.metric].to_numpy()
        assert r.n==30 and np.isclose(r.mean,x.mean()) and np.isclose(r.standard_deviation,x.std(ddof=1))
        assert np.allclose(reference_ci(x,f"{(r.scale,r.policy)}:{r.metric}"),[r.ci95_lower,r.ci95_upper],atol=1e-8,rtol=1e-10)
    for file,size in (("paired_tests",12),("secondary_paired_tests",12),("overhead_paired_tests",3),("resource_comparison",27)):
        tests=pd.read_csv(OUTPUT/f"{file}.csv",float_precision="round_trip");assert len(tests)==size
        for r in tests.itertuples():
            p=raw[raw.scale==r.scale].pivot(index="seed",columns="policy",values=r.metric).sort_index()
            a,b=p[r.policy_A].to_numpy(),p[r.policy_B].to_numpy();d=b-a
            assert np.isclose(r.absolute_difference,d.mean())
            ci=reference_ci(d,f"strong:{r.family}:{r.scale}:{r.metric}")
            assert np.allclose(ci,[r.difference_ci95_lower,r.difference_ci95_upper],rtol=1e-10,atol=1e-8)
            w,pv,e=reference_signed_rank(d)
            assert np.isclose(w,r.test_statistic) and np.isclose(pv,r.p_value,rtol=1e-8,atol=1e-14)
            assert np.isclose(e,r.rank_biserial_correlation)
            signs=np.round(d,12);assert [r.wins,r.ties,r.losses]==[(signs>0).sum(),(signs==0).sum(),(signs<0).sum()]
            if b.mean()>0:
                key=f"relative:strong:{r.family}:{r.scale}:{r.metric}"
                salt=int.from_bytes(hashlib.sha256(key.encode()).digest()[:4],"little")
                rng=np.random.default_rng(np.random.SeedSequence([73001,salt]));idx=rng.integers(0,30,(10000,30))
                denominator=b[idx].mean(axis=1)
                if (denominator>0).all():
                    rel=100*(denominator-a[idx].mean(axis=1))/denominator
                    assert np.allclose([linear_quantile(rel,.025),linear_quantile(rel,.975)],[r.relative_ci95_lower,r.relative_ci95_upper])
        last=0.
        for rank,idx in enumerate(tests.p_value.sort_values(kind="stable").index):
            last=min(1.,max(last,tests.loc[idx,"p_value"]*(size-rank)))
            assert np.isclose(last,tests.loc[idx,"p_value_holm"],rtol=1e-10,atol=1e-14)
        assert tests.supported_improvement.eq((tests.p_value_holm<.05)&(tests.absolute_difference>0)&(tests.difference_ci95_lower>0)).all()
    differences=pd.read_csv(OUTPUT/"paired_seed_differences.csv")
    negative=pd.read_csv(OUTPUT/"negative_seed_cases.csv")
    assert len(differences)==360 and len(negative)==differences.outcome.eq("loss").sum()
    for r in differences.itertuples():
        f=raw[(raw.scale==r.scale)&(raw.seed==r.seed)].set_index("policy")
        assert np.isclose(r.difference,f.loc[r.policy_B,r.metric]-f.loc[r.policy_A,r.metric])
    secondary=pd.read_csv(OUTPUT/"secondary_seed_differences.csv")
    negative_secondary=pd.read_csv(OUTPUT/"baseline_strength_negative_cases.csv")
    assert len(secondary)==360 and len(negative_secondary)==secondary.outcome.eq("loss").sum()
    for r in secondary.itertuples():
        f=raw[(raw.scale==r.scale)&(raw.seed==r.seed)].set_index("policy")
        assert np.isclose(r.difference,f.loc[r.policy_B,r.metric]-f.loc[r.policy_A,r.metric])
    return len(summary)


def conclusions(raw):
    """Check predeclared operational screens and source-backed report cells."""
    evidence=json.loads((OUTPUT/"hypotheses.json").read_text())
    primary=pd.read_csv(OUTPUT/"paired_tests.csv").set_index(["scale","metric"])
    secondary=pd.read_csv(OUTPUT/"secondary_paired_tests.csv").set_index(["scale","metric"])
    overhead=pd.read_csv(OUTPUT/"overhead_paired_tests.csv")
    assert evidence["B1"]==all(bool(secondary.loc[(s,m),"supported_improvement"]) for s in SCALES for m in ("sla_breach_rate","p95_latency_ms"))
    for flag,metrics in (("B2",("sla_breach_rate",)),("B3",("p95_latency_ms","p99_latency_ms"))):
        assert evidence[flag]==all(primary.loc[(s,m),"relative_ci95_lower"]>=-5 for s in SCALES for m in metrics)
    assert evidence["B4"]==bool(overhead.supported_improvement.all())
    for screen in evidence["resource_screens"]:
        scale=screen["scale"];f=raw[raw.scale==scale]
        for metric in ("average_replicas","actions_per_1000_requests"):
            p=f.pivot(index="seed",columns="policy",values=metric).sort_index()
            key=f"strong:fairness:{scale}:{metric}"
            salt=int.from_bytes(hashlib.sha256(key.encode()).digest()[:4],"little")
            rng=np.random.default_rng(np.random.SeedSequence([73001,salt]));idx=rng.integers(0,30,(10000,30))
            j=p.joint_sla.to_numpy()[idx].mean(axis=1);m=p.mjo.to_numpy()[idx].mean(axis=1)
            upper=linear_quantile(100*(m-j)/j,.975)
            assert np.isclose(screen[metric+"_relative_upper"],upper)
        p=f.pivot(index="seed",columns="policy",values="mean_gpu_vram_reserved_pct").sort_index()
        ci=reference_ci(p.mjo.to_numpy()-p.joint_sla.to_numpy(),f"strong:fairness:{scale}:vram")
        assert np.isclose(screen["vram_pp_upper"],ci[1])
        assert screen["passed"]==bool(screen["average_replicas_relative_upper"]<=5 and screen["actions_per_1000_requests_relative_upper"]<=5 and screen["vram_pp_upper"]<=2)
    assert evidence["B5"]==all(s["passed"] for s in evidence["resource_screens"])
    from .presentation import HEADINGS
    report=(OUTPUT/"report.md").read_text(encoding="utf-8")
    for heading in HEADINGS:assert "# "+heading+"\n" in report
    summary=pd.read_csv(OUTPUT/"summary_statistics.csv")
    for r in summary.itertuples():
        if r.metric in ("sla_breach_rate","mean_request_latency_ms","p95_latency_ms","p99_latency_ms","average_replicas","mean_gpu_vram_reserved_pct","Gold_breach_rate","Silver_breach_rate","Bronze_breach_rate"):
            factor=100 if "breach_rate" in r.metric else 1
            assert f"{r.mean*factor:.2f} ± {r.standard_deviation*factor:.2f} [{r.ci95_lower*factor:.2f}, {r.ci95_upper*factor:.2f}]" in report
    if not evidence["B1"]:assert "baseline-design limitation/failure" in report
    return evidence


def verify():
    protocol=json.loads((OUTPUT/"simulation_protocol.json").read_text());assert protocol["source_hashes"]==source_hashes()
    raw=pd.read_csv(OUTPUT/"raw_results.csv",float_precision="round_trip")
    assert len(raw)==270 and not raw.duplicated(["scale","seed","policy"]).any()
    assert set(zip(raw.scale,raw.seed,raw.policy))=={(s,i,p) for s in SCALES for i in range(1,31) for p in POLICIES}
    assert np.isfinite(raw.select_dtypes(include="number").to_numpy()).all()
    requests=batches=0
    for scale in SCALES:
        c=configuration(scale)
        for seed in range(1,31):
            w=generate_workload(c,seed);group=raw[(raw.scale==scale)&(raw.seed==seed)]
            assert group.traffic_hash.nunique()==group.workload_hash.nunique()==1
            assert group.traffic_hash.iloc[0]==digest(traffic_hash_payload(w)) and group.workload_hash.iloc[0]==digest(w.to_dict())
            for r in group.itertuples():
                n,b=audit_run(r,w,c);requests+=n;batches+=b
        print(f"Independent exports verified: {scale}",flush=True)
    summary_count=inference(raw);conclusions(raw)
    figures=list((OUTPUT/"figures").glob("*.png"));assert len(figures)==12
    for path in figures:
        with Image.open(path) as picture:assert min(picture.info["dpi"])>=299
        assert path.with_suffix(".svg").exists() and path.with_suffix(".pdf").exists()
    protected=verify_protected()
    evidence=dict(successful=True,runs=270,new_runs=180,reused_runs=90,requests_verified=requests,
        routing_batches_independently_reconstructed=batches,summary_rows_checked=summary_count,
        accounting_components_capacity_lifecycle=True,causal_arrival_and_feasible_routing=True,
        new_joint_scientific_exports_exactly_frozen=True,statistics_independently_reconstructed=True,
        figures_300dpi_and_vectors=12,protected_files_unchanged=protected)
    write_json(OUTPUT/"validation.json",evidence)
    write_json(OUTPUT/"environment.json",dict(python=platform.python_version(),platform=platform.platform(),
        packages={n:importlib.metadata.version(n) for n in ("numpy","pandas","scipy","simpy","matplotlib","pytest")}))
    paths=[*OUTPUT.rglob("*"),*(ROOT/"strong_baseline").glob("*"),ROOT/"run_strong_baseline.py",
           ROOT/"tools/verify_strong_baseline.py",ROOT/"tests/test_strong_baseline.py"]
    write_json(OUTPUT/"artifact_hashes.json",{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths) if p.is_file() and p.name!="artifact_hashes.json"})
    return evidence
