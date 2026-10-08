"""Scale-preserving inputs and timing-only delegation of the verified policies."""
from dataclasses import asdict,replace
import numpy as np
import pytest
from catalyst.reused import digest
from dynamic_placement.workload import generate_workload,Request
from dynamic_placement.simulator import Simulator
from dynamic_placement.metrics import validate_run
from joint_routing.simulator import RoutedSimulator
from scalability.configuration import SCALES,POLICIES,configuration,workload_summary,consistency_checks
from scalability.measurement import MeasuredBaseline,MeasuredRouted,normalized_metrics
from scalability.experiment import safe_output


def test_only_size_configuration_changes():
    small=asdict(configuration("SMALL"))
    for scale,(n,s) in SCALES.items():
        c=asdict(configuration(scale))
        assert c.pop("node_count")==n and c.pop("service_count")==s and s/n==4
        assert c=={k:v for k,v in small.items() if k not in ("node_count","service_count")}


@pytest.mark.parametrize("scale",SCALES)
def test_deterministic_generation_tiers_and_hashes(scale):
    c=configuration(scale);a=generate_workload(c,7);b=generate_workload(c,7)
    assert digest(a.to_dict())==digest(b.to_dict())
    assert len({r.request_id for r in a.requests})==len(a.requests)
    summary=workload_summary(scale,c,a)
    assert summary["services_per_node"]==4 and summary["burst_multiplier"]==3
    assert abs(summary["Gold_proportion"]-.35)<=.04
    assert all(s.cpu_cores<=2 and s.gpu_vram_gb<=7 for s in a.services)


@pytest.mark.parametrize("scale",SCALES)
@pytest.mark.parametrize("policy",POLICIES)
def test_instrumentation_identical_accounting_and_routing(scale,policy):
    c=replace(configuration(scale),slots=3);w=generate_workload(c,1);before=digest(w.to_dict())
    original=Simulator(c,w,policy).run() if policy=="sla_aware" else RoutedSimulator(c,w,policy).run()
    engine=MeasuredBaseline(c,w,policy) if policy=="sla_aware" else MeasuredRouted(c,w,policy)
    measured=engine.run();validate_run(c,w,measured)
    assert measured["outcomes"]==original["outcomes"] and measured["actions"]==original["actions"]
    assert measured["reservations"]==original["reservations"] and measured["lifecycle"]==original["lifecycle"]
    assert before==digest(w.to_dict()) and len(measured["timing"]["eligible_slot_samples"])==3
    if policy!="sla_aware":
        def strip(rows):return [{k:v for k,v in r.items() if k!="runtime_ms"} for r in rows]
        assert strip(measured["routing"])==strip(original["routing"])
        import json
        for r in measured["routing"]:
            assert all(c["ready"] and c["capacity_feasible"] and not c["pending"] and not c["retiring"] for c in json.loads(r["candidates_json"]))


@pytest.mark.parametrize("scale",SCALES)
def test_future_tape_does_not_change_past_routing(scale):
    c=replace(configuration(scale),slots=3);w=generate_workload(c,2)
    future=replace(w,requests=tuple(replace(r,work_factor=500) if r.arrival_s>=.2 else r for r in w.requests),
                   traffic=tuple({**t,"burst":True} if t["slot"]>=2 else t for t in w.traffic))
    def prefix(result):return [{k:v for k,v in r.items() if k!="runtime_ms"} for r in result["routing"] if r["time_s"]<.2]
    assert prefix(MeasuredRouted(c,w,"joint_sla").run())==prefix(MeasuredRouted(c,future,"joint_sla").run())


def test_normalized_metrics_use_correct_denominators():
    c=configuration("MEDIUM")
    m=dict(total_requests=20000,completed_requests=19900,total_actions=50,cold_starts=20,average_replicas=60,sla_breach_rate=.25,vram_gb_seconds=1000)
    t=dict(wall_clock_seconds=2,simulation_cpu_seconds=1.9,routing_cpu_ms=500,eligible_replica_seconds=500,
           control_cpu_times=[dict(snapshot_cpu_ms=10,policy_cpu_ms=20,apply_cpu_ms=5)])
    d=normalized_metrics(m,c,t,21000)
    assert d["wall_seconds_per_100k_requests"]==10
    assert d["controller_cpu_ms_per_request"]==535/20000
    assert d["actions_per_1000_requests"]==2.5 and d["replicas_per_service"]==1.5
    assert d["vram_reserved_gib_per_node"]==10 and d["sla_violations_per_1000_requests"]==250
    assert d["average_eligible_replicas"]==50 and d["routing_decisions_per_simulation_wall_second"]==10500


def test_protected_output_rejected_even_when_nested():
    from scalability.configuration import ROOT
    for name in ("results/paper_30seeds","results/joint_routing_30seeds/subdir","dynamic_placement",""):
        with pytest.raises(ValueError):safe_output(ROOT/name)
    assert safe_output(ROOT/"results/scalability_30seeds").name=="scalability_30seeds"


