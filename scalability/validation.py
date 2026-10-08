"""Independently reconstruct exported outcomes, routing choices and statistics."""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json
from paper_evaluation.validation import linear_quantile,reference_ci,reference_signed_rank
from joint_routing.validation import reference_choice,reference_score
from .configuration import ROOT,SCALES,POLICIES
from .experiment import protected_hashes,sources


def close(a,b,tol=1e-7):
    assert np.allclose(a,b,atol=tol,rtol=1e-9),(a,b)


def indices(key):
    salt=int.from_bytes(hashlib.sha256(key.encode()).digest()[:4],"little")
    return np.random.default_rng(np.random.SeedSequence([73001,salt])).integers(0,30,(10000,30))


def read(folder,name):return pd.read_csv(folder/f"{name}.csv.gz")


def verify(output):
    output=Path(output);protocol=json.loads((output/"simulation_protocol.json").read_text())
    assert sources()==protocol["source_hashes"] and protected_hashes()==protocol["protected_hashes"]
    analysis=json.loads((output/"analysis_protocol.json").read_text())
    for path,fingerprint in analysis["source_hashes"].items():assert digest((ROOT/path).read_text(encoding="utf-8"))==fingerprint
    raw=pd.read_csv(output/"raw_results.csv");indexed=raw.set_index(["scale","seed","policy"])
    assert len(raw)==270 and indexed.index.is_unique
    assert set(indexed.index)=={(s,seed,p) for s in SCALES for seed in range(1,31) for p in POLICIES}
    assert np.isfinite(raw.select_dtypes(include="number").to_numpy()).all()
    cfg=pd.read_csv(output/"scale_configuration_summary.csv").set_index(["scale","seed"])
    assert len(cfg)==90
    historical=pd.read_csv(ROOT/"results/joint_routing_30seeds/raw_policy_results.csv").set_index(["seed","policy"])
    requests_checked=0;quantiles=0;routing_checked=0;node_checks=0;reservation_checks=0
    for scale,(nn,ss) in SCALES.items():
        c=protocol["scales"][scale];horizon=c["slots"]*c["slot_seconds"]
        assert c["node_count"]==nn and c["service_count"]==ss
        small={k:v for k,v in protocol["scales"]["SMALL"].items() if k not in ("node_count","service_count")}
        assert {k:v for k,v in c.items() if k not in ("node_count","service_count")}==small
        for seed in range(1,31):
            with gzip.open(output/"inputs"/scale/f"seed_{seed:03d}.json.gz","rt",encoding="utf-8") as stream:v=json.load(stream)
            group=raw.loc[(raw.scale==scale)&(raw.seed==seed)]
            assert group.workload_hash.nunique()==group.traffic_hash.nunique()==group.total_requests.nunique()==1
            assert digest(v)==group.workload_hash.iloc[0]
            assert digest({k:v[k] for k in ("seed","services","requests","traffic")})==group.traffic_hash.iloc[0]
            assert len(v["services"])==ss and len(v["scenario"]["nodes"])==nn and all(n is not None for n in v["initial"].values())
            configuration_row=cfg.loc[(scale,seed)]
            close(configuration_row.requests_per_service,len(v["requests"])/ss)
            close(configuration_row.offered_requests_per_node_per_second,len(v["requests"])/nn/horizon)
            close(configuration_row.mean_cpu_demand,np.mean([s["cpu_cores"] for s in v["services"]]))
            close(configuration_row.mean_gpu_vram_demand_gb,np.mean([s["gpu_vram_gb"] for s in v["services"]]))
            close(configuration_row.mean_deadline_ms,np.mean([s["deadline_ms"] for s in v["services"]]))
            deadlines=[s["deadline_ms"] for s in v["services"]]
            close([configuration_row.deadline_p10_ms,configuration_row.deadline_p50_ms,configuration_row.deadline_p90_ms],[linear_quantile(deadlines,p) for p in (.1,.5,.9)])
            for tier in ("Gold","Silver","Bronze"):
                sub=[s["deadline_ms"] for s in v["services"] if s["tier"]==tier]
                close(configuration_row[f"{tier}_proportion"],len(sub)/ss);close(configuration_row[f"{tier}_mean_deadline_ms"],np.mean(sub))
            traffic=pd.DataFrame(v["traffic"]);rates=traffic.groupby("service_id").expected_rate_rps.mean()
            caps=np.array([[n[k] for k in ("cpu_capacity","gpu_capacity","bandwidth_capacity_mbps")] for n in v["scenario"]["nodes"]])
            close(configuration_row.expected_gpu_pressure,rates.sum()*.01/sum(v["gpu_units"]))
            close(configuration_row.expected_cpu_pressure,sum(rates[s["service_id"]]*s["cpu_cores"]*.0065 for s in v["services"])/caps[:,0].sum())
            close(configuration_row.initial_vram_pressure,sum(s["gpu_vram_gb"] for s in v["services"])/caps[:,1].sum())
            close(configuration_row.burst_slots_fraction,traffic.burst.mean())
            ref=pd.DataFrame(v["requests"]).set_index("request_id")
            for policy in POLICIES:
                row=indexed.loc[(scale,seed,policy)];folder=output/"runs"/scale/f"seed_{seed:03d}"/policy
                f=read(folder,"request_outcomes").set_index("request_id");assert f.index.is_unique and set(f.index)==set(ref.index)
                assert len(f)==row.total_requests and f.latency_ms.notna().all() and not f.unplaced.any() and row.dropped_requests==0
                reforder=ref.loc[f.index]
                for column in ("service_id","arrival_slot","arrival_s"):close(f[column],reforder[column],1e-12)
                services={s["service_id"]:s for s in v["services"]}
                close(f.deadline_ms,f.service_id.map({s:q["deadline_ms"] for s,q in services.items()}))
                assert f.tier.eq(f.service_id.map({s:q["tier"] for s,q in services.items()})).all()
                components=f[["service_queue_ms","node_queue_ms","network_ms","compute_ms","lifecycle_penalty_ms"]]
                assert (components>=-1e-7).all().all()
                close(f.latency_ms,(f.completion_s-f.arrival_s)*1000,1e-6);close(f.latency_ms,components.sum(axis=1),1e-6)
                close(f.compute_ms,reforder.work_factor*14,1e-6)
                ingress=f.service_id.map({s:q["ingress"] for s,q in services.items()}).to_numpy(dtype=int);target=f.node.to_numpy(dtype=int)
                network=np.array(v["scenario"]["network_latency_ms"])[ingress,target]+1000*reforder.payload_mbit/caps[target,2]
                close(f.network_ms,network,1e-6);assert f.breach.eq(f.latency_ms>f.deadline_ms).all()
                close(row.mean_request_latency_ms,f.latency_ms.mean());close(row.sla_breach_rate,f.breach.mean())
                close(row.mean_slot_latency_ms,f.groupby("arrival_slot").latency_ms.mean().mean())
                assert row.sla_breaches==f.breach.sum() and row.completed_requests==len(f)
                assert row.completed_after_horizon==(f.completion_s>horizon).sum()
                for metric,p in (("median_latency_ms",.5),("p95_latency_ms",.95),("p99_latency_ms",.99)):
                    close(row[metric],linear_quantile(f.latency_ms,p));quantiles+=1
                for tier in ("Gold","Silver","Bronze"):
                    sub=f.loc[f.tier==tier]
                    assert row[f"{tier}_requests"]==len(sub) and row[f"{tier}_breaches"]==sub.breach.sum()
                    close(row[f"{tier}_breach_rate"],sub.breach.mean())
                requests_checked+=len(f)
                sf,nf,af,lf=map(lambda name:read(folder,name),("slot_trajectories","node_trajectories","actions","lifecycle_events"))
                assert len(sf)==100 and len(nf)==100*nn and sf.requests.sum()==len(f)
                assert row.total_actions==(len(af) if "kind" in af else 0)==sf.accepted_actions.sum()
                for metric,kind in (("scale_outs","scale_up"),("scale_ins","scale_down"),("migrations","migrate")):
                    assert row[metric]==(af.kind.eq(kind).sum() if "kind" in af else 0)
                assert row.cold_starts==(lf.kind.eq("cold_start").sum() if "kind" in lf else 0)
                allocated={rid:int(sid) for rid,(sid,node) in enumerate((item for item in v["initial"].items() if item[1] is not None))}
                if "kind" in af:
                    for a in af.loc[af.kind=="scale_up"].itertuples():allocated[int(a.replica_id)]=int(a.service_id)
                cvs=[]
                for sid in set(allocated.values()):
                    reps=[rid for rid,s in allocated.items() if s==sid]
                    numbers=np.array([int((f.replica_id==rid).sum()) for rid in reps])
                    if numbers.mean()>0:cvs.append(numbers.std()/numbers.mean())
                close(row.replica_load_imbalance_cv,np.mean(cvs))
                for resource in ("cpu","gpu","bandwidth"):
                    assert nf[f"{resource}_utilization"].between(-1e-8,1+1e-8).all()
                    close(row[f"average_{resource}_utilization"],nf[f"{resource}_utilization"].mean())
                close(row.mean_gpu_vram_reserved_pct,nf.gpu_vram_reserved_fraction.mean()*100)
                node_checks+=len(nf)
                ledger=read(folder,"reservation_events");reserved=np.zeros_like(caps)
                memory_integral=0.;previous_time=0.;previous_memory=0.
                for e in ledger.itertuples():
                    now=min(e.time_s,horizon);memory_integral+=(now-previous_time)*previous_memory;previous_time=now
                    service=services[e.service_id]
                    reserved[e.node]+=e.sign*np.array([service[k] for k in ("cpu_cores","gpu_vram_gb","bandwidth_mbps")])
                    assert (reserved>=-1e-8).all() and (reserved<=caps+1e-8).all()
                    close(reserved[e.node],[e.cpu_reserved,e.gpu_vram_reserved,e.bandwidth_reserved]);previous_memory=reserved[:,1].sum();reservation_checks+=1
                memory_integral+=(horizon-previous_time)*previous_memory
                close(row.vram_gb_seconds,memory_integral)
                close(row.vram_reserved_gib_per_node,memory_integral/horizon/nn)
                timing=json.loads((folder/"timing.json").read_text());cpu=read(folder,"controller_cpu_times");snap=read(folder,"control_snapshot_times")
                assert len(cpu)==len(snap)==100
                close(row.average_eligible_replicas,cpu.eligible_replicas_end.mean())
                close(row.completed_requests_per_average_eligible_replica,len(f)/cpu.eligible_replicas_end.mean())
                total=sf.set_index("slot").decision_runtime_ms+snap.set_index("slot").runtime_ms
                close(row.controller_total_instrumented_mean_ms,total.mean());close(row.controller_total_instrumented_p95_ms,linear_quantile(total,.95))
                close(row.controller_decision_mean_ms,sf.decision_runtime_ms.mean());close(row.controller_decision_p95_ms,linear_quantile(sf.decision_runtime_ms,.95))
                close(row.control_only_cpu_ms,cpu[["snapshot_cpu_ms","policy_cpu_ms","apply_cpu_ms"]].to_numpy().sum())
                close(row.total_controller_cpu_ms,row.control_only_cpu_ms+timing["routing_cpu_ms"])
                for field,expected in (("wall_seconds_per_100k_requests",row.wall_clock_seconds*100000/len(f)),
                    ("controller_cpu_ms_per_request",row.total_controller_cpu_ms/len(f)),("actions_per_1000_requests",row.total_actions*1000/len(f)),
                    ("cold_starts_per_1000_requests",row.cold_starts*1000/len(f)),("replicas_per_service",row.average_replicas/ss),
                    ("sla_violations_per_1000_requests",f.breach.sum()*1000/len(f)),("requests_processed_per_slot",len(f)/100)):
                    close(row[field],expected)
                close(row.requests_completed_within_horizon_per_slot,(f.completion_s<=horizon).sum()/100)
                close(row.fraction_completed_after_horizon,(f.completion_s>horizon).mean())
                if scale=="SMALL":
                    historic=historical.loc[(seed,policy)]
                    for m in ("sla_breach_rate","mean_request_latency_ms","median_latency_ms","p95_latency_ms","p99_latency_ms","average_replicas","mean_gpu_vram_reserved_pct","total_actions"):
                        close(row[m],historic[m],1e-9)
                if policy!="sla_aware":
                    attempts=read(folder,"routing_attempts")
                    close(row.request_routing_decision_mean_ms,attempts.runtime_ms.mean());close(row.request_routing_decision_p95_ms,linear_quantile(attempts.runtime_ms,.95))
                    assert row.routing_attempts==len(attempts) and row.routing_assignments==attempts.success.sum()
                    blocked=defaultdict(list);retired=defaultdict(lambda:float("inf"))
                    if "kind" in lf:
                        for e in lf.itertuples():blocked[e.replica_id].append((e.start_s,e.ready_s))
                    if "kind" in af:
                        for e in af.itertuples():
                            if e.kind=="scale_down":retired[e.replica_id]=min(retired[e.replica_id],e.time_s)
                            elif e.kind=="migrate":
                                ends=[end for start,end in blocked[e.replica_id] if start>=e.time_s-1e-9];assert ends
                                blocked[e.replica_id].append((e.time_s,min(ends)))
                    first={};last={};counter=defaultdict(int);assignments=0
                    for chunk in pd.read_csv(folder/"routing_decisions.csv.gz",chunksize=10000):
                        for e in chunk.itertuples(index=False):
                            request=v["requests"][e.request_id];service=services[e.service_id]
                            assert e.service_id==request["service_id"] and abs(e.arrival_s-request["arrival_s"])<1e-10
                            assert abs(e.deadline_ms-service["deadline_ms"])<1e-8
                            assert e.time_s>=e.arrival_s-1e-10 and abs(e.age_ms-max(0,(e.time_s-e.arrival_s)*1000))<1e-7
                            candidates=json.loads(e.candidates_json);assert len(candidates)==e.eligible_count
                            assert len({a["id"] for a in candidates})==len(candidates)
                            assert e.rr_counter==counter[e.service_id];counter[e.service_id]+=1
                            for a in candidates:
                                assert a["ready"] and a["capacity_feasible"] and not a["pending"] and not a["retiring"]
                                assert a["queue_length"]>=0 and a["cycle_variance_ms2"]>0
                                assert not any(start-1e-10<=e.time_s<end-1e-10 for start,end in blocked[a["id"]])
                                assert e.time_s<retired[a["id"]]-1e-10
                                assert service["cpu_cores"]<=caps[a["node"],0] and service["gpu_vram_gb"]<=caps[a["node"],1] and v["gpu_units"][a["node"]]>=1
                                net=v["scenario"]["network_latency_ms"][service["ingress"]][a["node"]]+1000*service["payload_mbit"]/caps[a["node"],2]
                                assert abs(a["network_ms"]-net)<1e-8 and a["compute_ms"]==14
                            assert e.replica_id==reference_choice(candidates,e.deadline_ms,e.age_ms,policy,e.rr_counter)
                            chosen=next(a for a in candidates if a["id"]==e.replica_id);assert chosen["node"]==e.node
                            _,score=reference_score(chosen,e.deadline_ms,e.age_ms,policy)
                            columns=("estimated_queue_wait_ms","estimated_resource_wait_ms","estimated_completion_ms","slack_ms","risk_proxy","estimated_variance_ms2")
                            assert all(abs(getattr(e,k)-expected)<1e-6 for k,expected in zip(columns,score))
                            nq=reference_choice(candidates,e.deadline_ms,e.age_ms,"joint_no_queue",0)
                            away=chosen["network_ms"]>min(a["network_ms"] for a in candidates)+1e-12
                            assert away==e.routed_away_from_lowest_network and (e.replica_id!=nq)==e.queue_changed_choice
                            first.setdefault(e.request_id,(away,e.replica_id!=nq,len(candidates)>1));last[e.request_id]=(e.replica_id,e.node,e.time_s);assignments+=1
                    assert assignments==row.routing_assignments and set(last)==set(f.index)
                    actual=f.loc[list(last)]
                    values=np.array(list(last.values()))
                    close(actual.replica_id,values[:,0]);close(actual.node,values[:,1])
                    assert (values[:,2]<=actual.arrival_s+actual.service_queue_ms/1000+1e-8).all()
                    close([row.routed_away_from_lowest_network_fraction,row.queue_changed_choice_fraction,row.multi_eligible_fraction],np.array(list(first.values())).mean(axis=0))
                    replica_services=json.loads((folder/"replica_services.json").read_text());cv=[]
                    for sid,g in f.groupby("service_id"):
                        allocated=[int(rid) for rid,s in replica_services.items() if s==sid]
                        counts=g.replica_id.value_counts().reindex(allocated,fill_value=0).to_numpy(dtype=float)
                        cv.append(counts.std()/counts.mean())
                    close(row.mean_per_service_replica_request_cv,np.mean(cv));routing_checked+=assignments
            print(f"Independently verified {scale} seed {seed}/30 (all three policies)",flush=True)
    summary=pd.read_csv(output/"summary_statistics.csv")
    for r in summary.itertuples():
        values=raw.loc[(raw.scale==r.scale)&(raw.policy==r.policy)].sort_values("seed")[r.metric].to_numpy()
        assert r.n==30;close([r.mean,r.standard_deviation,r.median,r.min,r.max],[values.mean(),values.std(ddof=1),np.median(values),values.min(),values.max()])
        close([r.ci95_lower,r.ci95_upper],reference_ci(values,f"{(r.scale,r.policy)}:{r.metric}"))
    trends=pd.read_csv(output/"scale_trends.csv")
    assert len(trends)==len(summary);close(trends["mean"],summary["mean"]);close(trends.CI_low,summary.ci95_lower);close(trends.CI_high,summary.ci95_upper)
    primary=pd.read_csv(output/"paired_tests.csv");secondary=pd.read_csv(output/"secondary_paired_tests.csv")
    for tests in (primary,secondary):
        assert len(tests)==12
        for r in tests.itertuples():
            pivot=raw.loc[raw.scale==r.scale].pivot(index="seed",columns="policy",values=r.metric).sort_index()
            a,b=pivot.joint_sla.to_numpy(),pivot[r.policy_B].to_numpy();d=b-a
            close([r.mean_A,r.mean_B,r.absolute_difference,r.relative_improvement_percent],[a.mean(),b.mean(),d.mean(),100*d.mean()/b.mean()])
            stat,pval,effect=reference_signed_rank(d);close([r.test_statistic,r.rank_biserial_correlation],[stat,effect])
            assert np.isclose(pval,r.p_value,atol=1e-14,rtol=1e-8)
            close([r.difference_ci95_lower,r.difference_ci95_upper],reference_ci(d,f"scalability:{r.family}:{r.scale}:{r.metric}"))
            idx=indices(f"scalability-relative:{r.family}:{r.scale}:{r.metric}")
            ratio=100*(b[idx].mean(axis=1)-a[idx].mean(axis=1))/b[idx].mean(axis=1)
            close([r.relative_ci95_lower,r.relative_ci95_upper],[linear_quantile(ratio,p) for p in (.025,.975)])
            signs=np.round(d,12);assert [r.wins,r.ties,r.losses]==[(signs>0).sum(),(signs==0).sum(),(signs<0).sum()]
        highest=0
        for rank,idx in enumerate(tests.p_value.sort_values(kind="stable").index):
            highest=min(1,max(highest,tests.loc[idx,"p_value"]*(12-rank)));close(highest,tests.loc[idx,"p_value_holm"],1e-14)
        assert tests.supported_improvement.eq((tests.p_value_holm<.05)&(tests.absolute_difference>0)&(tests.difference_ci95_lower>0)).all()
    gains=pd.read_csv(output/"joint_relative_gain_by_scale.csv")
    close(gains.relative_gain,primary.relative_improvement_percent);close(gains.CI_low,primary.relative_ci95_lower);close(gains.CI_high,primary.relative_ci95_upper)
    differences=pd.read_csv(output/"paired_seed_differences.csv");negative=pd.read_csv(output/"negative_seed_cases.csv")
    assert len(differences)==360
    for r in differences.itertuples():
        b=indexed.loc[(r.scale,r.seed,"sla_aware"),r.metric];a=indexed.loc[(r.scale,r.seed,"joint_sla"),r.metric]
        close([r.sla_aware_value,r.joint_value,r.difference],[b,a,b-a])
        assert r.outcome==("win" if round(b-a,12)>0 else "loss" if round(b-a,12)<0 else "tie")
    expected=differences.loc[differences.outcome=="loss"]
    assert set(zip(negative.scale,negative.seed,negative.metric))==set(zip(expected.scale,expected.seed,expected.metric))
    resources=pd.read_csv(output/"resource_scaling.csv")
    for r in resources.itertuples():
        p=raw.loc[raw.scale==r.scale].pivot(index="seed",columns="policy",values=r.metric).sort_index()
        a,b=p.joint_sla.to_numpy(),p.sla_aware.to_numpy();d=a-b
        close([r.joint_mean,r.sla_aware_mean,r.joint_minus_baseline],[a.mean(),b.mean(),d.mean()])
        close([r.CI_low,r.CI_high],reference_ci(d,f"scalability-resource:{r.scale}:{r.metric}"))
        idx=indices(f"scalability-resource-relative:{r.scale}:{r.metric}")
        defined=bool(b.mean()>0 and (b[idx].mean(axis=1)>0).all())
        assert r.relative_defined==defined
        if defined:
            ratio=100*(a[idx].mean(axis=1)-b[idx].mean(axis=1))/b[idx].mean(axis=1)
            close([r.relative_CI_low,r.relative_CI_high],[linear_quantile(ratio,p) for p in (.025,.975)])
        else:assert pd.isna(r.relative_CI_low) and pd.isna(r.relative_CI_high)
    h=json.loads((output/"hypotheses.json").read_text());pt=primary.set_index(["scale","metric"])
    supported=lambda s,m:bool(pt.loc[(s,m),"supported_improvement"])
    expected_h1=all(supported(s,"sla_breach_rate") for s in SCALES);expected_h2=all(supported(s,"p95_latency_ms") for s in SCALES)
    large=primary.loc[(primary.scale=="LARGE")&primary.metric.isin(("sla_breach_rate","p95_latency_ms"))]
    expected_h3=sum(supported(s,"sla_breach_rate") and supported(s,"p95_latency_ms") for s in SCALES)>=2 and large.absolute_difference.ge(0).all() and large.losses.le(15).all()
    expected_h4=True;expected_h5=True
    for scale in SCALES:
        j=raw.loc[(raw.scale==scale)&(raw.policy=="joint_sla")]
        expected_h4 &= j.controller_total_instrumented_mean_ms.mean()<=10 and j.controller_total_instrumented_p95_ms.mean()<=100 and j.request_routing_decision_p95_ms.mean()<=1
        r=resources.loc[resources.scale==scale].set_index("metric")
        expected_h5 &= r.loc["average_replicas","relative_CI_high"]<=5 and r.loc["mean_gpu_vram_reserved_pct","CI_high"]<=2 and r.loc["actions_per_1000_requests","relative_CI_high"]<=5
    assert [h[k] for k in ("H1","H2","H3","H4","H5")]==[bool(v) for v in (expected_h1,expected_h2,expected_h3,expected_h4,expected_h5)]
    report=(output/"report.md").read_text(encoding="utf-8")
    for title in ("Research Question","Verified JointSLA Baseline","Scalability Methodology","Scale-Preserving Configuration","Small Results","Medium Results","Large Results","SLA Generalization","Mean and Tail Latency","Per-Tier Generalization","Resource Scaling","Controller Overhead Scaling","Negative Seeds","Statistical Significance","Does the JointSLA Advantage Persist?","Threats to Validity","Safe Paper Claims","Claims We Cannot Make","Implications for B-Level Publication"):
        assert f"# {title}" in report
    for r in pd.read_csv(output/"claim_ledger.csv").itertuples():
        reference=pt.loc[(r.scale,r.metric)]
        assert reference.supported_improvement and r.sentence in report;close(r.relative_improvement_percent,reference.relative_improvement_percent)
    from PIL import Image
    pictures=list((output/"figures").glob("*.png"));assert len(pictures)==10
    for path in pictures:
        with Image.open(path) as im:assert min(im.info["dpi"])>=299
        assert path.with_suffix(".svg").exists() and path.with_suffix(".pdf").exists()
    assert protected_hashes()==protocol["protected_hashes"]
    result=dict(successful_runs=270,pilot_runs=27,requests_verified=requests_checked,request_quantiles_verified=quantiles,
                routing_decisions_replayed=routing_checked,node_slots_verified=node_checks,reservation_events_verified=reservation_checks,
                comparisons_verified=24,baseline_artifacts_byte_identical=True,small_reproduces_verified_baseline=True,
                hashes_paired=True,primary_metrics_finite=True,all_negative_seeds_retained=True,hypotheses_verified=True,figures_checked=10)
    write_json(output/"validation.json",result)
    write_json(output/"artifact_hashes.json",{p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(output.rglob("*")) if p.is_file() and p.name!="artifact_hashes.json"})
    return result
