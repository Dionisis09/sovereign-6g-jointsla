"""Independent reconstruction of new outcomes, causal choices and inference.

The verifier reads exported observations; it never calls the new router,
controller, metric calculator or hypothesis evaluator to verify their answers.
Existing independently verified statistical references are reused unchanged.
"""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from catalyst.reused import digest, write_json
from paper_evaluation.validation import linear_quantile, reference_ci, reference_signed_rank
from paper_evaluation.experiments import ROOT, engine_hashes
from .experiment import ALL_POLICIES, protected_hashes, source_hashes
from .router import NEW_POLICIES, LABELS


def close(actual, expected, tolerance=1e-7):
    assert np.allclose(actual, expected, atol=tolerance, rtol=1e-10), (actual, expected)


def reference_score(c, deadline, age, policy):
    """Reconstruct score algebra without importing estimate/choose."""
    ignore = policy == "joint_no_queue"
    waiting = 0 if ignore else c["queue_length"]
    queue = waiting*c["cycle_ms"]+(0 if ignore else c["remaining_busy_ms"])
    completion = age+c["available_in_ms"]+queue+sum(c[k] for k in ("network_ms","compute_ms","resource_wait_ms","penalty_ms"))
    slack = deadline-completion
    variance = c["cycle_variance_ms2"]*(waiting+1+(bool(c["busy"]) and not ignore))
    risk = 1. if slack <= 0 else variance/(variance+slack**2)
    key = (completion,c["id"]) if policy == "joint_no_slack" else (risk,-slack,completion,c["id"])
    return key, (queue,c["resource_wait_ms"],completion,slack,risk,variance)


def reference_choice(candidates, deadline, age, policy, counter):
    if policy == "sla_rr":
        return sorted(candidates,key=lambda c:c["id"])[counter%len(candidates)]["id"]
    if policy == "sla_shortest_queue":
        return min(candidates,key=lambda c:(c["queue_length"]+int(c["busy"]),c["id"]))["id"]
    return min(candidates,key=lambda c:reference_score(c,deadline,age,policy)[0])["id"]


def bootstrap_indices(key):
    salt=int.from_bytes(hashlib.sha256(key.encode()).digest()[:4],"little")
    return np.random.default_rng(np.random.SeedSequence([73001,salt])).integers(0,30,(10000,30))


