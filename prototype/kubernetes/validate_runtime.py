"""Controlled live test: warm repair, burst scaling, scale-in and pod failure.

Only the named local kind context/namespace is touched. Run after deploying.
Outputs are per-request evidence, not a new paired paper experiment.
"""
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time
from prototype.gateway import fetch
from prototype.load import run as load

from prototype.kubernetes.settings import ROOT,NS,URL,KUBECTL,CLUSTER

def kubectl(*args):
    return subprocess.check_output([*KUBECTL,*args],text=True,timeout=30)

def validate_outcomes(folder,summary):
    """Reconcile every offered request and deadline against exported CSV evidence."""
    rows=list(csv.DictReader((Path(folder)/'request_outcomes.csv').open(encoding='utf-8')))
    assert len(rows)==summary['offered']
    assert sorted(int(r['request']) for r in rows)==list(range(summary['offered']))
    assert sum(r['status']=='200' for r in rows)==summary['completed']
    for r in rows:
        expected=int(r['status'])!=200 or float(r['latency_ms'])>float(r['deadline_ms'])
        assert (r['sla_failure']=='True')==expected
        if r['status']=='200': assert r['pretrained']=='True'
    assert abs(sum(r['sla_failure']=='True' for r in rows)/len(rows)-summary['sla_failure_rate'])<1e-12
    return len(rows)

def main():
    out=ROOT/'prototype/.cache'/('kubernetes_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    out.mkdir(parents=True,exist_ok=False)
    timeline=[];start=time.monotonic()
    def sample(phase):
        code,state=fetch(URL+'/state',timeout=3)
        assert code==200 and state['backend']=='KubernetesAdapter',state
        deployment=json.loads(kubectl('get','deployment','inference','-o','json'))
        row=dict(elapsed_s=time.monotonic()-start,phase=phase,
            controller_target=state.get('desired_replicas',0),deployment_target=deployment['spec']['replicas'],
            ready_by_controller=state.get('ready_replicas',0),ready_by_deployment=deployment['status'].get('readyReplicas',0),
            queue=state.get('queue',0),rate_rps=state.get('observed_rate_rps',0),endpoints=';'.join(state.get('endpoints',[])))
        timeline.append(row)
        return row
    def wait_for(phase,predicate,timeout=120):
        cutoff=time.monotonic()+timeout
        while time.monotonic()<cutoff:
            row=sample(phase)
            if predicate(row): return row
            time.sleep(1)
        raise AssertionError(f'{phase} timed out; latest: {timeline[-1]}')
    def checkpoint():
        if timeline:
            with (out/'replica_timeline.csv').open('w',newline='',encoding='utf-8') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(timeline[0]));writer.writeheader();writer.writerows(timeline)
        (out/'gateway.log').write_text(kubectl('logs','deployment/gateway'),encoding='utf-8')
        (out/'pods.json').write_text(kubectl('get','pods','-o','json'),encoding='utf-8')
        (out/'deployment.json').write_text(kubectl('get','deployment','inference','-o','json'),encoding='utf-8')
    try:
        wait_for('warm_floor',lambda r:r['deployment_target']==2 and r['ready_by_controller']==2 and r['ready_by_deployment']==2)
        print('Warm floor: 2 real ready replicas',flush=True)
        baseline=load(URL,60,6,11,str(out/'baseline'))
        # Let the unchanged 30-second action cooldown after warm repair expire.
        cutoff=time.monotonic()+35
        while time.monotonic()<cutoff: sample('settle');time.sleep(1)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(load,URL,1280,32,23,str(out/'burst'),120.)
            while not future.done(): sample('burst');time.sleep(.5)
            burst=future.result()
        peak=max(r['deployment_target'] for r in timeline if r['phase']=='burst')
        print(f'Burst peak: {peak} desired real pods',flush=True)
        assert peak>2,'The offered burst did not exercise scale-out; inspect outcomes and timeline'
        burst_rows=list(csv.DictReader((out/'burst/request_outcomes.csv').open(encoding='utf-8')))
        assert len({r['routed_to'] for r in burst_rows if r['status']=='200'})>=3,'New replicas did not serve traffic'
        wait_for('scale_in',lambda r:r['deployment_target']==2 and r['ready_by_controller']==2 and r['ready_by_deployment']==2)
        print('Scale-in: returned to warm floor 2',flush=True)
        pods=json.loads(kubectl('get','pods','-l','app=jointsla-inference','-o','json'))['items']
        ready=[p for p in pods if not p['metadata'].get('deletionTimestamp') and
               any(c['type']=='Ready' and c['status']=='True' for c in p['status'].get('conditions',[]))]
        victim=ready[0];victim_ip=victim['status']['podIP'];victim_uid=victim['metadata']['uid']
        kubectl('delete','pod',victim['metadata']['name'],'--wait=false')
        failure=load(URL,80,2,31,str(out/'failure'))
        verified_outcomes={phase:validate_outcomes(out/phase,summary) for phase,summary in
                           [('baseline',baseline),('burst',burst),('failure',failure)]}
        assert failure['completed']>=76,'Failover caused more than four unsuccessful requests; inspect outcomes'
        recovered=wait_for('failure_recovery',lambda r:r['ready_by_controller']==2 and r['ready_by_deployment']==2
                           and victim_ip not in r['endpoints'])
        # Ready replacement pods can coexist briefly with the draining old UID.
        wait_for('pod_termination',lambda r:victim_uid not in [p['metadata']['uid'] for p in
                 json.loads(kubectl('get','pods','-l','app=jointsla-inference','-o','json'))['items']])
        final_pods=json.loads(kubectl('get','pods','-l','app=jointsla-inference','-o','json'))['items']
        assert victim_uid not in [p['metadata']['uid'] for p in final_pods]
        checkpoint()
        events=[json.loads(line) for line in (out/'gateway.log').read_text().splitlines() if line.startswith('{')]
        applied=[e for e in events if e.get('event')=='reconciliation' and e.get('outcome')=='applied']
        assert any(e['desired_replicas']>2 for e in applied)
        assert any(e['desired_replicas']==2 for e in applied)
        report=dict(status='passed',cluster='kind-'+CLUSTER,physical_hosts=1,kubernetes_nodes=1,
                    cpu_inference=True,pretrained=True,baseline=baseline,burst=burst,failure=failure,
                    peak_deployment_replicas=peak,final_ready_replicas=recovered['ready_by_controller'],
                    applied_controller_actions=applied,removed_pod_uid=victim_uid,removed_pod_ip=victim_ip,
                    verified_request_outcomes=verified_outcomes,
                    kube_replaces_failed_pods=True,paper_statistics_updated=False)
        (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(dict(output=str(out),**report),indent=2),flush=True)
    except Exception as failure:
        checkpoint()
        (out/'verification.json').write_text(json.dumps(dict(status='failed',error=str(failure)),indent=2),encoding='utf-8')
        raise

if __name__=='__main__': main()
