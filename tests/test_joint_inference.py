"""Guard against positive claims on ties, losses, or excess resource costs."""
import numpy as np
import pandas as pd
from joint_routing.analysis import comparisons,evaluate_hypotheses
from joint_routing.router import Settings
from paper_evaluation.accounting import PRIMARY
from paper_evaluation.validation import reference_signed_rank


def paired_fixture():
    rows=[]
    for seed in range(1,31):
        for policy in ("sla_aware","sla_rr","sla_shortest_queue","joint_sla"):
            joint=policy=="joint_sla"
            row=dict(seed=seed,policy=policy,average_replicas=18 if joint else 20,
                     mean_gpu_vram_reserved_pct=80 if joint else 90,
                     controller_total_instrumented_mean_ms=5,request_routing_decision_p95_ms=.2)
            row.update({m:(10 if joint else 20)+seed*.01 for m in PRIMARY})
            rows.append(row)
    return pd.DataFrame(rows)


def test_paired_direction_holm_and_all_ties_are_not_benefit():
    raw=paired_fixture()
    tests,diffs=comparisons(raw,("sla_aware","sla_rr","sla_shortest_queue"),"main")
    assert len(tests)==12 and len(diffs)==360 and tests.supported_improvement.all()
    for r in tests.itertuples():
        stat,p,effect=reference_signed_rank(np.full(30,10.))
        assert np.isclose(r.test_statistic,stat) and np.isclose(r.p_value,p)
        assert r.rank_biserial_correlation==effect==1 and r.wins==30
    for metric in PRIMARY: raw.loc[raw.policy=="joint_sla",metric]+=10
    ties,_=comparisons(raw,("sla_aware",),"main")
    assert ties.ties.eq(30).all() and ties.p_value.eq(1).all() and not ties.supported_improvement.any()


def test_losses_are_retained_with_negative_effect():
    raw=paired_fixture()
    for metric in PRIMARY: raw.loc[raw.policy=="joint_sla",metric]+=20
    tests,diffs=comparisons(raw,("sla_aware",),"main")
    assert tests.losses.eq(30).all() and tests.rank_biserial_correlation.eq(-1).all()
    assert diffs.outcome.eq("loss").all() and not tests.supported_improvement.any()


def test_resource_and_overhead_gates_cannot_be_rescued_by_latency():
    raw=paired_fixture()
    tests,_=comparisons(raw,("sla_aware","sla_rr","sla_shortest_queue"),"main")
    h=evaluate_hypotheses(raw,tests,Settings())
    assert all(h[k] for k in ("H1","H2","H3","H4","H5"))
    raw.loc[raw.policy=="joint_sla","average_replicas"]=30
    raw.loc[raw.policy=="joint_sla","controller_total_instrumented_mean_ms"]=11
    h=evaluate_hypotheses(raw,tests,Settings())
    assert h["H1"] and h["H2"] and not h["H4"] and not h["H5"]


def test_p99_noninferiority_screen_rejects_wide_negative_interval():
    raw=paired_fixture()
    tests,_=comparisons(raw,("sla_aware",),"main")
    mask=tests.metric=="p99_latency_ms"
    tests.loc[mask,"supported_improvement"]=False
    tests.loc[mask,"relative_ci95_lower"]=-5.01
    assert not evaluate_hypotheses(raw,tests,Settings())["H3"]
    tests.loc[mask,"relative_ci95_lower"]=-5.
    assert evaluate_hypotheses(raw,tests,Settings())["H3"]
