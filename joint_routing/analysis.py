"""Reuse the verified seed-level inference primitives for new comparisons."""
import hashlib
from dataclasses import asdict
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json
from paper_evaluation.statistics import summarize,bootstrap_mean_ci,signed_rank,holm_adjust,rng_for,RESAMPLES
from paper_evaluation.accounting import PRIMARY
from paper_evaluation.experiments import ROOT
from .experiment import ALL_POLICIES,protected_hashes


def comparisons(raw,baselines,family):
    rows=[];differences=[]
    for baseline in baselines:
        for metric in PRIMARY:
            pivot=raw.pivot(index="seed",columns="policy",values=metric).sort_index()
            a,b=pivot.joint_sla.to_numpy(),pivot[baseline].to_numpy();d=b-a
            ci=bootstrap_mean_ci(d,key=f"joint:{family}:{baseline}:{metric}")
            indices=rng_for(f"joint-relative:{family}:{baseline}:{metric}").integers(0,30,(RESAMPLES,30))
            bm,am=b[indices].mean(axis=1),a[indices].mean(axis=1)
            relative_ci=np.quantile(100*(bm-am)/bm,[.025,.975])
            signs=np.round(d,12)
            rows.append(dict(family=family,metric=metric,policy_A="joint_sla",policy_B=baseline,n=30,
                             mean_A=float(a.mean()),mean_B=float(b.mean()),absolute_difference=float(d.mean()),
                             difference_ci95_lower=ci[0],difference_ci95_upper=ci[1],
                             relative_improvement_percent=float(100*d.mean()/b.mean()),
                             relative_ci95_lower=float(relative_ci[0]),relative_ci95_upper=float(relative_ci[1]),
                             test_used="Wilcoxon signed-rank, two-sided",**signed_rank(d),
                             wins=int((signs>0).sum()),ties=int((signs==0).sum()),losses=int((signs<0).sum())))
            for seed,bv,av,delta in zip(pivot.index,b,a,d):
                differences.append(dict(family=family,seed=int(seed),baseline_policy=baseline,metric=metric,
                                        baseline_value=float(bv),joint_value=float(av),absolute_difference=float(delta),
                                        relative_difference_percent=float(100*delta/bv),
                                        outcome="win" if round(delta,12)>0 else "loss" if round(delta,12)<0 else "tie"))
    tests=pd.DataFrame(rows)
    tests["p_value_holm"]=holm_adjust(tests.p_value)
    tests["significant_at_0_05"]=tests.p_value<.05
    tests["significant_holm_0_05"]=tests.p_value_holm<.05
    tests["supported_improvement"]=tests.significant_holm_0_05 & (tests.absolute_difference>0) & (tests.difference_ci95_lower>0)
    return tests,pd.DataFrame(differences)


def evaluate_hypotheses(raw,tests,settings):
    primary=tests.loc[tests.policy_B=="sla_aware"].set_index("metric")
    pivot=raw.set_index(["seed","policy"])
    base=pivot.xs("sla_aware",level="policy").sort_index()
    joint=pivot.xs("joint_sla",level="policy").sort_index()
    idx=rng_for("joint:H4:resources").integers(0,30,(RESAMPLES,30))
    replica_increase=100*(joint.average_replicas.to_numpy()[idx].mean(axis=1)-base.average_replicas.to_numpy()[idx].mean(axis=1))/base.average_replicas.to_numpy()[idx].mean(axis=1)
    vram_increase=(joint.mean_gpu_vram_reserved_pct-base.mean_gpu_vram_reserved_pct).to_numpy()[idx].mean(axis=1)
    rep_ci=np.quantile(replica_increase,[.025,.975]);vram_ci=np.quantile(vram_increase,[.025,.975])
    h1=bool(primary.loc["sla_breach_rate","supported_improvement"])
    h2=bool(primary.loc["p95_latency_ms","supported_improvement"])
    h3=bool(primary.loc["p99_latency_ms","supported_improvement"] or primary.loc["p99_latency_ms","relative_ci95_lower"]>=-settings.p99_noninferiority_percent)
    h4=bool(h1 and h2 and rep_ci[1]<=settings.replica_increase_percent and vram_ci[1]<=settings.vram_increase_pp)
    h5=bool(joint.controller_total_instrumented_mean_ms.mean()<=settings.controller_mean_limit_ms
            and joint.request_routing_decision_p95_ms.mean()<=settings.routing_p95_limit_ms)
    return dict(H1=h1,H2=h2,H3=h3,H4=h4,H5=h5,
                replica_increase_percent_ci95=[float(x) for x in rep_ci],vram_increase_pp_ci95=[float(x) for x in vram_ci],
                mean_controller_total_ms=float(joint.controller_total_instrumented_mean_ms.mean()),
                mean_seed_routing_p95_ms=float(joint.request_routing_decision_p95_ms.mean()),
                decision="supports additional coupled value in this model" if h1 and h2 and h3 and h4 and h5 else "predeclared coupled success criteria not all met",
                interpretation="hypothesis screens are conditional on this configuration; H4 is a comparable-resource check, not causal efficiency proof")


