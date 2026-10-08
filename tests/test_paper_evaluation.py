"""Statistical mechanisms and accounting, without changing simulator fixtures."""
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from catalyst.reused import digest
from dynamic_placement.config import Config
from dynamic_placement.workload import generate_workload, Request
from dynamic_placement.simulator import Simulator
from dynamic_placement.policies import POLICIES as CONTROLLERS
from paper_evaluation.accounting import request_metrics, validate_pairing, POLICIES, PRIMARY
from paper_evaluation.statistics import bootstrap_mean_ci, signed_rank, paired_analysis, holm_adjust
from paper_evaluation.validation import linear_quantile, reference_signed_rank
from run_paper_experiments import parse_seeds


@pytest.fixture
def paired_raw():
    rows=[]
    for seed in range(1,31):
        for policy in POLICIES:
            baseline=policy!="sla_aware"
            rows.append(dict(seed=seed,policy=policy,traffic_hash=f"t{seed}",workload_hash=f"w{seed}",total_requests=100,
                             **{m:(10+seed+(3 if baseline else 0))*(.01 if m=="sla_breach_rate" else 1) for m in PRIMARY}))
    return pd.DataFrame(rows)


def test_paper_identical_tapes_and_separate_seeds():
    c=Config(slots=3)
    a,b=generate_workload(c,1),generate_workload(c,1)
    assert digest(a.to_dict())==digest(b.to_dict())
    assert digest(a.to_dict())!=digest(generate_workload(c,2).to_dict())
    tape=digest(a.to_dict())
    for policy in POLICIES:
        result=Simulator(c,a,policy).run()
        assert len(result["outcomes"])==len(a.requests)
        assert digest(a.to_dict())==tape


@pytest.mark.parametrize("corruption",["duplicate","missing","traffic","counts"])
def test_invalid_pairing_rejected(paired_raw,corruption):
    raw=paired_raw.copy()
    if corruption=="duplicate": raw=pd.concat([raw,raw.iloc[:1]])
    if corruption=="missing": raw=raw.iloc[1:]
    if corruption=="traffic": raw.loc[0,"traffic_hash"]="different"
    if corruption=="counts": raw.loc[0,"total_requests"]=99
    with pytest.raises(ValueError): validate_pairing(raw,range(1,31))


def accounting_fixture():
    return pd.DataFrame(dict(request_id=range(6),tier=["Gold","Silver","Bronze","Silver","Bronze","Gold"],
                             arrival_slot=[0,0,1,1,1,1],latency_ms=[0.,10.,20.,30.,None,None],
                             breach=[False,False,False,True,True,True],dropped=[False]*4+[True,False],
                             unplaced=[False]*5+[True]))


def test_request_percentiles_are_not_slot_percentiles():
    m=request_metrics(accounting_fixture())
    assert m["median_latency_ms"]==15
    assert m["p95_latency_ms"]==pytest.approx(28.5)
    assert m["p99_latency_ms"]==pytest.approx(29.7)
    assert m["p95_latency_ms"]!=np.quantile([5,25],.95)
    assert linear_quantile([0,10,20,30],.99)==pytest.approx(29.7)


def test_tier_and_drop_accounting():
    m=request_metrics(accounting_fixture())
    assert m["total_requests"]==6 and m["completed_requests"]==4
    assert m["dropped_requests"]==m["unplaced_requests"]==1
    assert m["sla_breaches"]==3 and m["sla_breach_rate"]==.5
    assert m["drop_rate"]==pytest.approx(1/6)
    assert m["Bronze_drop_rate"]==.5
    assert all(m[f"{t}_requests"]==2 and m[f"{t}_breach_rate"]==.5 for t in ("Gold","Silver","Bronze"))


def test_failed_drop_cannot_disappear_from_denominator():
    f=accounting_fixture()
    f.loc[4,"breach"]=False
    with pytest.raises(ValueError): request_metrics(f)


def test_unaccounted_or_duplicate_request_rejected():
    f=accounting_fixture()
    f.loc[5,"unplaced"]=False
    with pytest.raises(ValueError): request_metrics(f)
    with pytest.raises(ValueError): request_metrics(pd.concat([f.iloc[:4],f.iloc[:1]]))


