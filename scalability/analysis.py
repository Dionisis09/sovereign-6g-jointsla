"""Unchanged seed-level inference primitives applied to three fixed scales."""
import json
import gzip
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json
from paper_evaluation.statistics import summarize,bootstrap_mean_ci,signed_rank,holm_adjust,rng_for,RESAMPLES
from paper_evaluation.accounting import PRIMARY
from .configuration import ROOT,SCALES,POLICIES


def paired(raw,baseline,family):
    rows=[];differences=[]
    for scale in SCALES:
        sub=raw.loc[raw.scale==scale]
        for metric in PRIMARY:
            pivot=sub.pivot(index="seed",columns="policy",values=metric).sort_index()
            a,b=pivot.joint_sla.to_numpy(),pivot[baseline].to_numpy();d=b-a
            ci=bootstrap_mean_ci(d,key=f"scalability:{family}:{scale}:{metric}")
            idx=rng_for(f"scalability-relative:{family}:{scale}:{metric}").integers(0,30,(RESAMPLES,30))
            relative=100*(b[idx].mean(axis=1)-a[idx].mean(axis=1))/b[idx].mean(axis=1)
            lo,hi=np.quantile(relative,[.025,.975]);signs=np.round(d,12)
            rows.append(dict(scale=scale,family=family,metric=metric,policy_A="joint_sla",policy_B=baseline,n=30,
                             mean_A=float(a.mean()),mean_B=float(b.mean()),absolute_difference=float(d.mean()),
                             difference_ci95_lower=ci[0],difference_ci95_upper=ci[1],relative_improvement_percent=float(100*d.mean()/b.mean()),
                             relative_ci95_lower=float(lo),relative_ci95_upper=float(hi),**signed_rank(d),
                             wins=int((signs>0).sum()),ties=int((signs==0).sum()),losses=int((signs<0).sum())))
            for seed,av,bv,delta in zip(pivot.index,a,b,d):
                differences.append(dict(scale=scale,seed=int(seed),metric=metric,baseline_policy=baseline,
                                        sla_aware_value=float(bv) if baseline=="sla_aware" else None,
                                        comparator_value=float(bv),joint_value=float(av),difference=float(delta),
                                        outcome="win" if round(delta,12)>0 else "loss" if round(delta,12)<0 else "tie"))
    f=pd.DataFrame(rows);f["p_value_holm"]=holm_adjust(f.p_value)
    f["supported_improvement"]=(f.p_value_holm<.05)&(f.absolute_difference>0)&(f.difference_ci95_lower>0)
    return f,pd.DataFrame(differences)


def resource_comparisons(raw):
    rows=[]
    for scale in SCALES:
        indexed=raw.loc[raw.scale==scale].set_index(["seed","policy"])
        j=indexed.xs("joint_sla",level="policy").sort_index();b=indexed.xs("sla_aware",level="policy").sort_index()
        for metric in ("average_replicas","replicas_per_service","mean_gpu_vram_reserved_pct","vram_reserved_gib_per_node",
                       "cold_starts","cold_starts_per_1000_requests","total_actions","actions_per_1000_requests","migrations",
                       "controller_decision_mean_ms","controller_total_instrumented_mean_ms","controller_cpu_ms_per_request"):
            a,x=j[metric].to_numpy(),b[metric].to_numpy();delta=a-x
            lo,hi=bootstrap_mean_ci(delta,key=f"scalability-resource:{scale}:{metric}")
            idx=rng_for(f"scalability-resource-relative:{scale}:{metric}").integers(0,30,(RESAMPLES,30))
            denominator=x[idx].mean(axis=1)
            # Rare counters (e.g. migrations) can have zero entire seed resamples.
            # Do not delete those draws or manufacture a finite ratio interval.
            defined=bool(x.mean()>0 and np.all(denominator>0))
            if defined:
                pct=100*(a[idx].mean(axis=1)-denominator)/denominator
                plo,phi=np.quantile(pct,[.025,.975]);percent=100*(a.mean()-x.mean())/x.mean()
            else:plo=phi=percent=None
            rows.append(dict(scale=scale,metric=metric,sla_aware_mean=float(x.mean()),joint_mean=float(a.mean()),
                             joint_minus_baseline=float(delta.mean()),CI_low=lo,CI_high=hi,
                             relative_increase_percent=float(percent) if defined else None,
                             relative_CI_low=float(plo) if defined else None,relative_CI_high=float(phi) if defined else None,
                             relative_defined=defined,relative_definition="undefined if any paired bootstrap baseline mean is zero; absolute CI retained"))
    return pd.DataFrame(rows)