def inference_fixture():
    import pandas as pd
    rows=[]
    for scale,(nodes,services) in SCALES.items():
        factor=nodes/5
        for seed in range(1,31):
            for policy in POLICIES:
                joint=policy=="joint_sla"
                rows.append(dict(scale=scale,seed=seed,policy=policy,sla_breach_rate=(.5 if joint else .6)+seed*.0001,
                    mean_request_latency_ms=(200 if joint else 300)+seed,p95_latency_ms=(800 if joint else 1200)+seed,
                    p99_latency_ms=(1600 if joint else 2000)+seed,average_replicas=(25 if joint else 27)*factor,
                    replicas_per_service=(25 if joint else 27)/20,mean_gpu_vram_reserved_pct=90 if joint else 94,
                    vram_reserved_gib_per_node=22 if joint else 23,cold_starts=25 if joint else 29,
                    cold_starts_per_1000_requests=(25 if joint else 29)/(6*factor),total_actions=44 if joint else 51,
                    actions_per_1000_requests=(44 if joint else 51)/(6*factor),migrations=0,
                    controller_decision_mean_ms=2,controller_total_instrumented_mean_ms=5,
                    controller_total_instrumented_p95_ms=8,request_routing_decision_p95_ms=.1,controller_cpu_ms_per_request=.2))
    return pd.DataFrame(rows)


def test_scale_pairing_and_single_global_holm_family():
    from scalability.analysis import paired
    raw=inference_fixture();tests,differences=paired(raw,"sla_aware","primary")
    assert len(tests)==12 and len(differences)==360 and tests.supported_improvement.all()
    assert tests.wins.eq(30).all() and tests.p_value_holm.ge(tests.p_value).all()
    assert tests.groupby("scale").size().eq(4).all()


def test_large_reversal_and_budget_failure_retained():
    from scalability.analysis import paired,resource_comparisons,hypotheses
    raw=inference_fixture();mask=(raw.scale=="LARGE")&(raw.policy=="joint_sla")
    raw.loc[mask,"sla_breach_rate"]+=.2
    raw.loc[mask,"p95_latency_ms"]+=800
    raw.loc[mask,"controller_total_instrumented_mean_ms"]=30
    tests,d=paired(raw,"sla_aware","primary");h=hypotheses(raw,tests,resource_comparisons(raw))
    assert not h["H1"] and not h["H2"] and not h["H3"] and not h["H4"]
    assert len(d[(d.scale=="LARGE")&(d.outcome=="loss")])==60


def test_resource_action_gate_is_independent_of_latency_gains():
    from scalability.analysis import paired,resource_comparisons,hypotheses
    raw=inference_fixture();mask=(raw.scale=="LARGE")&(raw.policy=="joint_sla")
    raw.loc[mask,"actions_per_1000_requests"]*=2
    tests,_=paired(raw,"sla_aware","primary");h=hypotheses(raw,tests,resource_comparisons(raw))
    assert h["H1"] and h["H2"] and h["H3"] and not h["H5"]


def test_scale_trends_keep_the_original_ci_bounds():
    import pandas as pd
    from scalability.analysis import scale_trends
    s=pd.DataFrame([dict(scale="SMALL",policy="joint_sla",metric="p95_latency_ms",mean=100,ci95_lower=90,ci95_upper=115)])
    t=scale_trends(s).iloc[0]
    assert t["mean"]==100 and t.CI_low==90 and t.CI_high==115


def test_consistency_screen_rejects_difficulty_change():
    import pandas as pd
    c=configuration("SMALL");row=workload_summary("SMALL",c,generate_workload(c,1));rows=[]
    for scale in SCALES:
        new={**row,"scale":scale}
        if scale=="LARGE":new["expected_gpu_pressure"]*=2
        rows.append(new)
    with pytest.raises(ValueError,match="scale consistency failed"):consistency_checks(pd.DataFrame(rows))


def test_replica_distribution_includes_unused_and_initial_creation_order():
    import pandas as pd
    from scalability.analysis import allocated_request_distribution
    initial={5:0,2:1}
    actions=pd.DataFrame([dict(kind="scale_up",replica_id=2,service_id=5)])
    outcomes=pd.DataFrame(dict(service_id=[5,5,2],replica_id=[0,0,1]))
    counts,cv=allocated_request_distribution(outcomes,initial,actions)
    assert counts.set_index("replica_id").requests.to_dict()=={0:2,1:1,2:0}
    assert cv==.5  # service 5 counts [2,0] CV=1; service 2 CV=0


def test_rare_counter_relative_ci_stays_undefined_without_dropping_draws():
    from scalability.analysis import resource_comparisons
    raw=inference_fixture();raw.loc[(raw.policy=="sla_aware")&(raw.seed==1),"migrations"]=1
    r=resource_comparisons(raw)
    rare=r.loc[r.metric=="migrations"]
    assert not rare.relative_defined.any() and rare.relative_CI_low.isna().all() and rare.relative_CI_high.isna().all()
    assert np.isfinite(rare.CI_low).all() and np.isfinite(rare.CI_high).all()