def test_completion_aware_tail_includes_post_horizon_requests():
    c=Config(slots=1)
    w=generate_workload(c,2)
    service=w.services[0]
    initial={s.service_id:None for s in w.services};initial[0]=0
    requests=tuple(Request(i,0,.099,0,1.,service.payload_mbit) for i in range(30))
    w=replace(w,requests=requests,initial=initial)
    result=Simulator(c,w,"static").run()
    f=pd.DataFrame(result["outcomes"])
    assert len(f)==30 and (f.completion_s>.1).all()
    m=request_metrics(f)
    assert m["completed_requests"]==30 and m["p99_latency_ms"]>m["median_latency_ms"]
    assert m["mean_request_latency_ms"]==pytest.approx(f.latency_ms.mean())


def test_bootstrap_ci_is_reproducible_and_shift_equivariant():
    x=np.arange(30,dtype=float)
    a=bootstrap_mean_ci(x,"fixture")
    assert a==bootstrap_mean_ci(x,"fixture")
    assert np.allclose(bootstrap_mean_ci(x+10,"fixture"),np.array(a)+10)
    assert a[0]<x.mean()<a[1]
    assert bootstrap_mean_ci(np.full(30,3.),"constant")== (3.,3.)
    assert bootstrap_mean_ci([1,2],"two")== (1.,2.)


@pytest.mark.parametrize("values,resamples",[([1,np.nan],10000),([1],10000),([1,2],9999)])
def test_invalid_ci_inputs(values,resamples):
    with pytest.raises(ValueError): bootstrap_mean_ci(values,resamples=resamples)


def test_wilcoxon_known_reference_and_effect():
    d=[6,8,14,16,23,24,28,29,41,-48,49,56,60,-67,75]
    r=signed_rank(d)
    assert r["test_statistic"]==24 and r["p_value"]==pytest.approx(.041259765625)
    assert r["rank_biserial_correlation"]==pytest.approx(.6)
    assert reference_signed_rank(d)==pytest.approx((24,.041259765625,.6))


def test_wilcoxon_ties_zero_and_reversed_effect():
    r=signed_rank([1,1,-1,0])
    assert r["wilcoxon_method"]=="asymptotic"
    assert r["rank_biserial_correlation"]==pytest.approx(1/3)
    assert tuple(r[k] for k in ("test_statistic","p_value","rank_biserial_correlation"))==pytest.approx(reference_signed_rank([1,1,-1,0]))
    assert signed_rank([-1,-2,-3])["rank_biserial_correlation"]==-1
    zero=signed_rank([0]*30)
    assert zero["p_value"]==1 and zero["rank_biserial_correlation"]==0


def test_paired_pipeline_signs_holm_and_losses_visible(paired_raw):
    paired_raw.loc[(paired_raw.seed==30)&(paired_raw.policy=="sla_aware"),"p99_latency_ms"]=100
    tests,diffs=paired_analysis(paired_raw,range(1,31))
    assert len(tests)==12 and len(diffs)==360
    assert tests.loc[tests.metric!="p99_latency_ms","wins"].eq(30).all()
    assert tests.loc[tests.metric=="p99_latency_ms","losses"].eq(1).all()
    assert (tests.p_value_holm>=tests.p_value).all()
    assert diffs.loc[(diffs.seed==30)&(diffs.metric=="p99_latency_ms"),"absolute_difference"].lt(0).all()
    assert np.allclose(holm_adjust([.01,.04,.03]),[.03,.06,.06])


def test_controller_future_tape_changes_cannot_affect_past_decisions(monkeypatch):
    c=Config(slots=4)
    w=generate_workload(c,1)
    past=tuple(r for r in w.requests if r.arrival_slot<2)
    # Change only future requests. Traffic metadata also changes, but snapshots exclude it.
    other=replace(w,requests=past,traffic=tuple({**t,"burst":True,"expected_rate_rps":9999} if t["slot"]>=2 else t for t in w.traffic))
    for policy in POLICIES:
        original=CONTROLLERS[policy]
        recorded=[]
        def observer(config,snapshot):
            assert not {"requests","traffic","future_arrivals","burst"}.intersection(snapshot)
            actions=original(config,snapshot)
            if snapshot["slot"]<2:
                serializable={k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in snapshot.items()}
                recorded.append(digest(dict(snapshot=serializable,actions=actions)))
            return actions
        monkeypatch.setitem(CONTROLLERS,policy,observer)
        Simulator(c,w,policy).run()
        first=recorded.copy();recorded.clear()
        Simulator(c,other,policy).run()
        assert first==recorded
        monkeypatch.setitem(CONTROLLERS,policy,original)


def test_inclusive_seed_specification():
    assert parse_seeds("1:30")==list(range(1,31))
    with pytest.raises(Exception): parse_seeds("1:29")