def hypotheses(raw,tests,resources):
    flags=tests.set_index(["scale","metric"])
    supported=lambda scale,metric:bool(flags.loc[(scale,metric),"supported_improvement"])
    h1=all(supported(s,"sla_breach_rate") for s in SCALES)
    h2=all(supported(s,"p95_latency_ms") for s in SCALES)
    large=tests.loc[(tests.scale=="LARGE")&tests.metric.isin(("sla_breach_rate","p95_latency_ms"))]
    h3=sum(supported(s,"sla_breach_rate") and supported(s,"p95_latency_ms") for s in SCALES)>=2 and large.absolute_difference.ge(0).all() and large.losses.le(15).all()
    overhead=[];fairness=[]
    for scale in SCALES:
        j=raw.loc[(raw.scale==scale)&(raw.policy=="joint_sla")]
        overhead.append(dict(scale=scale,controller_mean_ms=float(j.controller_total_instrumented_mean_ms.mean()),
                             controller_p95_ms=float(j.controller_total_instrumented_p95_ms.mean()),
                             routing_p95_ms=float(j.request_routing_decision_p95_ms.mean()),
                             passed=bool(j.controller_total_instrumented_mean_ms.mean()<=10 and j.controller_total_instrumented_p95_ms.mean()<=100 and j.request_routing_decision_p95_ms.mean()<=1)))
        r=resources.loc[resources.scale==scale].set_index("metric")
        passed=r.loc["average_replicas","relative_CI_high"]<=5 and r.loc["mean_gpu_vram_reserved_pct","CI_high"]<=2 and r.loc["actions_per_1000_requests","relative_CI_high"]<=5
        fairness.append(dict(scale=scale,replica_relative_upper=float(r.loc["average_replicas","relative_CI_high"]),
                             vram_pp_upper=float(r.loc["mean_gpu_vram_reserved_pct","CI_high"]),
                             normalized_actions_relative_upper=float(r.loc["actions_per_1000_requests","relative_CI_high"]),passed=bool(passed)))
    return dict(H1=bool(h1),H2=bool(h2),H3=bool(h3),H4=all(r["passed"] for r in overhead),H5=all(r["passed"] for r in fairness),
                overhead_by_scale=overhead,resources_by_scale=fairness,
                scope="conditional synthetic-model evidence; performance persistence, computational budget and resource fairness are distinct conclusions")


def scale_trends(summary):
    return summary[["scale","policy","metric","mean","ci95_lower","ci95_upper"]].rename(columns={"ci95_lower":"CI_low","ci95_upper":"CI_high"})


def allocated_request_distribution(outcomes,initial,actions):
    """All allocated IDs, including retired/unused, in the original creation order."""
    mapping={rid:int(sid) for rid,(sid,node) in enumerate((item for item in initial.items() if item[1] is not None))}
    if "kind" in actions:
        for a in actions.loc[actions.kind=="scale_up"].itertuples():mapping[int(a.replica_id)]=int(a.service_id)
    assert outcomes.service_id.eq(outcomes.replica_id.map(mapping)).all()
    counts=outcomes.replica_id.value_counts();rows=[];cvs=[]
    for sid in sorted(set(mapping.values())):
        replicas=[rid for rid,s in mapping.items() if s==sid]
        numbers=counts.reindex(replicas,fill_value=0).to_numpy(dtype=float)
        if numbers.mean()>0:cvs.append(numbers.std()/numbers.mean())
        for rid,n in zip(replicas,numbers):rows.append(dict(service_id=sid,replica_id=rid,requests=int(n)))
    return pd.DataFrame(rows),float(np.mean(cvs))


