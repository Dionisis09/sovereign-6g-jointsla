"""Unchanged seed-level inference for the preregistered adversarial comparisons."""
import numpy as np
import pandas as pd
from catalyst.reused import write_json
from paper_evaluation.accounting import PRIMARY
from paper_evaluation.statistics import summarize,bootstrap_mean_ci,signed_rank,holm_adjust,rng_for,RESAMPLES
from scalability.configuration import SCALES
from .protocol import OUTPUT


def paired(raw,a_policy,b_policy,metrics,family):
    rows=[];seeds=[]
    for scale in SCALES:
        for metric in metrics:
            p=raw[raw.scale==scale].pivot(index="seed",columns="policy",values=metric).sort_index()
            a,b=p[a_policy].to_numpy(),p[b_policy].to_numpy();d=b-a
            key=f"strong:{family}:{scale}:{metric}";lo,hi=bootstrap_mean_ci(d,key=key)
            idx=rng_for("relative:"+key).integers(0,30,(RESAMPLES,30));den=b[idx].mean(axis=1)
            if b.mean()>0 and (den>0).all():
                rel=100*(den-a[idx].mean(axis=1))/den;rlo,rhi=np.quantile(rel,[.025,.975]);point=100*d.mean()/b.mean()
            else:rlo=rhi=point=None
            signs=np.round(d,12)
            rows.append(dict(scale=scale,metric=metric,family=family,policy_A=a_policy,policy_B=b_policy,n=30,
                mean_A=float(a.mean()),mean_B=float(b.mean()),absolute_difference=float(d.mean()),difference_ci95_lower=lo,difference_ci95_upper=hi,
                relative_improvement_percent=point,relative_ci95_lower=rlo,relative_ci95_upper=rhi,
                **signed_rank(d),wins=int((signs>0).sum()),ties=int((signs==0).sum()),losses=int((signs<0).sum())))
            seeds.extend(dict(scale=scale,seed=int(seed),metric=metric,policy_A=a_policy,policy_B=b_policy,A_value=float(av),B_value=float(bv),
                              difference=float(delta),outcome="win" if round(delta,12)>0 else "loss" if round(delta,12)<0 else "tie")
                         for seed,av,bv,delta in zip(p.index,a,b,d))
    frame=pd.DataFrame(rows);frame["p_value_holm"]=holm_adjust(frame.p_value)
    frame["supported_improvement"]=(frame.p_value_holm<.05)&(frame.absolute_difference>0)&(frame.difference_ci95_lower>0)
    return frame,pd.DataFrame(seeds)