def verify(output):
    output=Path(output)
    protocol=json.loads((output/"protocol.json").read_text(encoding="utf-8"))
    config=protocol["config"]; settings=protocol["settings"]
    assert protocol["engine_sources"] == engine_hashes()
    assert protocol["new_sources"] == source_hashes()
    assert protocol["protected_baseline_hashes"] == protected_hashes()
    assert protocol["predeclared_document_hash"] == digest((ROOT/"joint_routing/README.md").read_text(encoding="utf-8"))
    analysis=json.loads((output/"analysis_protocol.json").read_text(encoding="utf-8"))
    assert analysis["settings"] == settings
    for path,fingerprint in analysis["source_hashes"].items():
        assert digest((ROOT/path).read_text(encoding="utf-8")) == fingerprint
    raw=pd.read_csv(output/"raw_policy_results.csv")
    indexed=raw.set_index(["seed","policy"])
    assert indexed.index.is_unique and set(indexed.index)=={(s,p) for s in range(1,31) for p in ALL_POLICIES}
    assert len(raw)==270 and np.isfinite(raw.select_dtypes(include="number").to_numpy()).all()
    historical=pd.read_csv(ROOT/"results/paper_30seeds/raw_policy_results.csv").set_index(["seed","policy"])
    preserved=indexed.loc[historical.index,historical.columns]
    for column in historical:
        if pd.api.types.is_numeric_dtype(historical[column]):
            close(preserved[column],historical[column],1e-12)
        else:
            assert preserved[column].equals(historical[column]), column
    inputs={}
    for seed,group in raw.groupby("seed"):
        with gzip.open(output/"inputs"/f"seed_{seed:03d}.json.gz","rt",encoding="utf-8") as stream:
            value=json.load(stream)
        inputs[seed]=value
        assert group.workload_hash.nunique()==group.traffic_hash.nunique()==group.total_requests.nunique()==1
        assert digest(value)==group.workload_hash.iloc[0]
        assert digest({k:value[k] for k in ("seed","services","requests","traffic")})==group.traffic_hash.iloc[0]
    outcomes=pd.read_csv(output/"request_outcomes.csv.gz")
    assert set(outcomes.policy)==set(NEW_POLICIES)
    outcome_groups={key:group.set_index("request_id") for key,group in outcomes.groupby(["seed","policy"],sort=False)}
    quantiles=0
    for key,f in outcome_groups.items():
        value=inputs[key[0]]; r=indexed.loc[key]
        reference=pd.DataFrame(value["requests"]).set_index("request_id").loc[f.index]
        assert f.index.is_unique and set(f.index)==set(range(len(reference))) and len(f)==r.total_requests
        for column in ("service_id","arrival_slot","arrival_s"):
            close(f[column],reference[column],1e-12)
        services={s["service_id"]:s for s in value["services"]}
        close(f.deadline_ms,f.service_id.map({s:v["deadline_ms"] for s,v in services.items()}))
        assert f.tier.eq(f.service_id.map({s:v["tier"] for s,v in services.items()})).all()
        completed=f.latency_ms.notna(); unplaced=f.unplaced.astype(bool)
        assert (completed|unplaced).all() and not (completed&unplaced).any()
        assert f.loc[unplaced,"breach"].all() and r.dropped_requests==0
        valid=f.loc[completed]
        components=valid[["service_queue_ms","node_queue_ms","network_ms","compute_ms","lifecycle_penalty_ms"]]
        assert (components>=-1e-7).all().all()
        close(valid.latency_ms,(valid.completion_s-valid.arrival_s)*1000,1e-6)
        close(valid.latency_ms,components.sum(axis=1),1e-6)
        close(valid.compute_ms,reference.loc[valid.index,"work_factor"]*sum(config[k] for k in ("preprocess_ms","inference_ms","postprocess_ms")),1e-6)
        ingress=valid.service_id.map({s:v["ingress"] for s,v in services.items()}).to_numpy(dtype=int)
        node=valid.node.to_numpy(dtype=int)
        bw=np.array([n["bandwidth_capacity_mbps"] for n in value["scenario"]["nodes"]])
        network=np.array(value["scenario"]["network_latency_ms"])[ingress,node]+1000*reference.loc[valid.index,"payload_mbit"]/bw[node]
        close(valid.network_ms,network,1e-6)
        assert valid.breach.eq(valid.latency_ms>valid.deadline_ms).all()
        assert r.completed_requests==completed.sum() and r.unplaced_requests==unplaced.sum()
        assert r.sla_breaches==f.breach.sum()
        close(r.sla_breach_rate,f.breach.mean()); close(r.mean_request_latency_ms,valid.latency_ms.mean())
        close(r.mean_slot_latency_ms,f.groupby("arrival_slot").latency_ms.mean().mean())
        for metric,p in (("median_latency_ms",.5),("p95_latency_ms",.95),("p99_latency_ms",.99)):
            close(r[metric],linear_quantile(valid.latency_ms,p)); quantiles+=1
        assert r.completed_after_horizon==(valid.completion_s>config["slots"]*config["slot_seconds"]).sum()
        for tier in ("Gold","Silver","Bronze"):
            sub=f.loc[f.tier==tier]
            assert r[f"{tier}_requests"]==len(sub) and r[f"{tier}_breaches"]==sub.breach.sum()
            close(r[f"{tier}_breach_rate"],sub.breach.mean())
    print(f"Verified {len(outcomes):,} outcomes and {quantiles} request quantiles",flush=True)
    slots=pd.read_csv(output/"slot_trajectories.csv")
    nodes=pd.read_csv(output/"node_trajectories.csv")
    actions=pd.read_csv(output/"actions.csv")
    lifecycle=pd.read_csv(output/"lifecycle_events.csv")
    attempts=pd.read_csv(output/"routing_attempts.csv")
    snapshots=pd.read_csv(output/"control_snapshot_times.csv")
    blocked=defaultdict(list); retired=defaultdict(lambda:float("inf"))
    for e in lifecycle.itertuples():
        blocked[(e.seed,e.policy,e.replica_id)].append((e.start_s,e.ready_s))
    for e in actions.itertuples():
        ridkey=(e.seed,e.policy,e.replica_id)
        if e.kind=="scale_down": retired[ridkey]=min(retired[ridkey],e.time_s)
        if e.kind=="migrate":
            following=[end for start,end in blocked[ridkey] if start>=e.time_s-1e-9]
            assert following, ("missing migration downtime",ridkey)
            blocked[ridkey].append((e.time_s,min(following)))
    for key in outcome_groups:
        r=indexed.loc[key]
        select=lambda f:f.loc[(f.seed==key[0])&(f.policy==key[1])]
        sf,nf,af,lf,tf,cf=map(select,(slots,nodes,actions,lifecycle,attempts,snapshots))
        assert len(sf)==len(cf)==config["slots"] and len(nf)==config["slots"]*config["node_count"]
        assert r.total_actions==len(af)
        for metric,kind in (("migrations","migrate"),("scale_outs","scale_up"),("scale_ins","scale_down")):
            assert r[metric]==af.kind.eq(kind).sum()
        assert r.cold_starts==lf.kind.eq("cold_start").sum()
        close(r.average_replicas,r.replica_seconds/(config["slots"]*config["slot_seconds"]))
        assert r.peak_replicas==max(sf.replicas.max(),sum(n is not None for n in inputs[key[0]]["initial"].values()))
        for resource in ("cpu","gpu","bandwidth"):
            if resource in ("cpu","gpu"): assert nf[f"{resource}_utilization"].between(-1e-8,1+1e-8).all()
            close(r[f"average_{resource}_utilization"],nf[f"{resource}_utilization"].mean())
        total=sf.set_index("slot").decision_runtime_ms+cf.set_index("slot").runtime_ms
        for field,sample in (("controller_total_instrumented",total),("controller_decision",sf.decision_runtime_ms),("request_routing_decision",tf.runtime_ms)):
            close(r[f"{field}_mean_ms"],sample.mean())
            close(r[f"{field}_p95_ms"],linear_quantile(sample,.95))
        close(r.controller_snapshot_mean_ms,cf.runtime_ms.mean())
        close(r.routing_computation_per_request_ms,tf.runtime_ms.sum()/r.total_requests)
        assert r.routing_attempts==len(tf) and r.routing_no_eligible_attempts==(~tf.success).sum()
        assert r.routing_assignments==tf.success.sum()
    ledger=pd.read_csv(output/"reservation_events.csv")
    for key,f in ledger.groupby(["seed","policy"],sort=False):
        v=inputs[key[0]]
        caps=np.array([[n[k] for k in ("cpu_capacity","gpu_capacity","bandwidth_capacity_mbps")] for n in v["scenario"]["nodes"]])
        resident=np.zeros_like(caps)
        for e in f.itertuples():
            s=v["services"][e.service_id]
            resident[e.node]+=e.sign*np.array([s[k] for k in ("cpu_cores","gpu_vram_gb","bandwidth_mbps")])
            assert (resident>=-1e-8).all() and (resident<=caps+1e-8).all()
            close(resident[e.node],[e.cpu_reserved,e.gpu_vram_reserved,e.bandwidth_reserved])
    previous=None; first={}; last={}; counters=defaultdict(int); routing_count=0; run_count=0
    def finish_routing(key):
        nonlocal run_count
        f=outcome_groups[key];r=indexed.loc[key]
        assert set(last)==set(f.loc[f.latency_ms.notna()].index)
        for request,(rid,node,time) in last.items():
            row=f.loc[request]
            assert (rid,node)==(row.replica_id,row.node)
            assert time<=row.arrival_s+row.service_queue_ms/1000+1e-8
        for field,values in (("routed_away_from_lowest_network_fraction",[x[0] for x in first.values()]),
                             ("queue_changed_choice_fraction",[x[1] for x in first.values()]),
                             ("multi_eligible_fraction",[x[2] for x in first.values()])):
            close(r[field],np.mean(values))
        assert len(first)==r.completed_requests
        run_count+=1
        if key[1]==NEW_POLICIES[-1]: print(f"Routing replay verified seed {key[0]}/30",flush=True)
    score_columns=("estimated_queue_wait_ms","estimated_resource_wait_ms","estimated_completion_ms","slack_ms","risk_proxy","estimated_variance_ms2")
    for chunk in pd.read_csv(output/"routing_decisions.csv.gz",chunksize=30000):
        for e in chunk.itertuples(index=False):
            key=(e.seed,e.policy)
            if key!=previous:
                if previous is not None: finish_routing(previous)
                previous=key;first={};last={};counters=defaultdict(int)
            v=inputs[e.seed];service=v["services"][e.service_id];request=v["requests"][e.request_id]
            assert e.service_id==request["service_id"] and abs(e.arrival_s-request["arrival_s"])<1e-10
            assert e.time_s>=e.arrival_s-1e-10 and abs(e.age_ms-max(0,(e.time_s-e.arrival_s)*1000))<1e-7
            assert abs(e.deadline_ms-service["deadline_ms"])<1e-8
            candidates=json.loads(e.candidates_json)
            assert len(candidates)==e.eligible_count and len({c["id"] for c in candidates})==len(candidates)
            assert e.rr_counter==counters[e.service_id];counters[e.service_id]+=1
            for c in candidates:
                assert c["ready"] and not c["pending"] and not c["retiring"] and c["capacity_feasible"]
                assert c["queue_length"]>=0 and c["cycle_variance_ms2"]>0
                assert not any(start-1e-10<=e.time_s<end-1e-10 for start,end in blocked[(e.seed,e.policy,c["id"])])
                assert e.time_s<retired[(e.seed,e.policy,c["id"])]-1e-10
                n=v["scenario"]["nodes"][c["node"]]
                assert service["cpu_cores"]<=n["cpu_capacity"] and service["gpu_vram_gb"]<=n["gpu_capacity"] and v["gpu_units"][c["node"]]>=1
                net=v["scenario"]["network_latency_ms"][service["ingress"]][c["node"]]+1000*service["payload_mbit"]/n["bandwidth_capacity_mbps"]
                assert abs(c["network_ms"]-net)<1e-8 and abs(c["compute_ms"]-14)<1e-8
            assert e.replica_id==reference_choice(candidates,e.deadline_ms,e.age_ms,e.policy,e.rr_counter)
            chosen=next(c for c in candidates if c["id"]==e.replica_id)
            assert e.node==chosen["node"]
            _,score=reference_score(chosen,e.deadline_ms,e.age_ms,e.policy)
            assert all(abs(getattr(e,column)-expected)<1e-6 for column,expected in zip(score_columns,score))
            lowest=min(candidates,key=lambda c:(c["network_ms"],c["id"]))["id"]
            nq=reference_choice(candidates,e.deadline_ms,e.age_ms,"joint_no_queue",0)
            away=chosen["network_ms"]>min(c["network_ms"] for c in candidates)+1e-12
            assert lowest==e.lowest_network_replica and nq==e.no_queue_choice
            assert away==e.routed_away_from_lowest_network and (e.replica_id!=nq)==e.queue_changed_choice
            first.setdefault(e.request_id,(away,e.replica_id!=nq,len(candidates)>1))
            last[e.request_id]=(e.replica_id,e.node,e.time_s);routing_count+=1
    finish_routing(previous)
    assert run_count==150 and routing_count==indexed.loc[(slice(None),list(NEW_POLICIES)),"routing_assignments"].sum()
    summary=pd.read_csv(output/"summary_statistics.csv")
    for r in summary.itertuples():
        x=raw.loc[raw.policy==r.policy].sort_values("seed")[r.metric].to_numpy()
        assert r.n==30
        close([r.mean,r.standard_deviation,r.median,r.min,r.max],[x.mean(),x.std(ddof=1),np.median(x),x.min(),x.max()])
        close([r.ci95_lower,r.ci95_upper],reference_ci(x,f"{(r.policy,)}:{r.metric}"))
    tests=pd.read_csv(output/"paired_tests.csv"); ablation=pd.read_csv(output/"ablation_tests.csv")
    differences=pd.read_csv(output/"paired_seed_differences.csv")
    assert len(tests)==12 and len(ablation)==8 and len(differences)==600
    for family in (tests,ablation):
        for r in family.itertuples():
            p=raw.pivot(index="seed",columns="policy",values=r.metric).sort_index()
            a,b=p.joint_sla.to_numpy(),p[r.policy_B].to_numpy();d=b-a
            close([r.mean_A,r.mean_B,r.absolute_difference,r.relative_improvement_percent],[a.mean(),b.mean(),d.mean(),100*d.mean()/b.mean()])
            stat,pval,effect=reference_signed_rank(d)
            close([r.test_statistic,r.rank_biserial_correlation],[stat,effect])
            assert np.isclose(r.p_value,pval,rtol=1e-8,atol=1e-14)
            close([r.difference_ci95_lower,r.difference_ci95_upper],reference_ci(d,f"joint:{r.family}:{r.policy_B}:{r.metric}"))
            idx=bootstrap_indices(f"joint-relative:{r.family}:{r.policy_B}:{r.metric}")
            ratio=100*(b[idx].mean(axis=1)-a[idx].mean(axis=1))/b[idx].mean(axis=1)
            close([r.relative_ci95_lower,r.relative_ci95_upper],[linear_quantile(ratio,p) for p in (.025,.975)])
            signs=np.round(d,12)
            assert [r.wins,r.ties,r.losses]==[(signs>0).sum(),(signs==0).sum(),(signs<0).sum()]
            df=differences.loc[(differences.family==r.family)&(differences.baseline_policy==r.policy_B)&(differences.metric==r.metric)].sort_values("seed")
            assert df.seed.tolist()==list(range(1,31))
            close(df.absolute_difference,d);close(df.relative_difference_percent,100*d/b)
            close(df.baseline_value,b);close(df.joint_value,a)
        largest=0
        for rank,index in enumerate(family.p_value.sort_values(kind="stable").index):
            largest=min(1,max(largest,family.loc[index,"p_value"]*(len(family)-rank)))
            close(largest,family.loc[index,"p_value_holm"],1e-14)
        assert family.supported_improvement.eq((family.p_value_holm<.05)&(family.absolute_difference>0)&(family.difference_ci95_lower>0)).all()
    h=json.loads((output/"hypotheses.json").read_text(encoding="utf-8"))
    primary=tests.loc[tests.policy_B=="sla_aware"].set_index("metric")
    base=indexed.xs("sla_aware",level="policy").sort_index();joint=indexed.xs("joint_sla",level="policy").sort_index()
    idx=bootstrap_indices("joint:H4:resources")
    reps=100*(joint.average_replicas.to_numpy()[idx].mean(axis=1)-base.average_replicas.to_numpy()[idx].mean(axis=1))/base.average_replicas.to_numpy()[idx].mean(axis=1)
    vram=(joint.mean_gpu_vram_reserved_pct-base.mean_gpu_vram_reserved_pct).to_numpy()[idx].mean(axis=1)
    repci=[linear_quantile(reps,p) for p in (.025,.975)];vramci=[linear_quantile(vram,p) for p in (.025,.975)]
    close(h["replica_increase_percent_ci95"],repci);close(h["vram_increase_pp_ci95"],vramci)
    expected=dict(H1=bool(primary.loc["sla_breach_rate","supported_improvement"]),H2=bool(primary.loc["p95_latency_ms","supported_improvement"]),
                  H3=bool(primary.loc["p99_latency_ms","supported_improvement"] or primary.loc["p99_latency_ms","relative_ci95_lower"]>=-settings["p99_noninferiority_percent"]))
    expected["H4"]=expected["H1"] and expected["H2"] and repci[1]<=settings["replica_increase_percent"] and vramci[1]<=settings["vram_increase_pp"]
    expected["H5"]=joint.controller_total_instrumented_mean_ms.mean()<=settings["controller_mean_limit_ms"] and joint.request_routing_decision_p95_ms.mean()<=settings["routing_p95_limit_ms"]
    assert all(h[k]==v for k,v in expected.items())
    report=(output/"report.md").read_text(encoding="utf-8")
    for title in ("Research Question","Existing SLA-aware Baseline","Joint Placement and Routing Design","Formal Problem Formulation","Experimental Setup","SLA Results","Mean and Tail Latency","Per-Tier Results","Routing Behavior","Resource Cost","Controller Overhead","Statistical Significance","Wins / Ties / Losses","Negative Results","Interpretation","Threats to Validity","Safe Paper Claims","Claims We Cannot Make"):
        assert f"# {title}" in report
    for r in pd.read_csv(output/"claim_ledger.csv").itertuples():
        reference=primary.loc[r.metric]
        assert reference.supported_improvement and r.sentence in report
        close(r.relative_improvement_percent,reference.relative_improvement_percent)
    from PIL import Image
    pictures=list((output/"figures").glob("*.png"));assert len(pictures)==8
    for path in pictures:
        with Image.open(path) as picture: assert min(picture.info["dpi"])>=299
        assert path.with_suffix(".svg").exists()
        assert path.with_suffix(".pdf").exists()
    assert protected_hashes()==protocol["protected_baseline_hashes"]
    result=dict(combined_runs=270,new_runs=150,reused_runs=120,seeds=[1,30],request_outcomes_checked=len(outcomes),
                request_quantiles_checked=quantiles,routing_decisions_replayed=routing_count,statistical_comparisons_checked=20,
                baseline_artifacts_unchanged=True,hypotheses_independently_checked=True,figures_checked=8)
    write_json(output/"validation.json",result)
    manifest={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob("*")) if p.is_file() and p.name!="artifact_hashes.json"}
    write_json(output/"artifact_hashes.json",manifest)
    return result