def analyze(raw,output):
    assert len(raw)==270 and not raw.duplicated(["scale","seed","policy"]).any()
    assert raw.groupby(["scale","policy"]).size().eq(30).all()
    paths=[ROOT/"scalability"/n for n in ("analysis.py","presentation.py","validation.py")]
    write_json(output/"analysis_protocol.json",dict(source_hashes={p.relative_to(ROOT).as_posix():digest(p.read_text(encoding="utf-8")) for p in paths},
               main_family=12,secondary_family=12,bootstrap_resamples=10000,statistical_primitives="unchanged paper_evaluation.statistics"))
    # Supplemental observed imbalance covers the common-FIFO baseline as well.
    raw=raw.copy();distribution=[]
    # Keep arrival-cohort volume distinct from actual completions during T.
    raw["requests_completed_within_horizon_per_slot"]=(raw.completed_requests-raw.completed_after_horizon)/100
    raw["fraction_completed_after_horizon"]=raw.completed_after_horizon/raw.completed_requests
    for index,r in raw.iterrows():
        folder=output/"runs"/r.scale/f"seed_{int(r.seed):03d}"/r.policy
        with gzip.open(output/"inputs"/r.scale/f"seed_{int(r.seed):03d}.json.gz","rt") as stream:v=json.load(stream)
        requests=pd.read_csv(folder/"request_outcomes.csv.gz",usecols=["service_id","replica_id"])
        actions=pd.read_csv(folder/"actions.csv.gz")
        counts,cv=allocated_request_distribution(requests,v["initial"],actions)
        raw.loc[index,"replica_load_imbalance_cv"]=cv
        distribution.append(counts.assign(scale=r.scale,seed=int(r.seed),policy=r.policy))
    raw.to_csv(output/"raw_results.csv",index=False)
    pd.concat(distribution,ignore_index=True).to_csv(output/"replica_load_distribution.csv",index=False)
    raw[["scale","seed","policy","routing_decisions","queue_changed_choice_fraction","routed_away_from_lowest_network_fraction",
         "multi_eligible_fraction","replica_load_imbalance_cv","average_eligible_replicas","completed_requests_per_average_eligible_replica"]].to_csv(output/"routing_analysis.csv",index=False)
    summary=summarize(raw,group_columns=("scale","policy"))
    summary.to_csv(output/"summary_statistics.csv",index=False)
    scale_trends(summary).to_csv(output/"scale_trends.csv",index=False)
    main,differences=paired(raw,"sla_aware","primary");secondary,sd=paired(raw,"sla_shortest_queue","secondary")
    main.to_csv(output/"paired_tests.csv",index=False);secondary.to_csv(output/"secondary_paired_tests.csv",index=False)
    differences.to_csv(output/"paired_seed_differences.csv",index=False)
    sd.drop(columns="sla_aware_value").to_csv(output/"secondary_seed_differences.csv",index=False)
    differences.loc[differences.outcome=="loss",["scale","seed","metric","sla_aware_value","joint_value","difference"]].to_csv(output/"negative_seed_cases.csv",index=False)
    main[["scale","metric","relative_improvement_percent","relative_ci95_lower","relative_ci95_upper"]].rename(
        columns={"relative_improvement_percent":"relative_gain","relative_ci95_lower":"CI_low","relative_ci95_upper":"CI_high"}).to_csv(output/"joint_relative_gain_by_scale.csv",index=False)
    resources=resource_comparisons(raw);resources.to_csv(output/"resource_scaling.csv",index=False)
    write_json(output/"hypotheses.json",hypotheses(raw,main,resources))
    metrics=["scale","seed","policy","N_nodes","N_services","mean_active_replicas","total_requests","routing_decisions",
             "controller_decision_mean_ms","controller_decision_p95_ms","controller_total_instrumented_mean_ms","controller_total_instrumented_p95_ms",
             "request_routing_decision_mean_ms","request_routing_decision_p95_ms","control_only_cpu_ms","routing_cpu_ms","total_controller_cpu_ms",
             "controller_cpu_ms_per_request","wall_clock_seconds","wall_seconds_per_100k_requests","sampled_peak_process_rss_mib"]
    overhead=raw[metrics].copy()
    overhead["controller_ms_per_routing_decision"]=np.where(overhead.routing_decisions>0,overhead.total_controller_cpu_ms/overhead.routing_decisions.replace(0,np.nan),np.nan)
    overhead["explicit_routing_available"]=overhead.routing_decisions>0
    overhead.to_csv(output/"controller_overhead_scaling.csv",index=False)
    buckets=[]
    for r in raw.loc[raw.policy!="sla_aware"].itertuples():
        f=output/"runs"/r.scale/f"seed_{r.seed:03d}"/r.policy/"routing_decisions.csv.gz"
        sums={}
        for chunk in pd.read_csv(f,chunksize=10000,usecols=["eligible_count","runtime_ms"]):
            for count,group in chunk.groupby("eligible_count"):
                n,total=sums.get(int(count),(0,0.));sums[int(count)]=(n+len(group),total+group.runtime_ms.sum())
        for count,(n,total) in sums.items():buckets.append(dict(scale=r.scale,seed=r.seed,policy=r.policy,candidate_replicas=count,decisions=n,mean_routing_ms=total/n))
    buckets=pd.DataFrame(buckets);buckets.to_csv(output/"routing_candidate_times.csv",index=False)
    fits=[]
    for policy in POLICIES:
        g=raw.loc[raw.policy==policy].groupby("N_services").controller_decision_mean_ms.mean()
        slope,intercept=np.polyfit(np.log(g.index),np.log(g.values),1)
        fits.append(dict(policy=policy,fit="log policy mean ms ~ log services",slope=float(slope),intercept=float(intercept),
                         scope="descriptive three-scale fit; nodes and services are collinear, not asymptotic proof"))
        if policy!="sla_aware":
            b=buckets.loc[buckets.policy==policy]
            slope,intercept=np.polyfit(b.candidate_replicas,b.mean_routing_ms,1)
            fits.append(dict(policy=policy,fit="seed-bucket mean routing ms ~ candidates",slope=float(slope),intercept=float(intercept),
                             scope="descriptive fit of correlated seed/bucket observations; no significance/complexity claim"))
    pd.DataFrame(fits).to_csv(output/"exploratory_scaling_fits.csv",index=False)
    return main
