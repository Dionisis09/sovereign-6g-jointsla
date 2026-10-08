"""Only node/service counts change; the verified generator is reused as-is."""
from dataclasses import asdict,replace
from pathlib import Path
import numpy as np
import pandas as pd
from catalyst.reused import digest,write_json
from dynamic_placement.config import Config
from dynamic_placement.workload import generate_workload
from dynamic_placement.scenario_model import traffic_hash_payload

ROOT=Path(__file__).resolve().parents[1]
SCALES={"SMALL":(5,20),"MEDIUM":(10,40),"LARGE":(20,80)}
POLICIES=("sla_aware","joint_sla","sla_shortest_queue")


def configuration(scale):
    n,s=SCALES[scale]
    return replace(Config.load(ROOT/"dynamic_placement/config.json"),node_count=n,service_count=s,first_seed=1,trials=30)


def workload_summary(scale,config,w):
    """Exogenous pressure, rather than policy outcomes, establishes comparability."""
    services=w.services;traffic=pd.DataFrame(w.traffic)
    mean_rates=traffic.groupby("service_id").expected_rate_rps.mean()
    caps=w.scenario.capacities
    cpu_work=(config.preprocess_ms+config.postprocess_ms+config.gpu_stage_cpu_fraction*config.inference_ms)/1000
    bursts=traffic.burst.to_numpy().reshape(config.service_count,config.slots)
    starts=bursts[:,0].sum()+np.logical_and(bursts[:,1:],~bursts[:,:-1]).sum()
    deadlines=np.array([s.deadline_ms for s in services])
    d=dict(scale=scale,seed=w.seed,nodes=config.node_count,services=config.service_count,
           services_per_node=config.service_count/config.node_count,total_requests=len(w.requests),
           requests_per_service=len(w.requests)/config.service_count,
           offered_requests_per_node_per_second=len(w.requests)/(config.node_count*config.slots*config.slot_seconds),
           expected_requests_per_node_per_second=float(mean_rates.sum()/config.node_count),
           gpu_execution_units_per_request=1.,mean_gpu_compute_ms=config.inference_ms,
           mean_cpu_demand=float(np.mean([s.cpu_cores for s in services])),
           mean_gpu_vram_demand_gb=float(np.mean([s.gpu_vram_gb for s in services])),
           mean_bandwidth_demand_mbps=float(np.mean([s.bandwidth_mbps for s in services])),
           mean_deadline_ms=float(deadlines.mean()),deadline_p10_ms=float(np.quantile(deadlines,.1)),
           deadline_p50_ms=float(np.quantile(deadlines,.5)),deadline_p90_ms=float(np.quantile(deadlines,.9)),
           expected_cpu_pressure=float(sum(mean_rates[s.service_id]*s.cpu_cores*cpu_work for s in services)/caps[:,0].sum()),
           expected_gpu_pressure=float(mean_rates.sum()*config.inference_ms/1000/sum(w.gpu_units)),
           initial_vram_pressure=float(sum(s.gpu_vram_gb for s in services)/caps[:,1].sum()),
           expected_bandwidth_pressure=float(sum(mean_rates[s.service_id]*s.payload_mbit for s in services)/caps[:,2].sum()),
           mean_node_cpu_capacity=float(caps[:,0].mean()),mean_node_vram_capacity=float(caps[:,1].mean()),
           mean_node_gpu_units=float(np.mean(w.gpu_units)),
           burst_slots_fraction=float(bursts.mean()),bursts_per_service=float(starts/config.service_count),
           burst_multiplier=config.burst_multiplier,burst_period_slots=config.burst_period,
           burst_width_min_slots=config.burst_min_slots,burst_width_max_slots=config.burst_max_slots,
           action_budget_per_slot=config.action_budget,actions_available_per_service_per_slot=config.action_budget/config.service_count,
           initially_unplaced_services=sum(n is None for n in w.initial.values()),
           workload_hash=digest(w.to_dict()),traffic_hash=digest(traffic_hash_payload(w)))
    for tier in ("Gold","Silver","Bronze"):
        values=[s.deadline_ms for s in services if s.tier==tier]
        d[f"{tier}_proportion"]=len(values)/len(services)
        d[f"{tier}_mean_deadline_ms"]=float(np.mean(values))
    return d


def consistency_checks(frame):
    """Fixed pre-outcome tolerance: <=15% shifts of 30-seed means, tier <=4pp."""
    means=frame.groupby("scale").mean(numeric_only=True)
    required=("requests_per_service","offered_requests_per_node_per_second","expected_requests_per_node_per_second",
              "mean_cpu_demand","mean_gpu_vram_demand_gb","mean_bandwidth_demand_mbps","mean_deadline_ms",
              "deadline_p10_ms","deadline_p50_ms","deadline_p90_ms","expected_cpu_pressure","expected_gpu_pressure",
              "initial_vram_pressure","expected_bandwidth_pressure","mean_node_cpu_capacity","mean_node_vram_capacity",
              "mean_node_gpu_units","burst_slots_fraction","bursts_per_service",
              "Gold_mean_deadline_ms","Silver_mean_deadline_ms","Bronze_mean_deadline_ms")
    rows=[]
    for scale in SCALES:
        for metric in required:
            ratio=means.loc[scale,metric]/means.loc["SMALL",metric]
            rows.append(dict(scale=scale,metric=metric,value=float(means.loc[scale,metric]),
                             small_reference=float(means.loc["SMALL",metric]),relative_change=float(ratio-1),
                             criterion="absolute relative change <=0.15",passed=bool(abs(ratio-1)<=.15)))
        for tier in ("Gold","Silver","Bronze"):
            change=means.loc[scale,f"{tier}_proportion"]-means.loc["SMALL",f"{tier}_proportion"]
            rows.append(dict(scale=scale,metric=f"{tier}_proportion",value=float(means.loc[scale,f"{tier}_proportion"]),
                             small_reference=float(means.loc["SMALL",f"{tier}_proportion"]),relative_change=float(change),
                             criterion="absolute fraction change <=0.04",passed=bool(abs(change)<=.04)))
    assert frame.services_per_node.eq(4).all() and frame.burst_multiplier.eq(3).all()
    assert frame.initially_unplaced_services.eq(0).all()
    checks=pd.DataFrame(rows)
    if not checks.passed.all(): raise ValueError("scale consistency failed: "+checks.loc[~checks.passed].to_json(orient="records"))
    return checks


def preflight(output):
    """Validate all 90 workload configurations before any policy simulation."""
    rows=[]
    for scale in SCALES:
        c=configuration(scale)
        for seed in range(1,31):rows.append(workload_summary(scale,c,generate_workload(c,seed)))
    f=pd.DataFrame(rows);checks=consistency_checks(f)
    f.to_csv(output/"scale_configuration_summary.csv",index=False)
    checks.to_csv(output/"scale_consistency_checks.csv",index=False)
    write_json(output/"configuration_validation.json",dict(workloads_checked=90,all_checks_passed=True,
               tolerance_relative_mean=.15,tier_proportion_tolerance_pp=4,
               interpretation="distributional consistency screen across 30 seeds; not exact per-seed pressure equivalence",
               configs={s:asdict(configuration(s)) for s in SCALES}))
    return f
