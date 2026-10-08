"""Pure workload adapters; controllers never receive future arrivals."""
from collections import defaultdict
from dataclasses import replace, asdict
import math
import numpy as np
from dynamic_placement.workload import generate_workload, Request
from scalability.configuration import configuration
from hardware_grounded.calibration import (load_profiles, hardware_workload,
    calibrated_config, configs_for_services, arrival_hash)

LOADS=(.5,.75,1.,1.25,1.5,1.75,2.)
REGIMES={'D0':(0,0,0),'D1':(1,0,0),'D2':(0,1,0),'D3':(0,0,1),
         'D4':(1,1,0),'D5':(1,0,1),'D6':(0,1,1),'D7':(1,1,1)}
POLICIES=('sla_aware','joint_sla')

def scale_traffic(workload,m,config=None):
    """Conditional compound-Poisson thinning/superposition, identity at 1x.

    Cluster marks are independent of original arrival/work streams. Added work
    uses the unchanged lognormal distribution. Service definitions stay fixed.
    """
    if not math.isfinite(m) or m<=0:raise ValueError('positive finite multiplier required')
    if m==1.:return workload
    c=config or configuration('MEDIUM')
    raw=[]
    if m<1:
        groups=defaultdict(list)
        for r in workload.requests:groups[r.service_id,r.arrival_slot,r.arrival_s].append(r)
        for (sid,slot,t),rs in sorted(groups.items()):
            # Float-time bits are deterministic; independent uniform per cluster.
            bits=int(np.float64(t).view(np.uint64))
            rng=np.random.default_rng(np.random.SeedSequence([workload.seed,9101,sid,slot,bits&0xffffffff,bits>>32]))
            if rng.random()<m:raw.extend((r.arrival_s,r.service_id,r.arrival_slot,r.work_factor,r.payload_mbit) for r in rs)
    else:
        raw=[(r.arrival_s,r.service_id,r.arrival_slot,r.work_factor,r.payload_mbit) for r in workload.requests]
        for row in workload.traffic:
            sid,slot=row['service_id'],row['slot'];s=workload.services[sid]
            rng=np.random.default_rng(np.random.SeedSequence([workload.seed,9102,sid,slot]))
            work=np.random.default_rng(np.random.SeedSequence([workload.seed,9103,sid,slot]))
            n=int(rng.poisson((m-1)*row['expected_rate_rps']*c.slot_seconds/c.batch_mean))
            for _ in range(n):
                t=(slot+float(rng.random()))*c.slot_seconds
                for _ in range(int(rng.geometric(1/c.batch_mean))):
                    f=float(work.lognormal(-c.work_sigma**2/2,c.work_sigma))
                    raw.append((t,sid,slot,f,s.payload_mbit))
    raw.sort(key=lambda r:(r[0],r[1]))
    requests=tuple(Request(i,sid,t,slot,f,p) for i,(t,sid,slot,f,p) in enumerate(raw))
    counts=defaultdict(int)
    for r in requests:counts[r.service_id,r.arrival_slot]+=1
    traffic=tuple(dict(row,expected_rate_rps=m*row['expected_rate_rps'],arrivals=counts[row['service_id'],row['slot']]) for row in workload.traffic)
    return replace(workload,requests=requests,traffic=traffic)

def regime_inputs(regime,seed,profiles=None):
    """Change exactly E/V/C components; D0/D7 match frozen endpoints."""
    profiles=profiles or load_profiles();e,v,cold=REGIMES[regime]
    base=configuration('MEDIUM');real=calibrated_config(profiles)
    w=hardware_workload(profiles,seed) if v else generate_workload(base,seed)
    changes={}
    if e:changes.update({k:getattr(real,k) for k in ('preprocess_ms','inference_ms','postprocess_ms')})
    if cold:changes['cold_start_slots']=real.cold_start_slots
    config=replace(base,**changes)
    real_cs=configs_for_services(real,profiles,w.services);cs={}
    for sid,rc in real_cs.items():
        fields={k:getattr(rc,k) for k in ('preprocess_ms','inference_ms','postprocess_ms')} if e else {}
        if cold:fields['cold_start_slots']=rc.cold_start_slots
        cs[sid]=replace(base,**fields)
    return config,w,cs

def regime_definitions():
    return {k:dict(real_execution=bool(e),real_vram=bool(v),real_cold=bool(c)) for k,(e,v,c) in REGIMES.items()}
