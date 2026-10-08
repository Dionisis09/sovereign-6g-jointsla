"""Independent reconstruction of calibrated request work and lifecycle units."""
import json
import numpy as np
from joint_routing.validation import reference_choice,reference_score


def validate_run(config,workload,result,service_configs):
    rows=sorted(result['outcomes'],key=lambda r:r['request_id'])
    assert [r['request_id'] for r in rows]==list(range(len(workload.requests))),'lost/duplicate requests'
    for request,row in zip(workload.requests,rows):
        service=workload.services[request.service_id];c=service_configs[request.service_id]
        assert row['service_id']==request.service_id and row['arrival_slot']==request.arrival_slot
        assert row['arrival_s']==request.arrival_s and row['deadline_ms']==service.deadline_ms and row['tier']==service.tier
        if row['unplaced']:
            assert workload.initial[request.service_id] is None and row['breach'];continue
        actual=1000*(row['completion_s']-request.arrival_s)
        compute=(c.preprocess_ms+c.inference_ms+c.postprocess_ms)*request.work_factor
        node=workload.scenario.nodes[row['node']]
        network=workload.scenario.network_latency_ms[service.ingress,row['node']]+1000*request.payload_mbit/node.bandwidth_capacity_mbps
        components=[row[k] for k in ('service_queue_ms','node_queue_ms','compute_ms','network_ms','lifecycle_penalty_ms')]
        assert np.isfinite(components).all() and min(components)>=-1e-7
        assert abs(actual-row['latency_ms'])<1e-6 and abs(actual-sum(components))<1e-6
        assert abs(compute-row['compute_ms'])<1e-6 and abs(network-row['network_ms'])<1e-6
        assert row['breach']==(actual>service.deadline_ms)
    ledger=np.zeros_like(workload.scenario.capacities)
    for event in result['reservations']:
        ledger[event['node']]+=event['sign']*workload.services[event['service_id']].reservation
        assert (ledger>=-1e-8).all() and (ledger<=workload.scenario.capacities+1e-8).all()
        assert np.allclose(ledger[event['node']],[event[k] for k in ('cpu_reserved','gpu_vram_reserved','bandwidth_reserved')])
    assert len(result['slots'])==config.slots and len(result['nodes'])==config.slots*config.node_count
    for row in result['nodes']:
        assert all(-1e-8<=row[f'{r}_utilization']<=1+1e-8 for r in ('cpu','gpu','bandwidth'))
    for row in result['lifecycle']:
        sid=result['replica_services'][row['replica_id']];c=service_configs[sid]
        duration=(c.cold_start_slots if row['kind']=='cold_start' else c.migration_down_slots)*c.slot_seconds
        assert abs(row['ready_s']-row['start_s']-duration)<1e-8
    assert sum(r['accepted_actions'] for r in result['slots'])==len(result['actions'])
    routing_checks=0
    for row in result['routing']:
        candidates=json.loads(row['candidates_json'])
        assert row['time_s']>=row['arrival_s']-1e-9
        assert row['replica_id']==reference_choice(candidates,row['deadline_ms'],row['age_ms'],'joint_sla',row['rr_counter'])
        chosen=next(c for c in candidates if c['id']==row['replica_id'])
        assert chosen['ready'] and not chosen['pending'] and not chosen['retiring'] and chosen['capacity_feasible']
        _,expected=reference_score(chosen,row['deadline_ms'],row['age_ms'],'joint_sla')
        for field,value in zip(('estimated_queue_wait_ms','estimated_resource_wait_ms','estimated_completion_ms','slack_ms','risk_proxy','estimated_variance_ms2'),expected):
            assert np.isclose(row[field],value,atol=1e-7)
        routing_checks+=1
    return dict(requests_verified=len(rows),routing_choices_verified=routing_checks,reservation_events_verified=len(result['reservations']),
        node_slots_verified=len(result['nodes']),lifecycle_intervals_verified=len(result['lifecycle']),accounting_complete=True)