def analyze(raw):
    assert len(raw)==270 and not raw.duplicated(["scale","seed","policy"]).any()
    assert raw.groupby(["scale","seed"]).traffic_hash.nunique().eq(1).all()
    raw=raw.copy();raw.to_csv(OUTPUT/"raw_results.csv",index=False)
    summary=summarize(raw,group_columns=("scale","policy"));summary.to_csv(OUTPUT/"summary_statistics.csv",index=False)
    primary,diffs=paired(raw,"joint_sla","mjo",PRIMARY,"primary")
    secondary,secondary_diffs=paired(raw,"mjo","sla_aware",PRIMARY,"strength_sanity")
    overhead,_=paired(raw,"joint_sla","mjo",("controller_total_instrumented_mean_ms",),"overhead")
    primary.to_csv(OUTPUT/"paired_tests.csv",index=False);secondary.to_csv(OUTPUT/"secondary_paired_tests.csv",index=False)
    secondary_diffs.to_csv(OUTPUT/"secondary_seed_differences.csv",index=False)
    secondary_diffs[secondary_diffs.outcome=="loss"].to_csv(OUTPUT/"baseline_strength_negative_cases.csv",index=False)
    overhead.to_csv(OUTPUT/"overhead_paired_tests.csv",index=False)
    diffs.to_csv(OUTPUT/"paired_seed_differences.csv",index=False)
    diffs[diffs.outcome=="loss"].to_csv(OUTPUT/"negative_seed_cases.csv",index=False)
    resource_metrics=("average_replicas","peak_replicas","mean_gpu_vram_reserved_pct","vram_reserved_gib_per_node","total_actions",
                      "actions_per_1000_requests","cold_starts","cold_starts_per_1000_requests","migrations")
    resources,rd=paired(raw,"joint_sla","mjo",resource_metrics,"resource_diagnostics")
    # Resource diagnostics are not another confirmatory claim family; retain
    # bootstrap intervals and transparently label exploratory signed ranks.
    resources["inference_scope"]="exploratory resource diagnostics; H5-style screen uses bootstrap bounds"
    resources.to_csv(OUTPUT/"resource_comparison.csv",index=False)
    controller_cols=[c for c in raw if "controller_" in c or "routing_" in c or c in ("scale","seed","policy","total_requests","wall_clock_seconds","timing_source")]
    raw[controller_cols].to_csv(OUTPUT/"controller_overhead.csv",index=False)
    raw[["scale","seed","policy",*[c for c in raw if c.startswith("solver_")]]].to_csv(OUTPUT/"solver_statistics.csv",index=False)
    tier_cols=["scale","seed","policy",*[c for c in raw if c.startswith(("Gold_","Silver_","Bronze_"))]]
    raw[tier_cols].to_csv(OUTPUT/"tier_results.csv",index=False)
    trade=[]
    for scale in SCALES:
        for policy in ("joint_sla","mjo"):
            f=raw[(raw.scale==scale)&(raw.policy==policy)]
            cpu=f.controller_total_instrumented_mean_ms.mean()
            baseline=raw[(raw.scale==scale)&(raw.policy=="sla_aware")].sla_breach_rate.mean()
            trade.append(dict(scale=scale,policy=policy,sla_breach_rate=float(f.sla_breach_rate.mean()),p95_ms=float(f.p95_latency_ms.mean()),
                full_controller_mean_ms=float(cpu),controller_cpu_ms_per_request=float(f.controller_cpu_ms_per_request.mean()),
                sla_improvement_pp_per_controller_ms=float(100*(baseline-f.sla_breach_rate.mean())/cpu),
                scope="descriptive; historical SLA-aware scientific reference; fresh primary-policy timing; not an efficiency law"))
    pd.DataFrame(trade).to_csv(OUTPUT/"performance_complexity.csv",index=False)
    flags=secondary.set_index(["scale","metric"])
    B1=all(bool(flags.loc[(s,m),"supported_improvement"]) for s in SCALES for m in ("sla_breach_rate","p95_latency_ms"))
    p=primary.set_index(["scale","metric"])
    competitive=lambda metrics:all(p.loc[(s,m),"relative_ci95_lower"]>=-5 for s in SCALES for m in metrics)
    r=resources.set_index(["scale","metric"])
    # Positive relative improvement means MJO uses more than Joint. Its upper
    # MJO-vs-Joint increase must use Joint as denominator: recompute paired ratios.
    fairness=[]
    for scale in SCALES:
        f=raw[raw.scale==scale].set_index(["seed","policy"])
        j=f.xs("joint_sla",level="policy").sort_index();m=f.xs("mjo",level="policy").sort_index()
        row=dict(scale=scale)
        for metric in ("average_replicas","actions_per_1000_requests"):
            idx=rng_for(f"strong:fairness:{scale}:{metric}").integers(0,30,(RESAMPLES,30))
            pct=100*(m[metric].to_numpy()[idx].mean(axis=1)-j[metric].to_numpy()[idx].mean(axis=1))/j[metric].to_numpy()[idx].mean(axis=1)
            row[metric+"_relative_upper"]=float(np.quantile(pct,.975))
        delta=m.mean_gpu_vram_reserved_pct.to_numpy()-j.mean_gpu_vram_reserved_pct.to_numpy()
        row["vram_pp_upper"]=bootstrap_mean_ci(delta,key=f"strong:fairness:{scale}:vram")[1]
        row["passed"]=bool(row["average_replicas_relative_upper"]<=5 and row["actions_per_1000_requests_relative_upper"]<=5 and row["vram_pp_upper"]<=2)
        fairness.append(row)
    write_json(OUTPUT/"hypotheses.json",dict(B1=bool(B1),B2=bool(competitive(("sla_breach_rate",))),
         B3=bool(competitive(("p95_latency_ms","p99_latency_ms"))),B4=bool(overhead.supported_improvement.all()),
         B5=all(r["passed"] for r in fairness),resource_screens=fairness,
         interpretation="B1 gate controls stronger-baseline label; B2/B3 bootstrap operational screens are not proof of equivalence"))