def analyze(raw,output,settings):
    assert raw.groupby("policy").size().eq(30).all() and set(raw.policy)==set(ALL_POLICIES)
    assert not raw.duplicated(["seed","policy"]).any()
    for _,group in raw.groupby("seed"):
        assert group.traffic_hash.nunique()==group.workload_hash.nunique()==group.total_requests.nunique()==1
    sources=[ROOT/"joint_routing/analysis.py",ROOT/"joint_routing/presentation.py",ROOT/"joint_routing/validation.py"]
    write_json(output/"analysis_protocol.json",dict(source_hashes={p.relative_to(ROOT).as_posix():digest(p.read_text(encoding="utf-8")) for p in sources},
               statistical_primitives="unchanged paper_evaluation.statistics",bootstrap_resamples=10000,
               paired_design=True,positive_difference="baseline minus JointSLA",settings=asdict(settings)))
    summarize(raw).to_csv(output/"summary_statistics.csv",index=False)
    main,diffs=comparisons(raw,("sla_aware","sla_rr","sla_shortest_queue"),"main")
    ablation,adiffs=comparisons(raw,("joint_no_queue","joint_no_slack"),"exploratory_ablation")
    main.to_csv(output/"paired_tests.csv",index=False)
    ablation.to_csv(output/"ablation_tests.csv",index=False)
    pd.concat([diffs,adiffs],ignore_index=True).to_csv(output/"paired_seed_differences.csv",index=False)
    hypotheses=evaluate_hypotheses(raw,main,settings)
    write_json(output/"hypotheses.json",hypotheses)
    base=raw.loc[raw.policy=="sla_aware"].set_index("seed")
    costs=[]
    for policy in raw.policy.unique():
        g=raw.loc[raw.policy==policy].set_index("seed")
        sla=100*(base.sla_breach_rate.mean()-g.sla_breach_rate.mean())
        latency=base.mean_request_latency_ms.mean()-g.mean_request_latency_ms.mean()
        rep=g.average_replicas.mean()-base.average_replicas.mean()
        vram=g.mean_gpu_vram_reserved_pct.mean()-base.mean_gpu_vram_reserved_pct.mean()
        actions=g.total_actions.mean()-base.total_actions.mean()
        costs.append(dict(policy=policy,sla_reduction_pp=sla,latency_reduction_ms=latency,
                          additional_average_replicas=rep,additional_vram_residency_pp=vram,additional_actions=actions,
                          sla_pp_per_additional_replica=sla/rep if rep>1e-12 else None,
                          sla_pp_per_additional_vram_pp=sla/vram if vram>1e-12 else None,
                          latency_ms_per_additional_action=latency/actions if actions>1e-12 else None,
                          ratio_definition="undefined when extra resource/action <=0; diagnostic ratios of means, not universal metrics"))
    pd.DataFrame(costs).to_csv(output/"resource_normalized_analysis.csv",index=False)
    distribution=[]
    for f in pd.read_csv(output/"request_outcomes.csv.gz",chunksize=40000):
        distribution.append(f.groupby(["seed","policy","service_id","replica_id","node"]).size().rename("requests").reset_index())
    counts=pd.concat(distribution).groupby(["seed","policy","service_id","replica_id","node"],as_index=False).requests.sum()
    counts.to_csv(output/"replica_request_distribution.csv",index=False)
    return hypotheses
