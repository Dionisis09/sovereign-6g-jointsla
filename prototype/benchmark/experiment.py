"""Serial paired real-inference trials in the isolated owned validation cluster.

All run artifacts are new and immutable. Existing simulator results and the
primary Kubernetes lab are not mutated. CLI pilots cannot be pooled into main.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import threading
import time
from urllib.request import urlopen
import yaml
from kubernetes import client,config
from prototype.gateway import fetch
from prototype.benchmark.load import run as load,tape
from prototype.benchmark.policies import MODES

ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'.cache/kubernetes-validation'
NS='jointsla-prototype'
URL='http://127.0.0.1:18091'
KUBE=['kubectl','--kubeconfig',str(CACHE/'config'),'--context','kind-jointsla-validation','-n',NS]
MAIN=ROOT/'prototype/.cache/kubernetes_comparison_v2'
SETTLE=35
FOLLOW=20


def utc(): return datetime.now(timezone.utc).isoformat()
def write(path,data): Path(path).write_text(json.dumps(data,indent=2),encoding='utf-8')
def command(*args,input=None):
    return subprocess.check_output(KUBE+list(args),input=input,text=True,timeout=180)


def apis():
    config.load_kube_config(config_file=str(CACHE/'config'),context='kind-jointsla-validation')
    configuration=client.Configuration.get_default_copy();configuration.retries=0
    api=client.ApiClient(configuration)
    core,apps,autos=client.CoreV1Api(api),client.AppsV1Api(api),client.AutoscalingV2Api(api)
    nodes=core.list_node(_request_timeout=(2,3)).items
    assert [n.metadata.name for n in nodes]==['jointsla-validation-control-plane']
    return core,apps,autos


class Sampler:
    def __init__(self):
        self.core,self.apps,self.autos=apis()
        self.rows=[];self.stop=threading.Event();self.phase='preparation'
        self.thread=threading.Thread(target=self.loop,daemon=True)

    def sample(self):
        started=time.perf_counter();stamp=time.time()
        try:
            pods=self.core.list_namespaced_pod(NS,label_selector='app=jointsla-inference',_request_timeout=(2,3)).items
            scale=self.apps.read_namespaced_deployment_scale('inference',NS,_request_timeout=(2,3))
            hpas=self.autos.list_namespaced_horizontal_pod_autoscaler(NS,_request_timeout=(2,3)).items
            code,state=fetch(URL+'/state',timeout=2)
            row=dict(unix_s=stamp,phase=self.phase,target=scale.spec.replicas,
                     ready=sum(not p.metadata.deletion_timestamp and any(c.type=='Ready' and c.status=='True' for c in (p.status.conditions or [])) for p in pods),
                     gateway_state=state if code==200 else None,
                     pods=[dict(name=p.metadata.name,uid=p.metadata.uid,ip=p.status.pod_ip,
                         created=p.metadata.creation_timestamp.isoformat(),
                         deleting=p.metadata.deletion_timestamp.isoformat() if p.metadata.deletion_timestamp else None,
                         ready=any(c.type=='Ready' and c.status=='True' for c in (p.status.conditions or [])),
                         conditions=[dict(type=c.type,status=c.status,last_transition=c.last_transition_time.isoformat() if c.last_transition_time else None) for c in (p.status.conditions or [])],
                         containers=[dict(name=c.name,restarts=c.restart_count,state=client.ApiClient().sanitize_for_serialization(c.state)) for c in (p.status.container_statuses or [])]) for p in pods],
                     hpas=[client.ApiClient().sanitize_for_serialization(h) for h in hpas])
        except Exception as failure:
            row=dict(unix_s=stamp,phase=self.phase,sampling_error=str(failure))
        try:
            with urlopen(URL+'/metrics',timeout=2) as response:
                metrics=response.read(2000000).decode()
            value=re.search(r'^jointsla_gateway_decision_seconds ([^\n]+)',metrics,re.M)
            if value: row['control_step_ms']=1000*float(value.group(1))
        except Exception as failure:
            row['control_metric_error']=str(failure)
        row['sampler_step_ms']=(time.perf_counter()-started)*1000
        self.rows.append(row);return row

    def loop(self):
        while not self.stop.is_set():
            self.sample();self.stop.wait(.5)

    def finish(self,folder):
        self.stop.set();self.thread.join(15)
        assert not self.thread.is_alive()
        with (Path(folder)/'timeline.jsonl').open('w',encoding='utf-8') as handle:
            for row in self.rows: handle.write(json.dumps(row)+'\n')


def hpa_document():
    return dict(apiVersion='autoscaling/v2',kind='HorizontalPodAutoscaler',metadata=dict(name='benchmark-hpa',namespace=NS),
        spec=dict(scaleTargetRef=dict(apiVersion='apps/v1',kind='Deployment',name='inference'),minReplicas=2,maxReplicas=4,
                  metrics=[dict(type='Resource',resource=dict(name='cpu',target=dict(type='Utilization',averageUtilization=80)))]))


def pod_items(core,label):
    return core.list_namespaced_pod(NS,label_selector=label,_request_timeout=(2,3)).items


def wait_gateway(apps):
    cutoff=time.monotonic()+120
    while time.monotonic()<cutoff:
        deployment=apps.read_namespaced_deployment('gateway',NS,_request_timeout=(2,3))
        status=deployment.status
        if (status.observed_generation or 0)>=deployment.metadata.generation and status.updated_replicas==1 and status.available_replicas==1:
            return
        time.sleep(.5)
    raise RuntimeError('Fresh gateway did not become available')


def initial_state(core=None,mode=None,require_cpu=False,apps=None):
    if core is None or apps is None:
        live_core,live_apps,_=apis();core=core or live_core;apps=apps or live_apps
    cutoff=time.monotonic()+120
    while time.monotonic()<cutoff:
        pods=pod_items(core,'app=jointsla-inference')
        ready=[p for p in pods if not p.metadata.deletion_timestamp and
               any(c.type=='Ready' and c.status=='True' for c in (p.status.conditions or []))]
        try: status,state=fetch(URL+'/state',timeout=3)
        except (OSError,ValueError):
            time.sleep(.5);continue  # endpoint propagation during reset; never retry a burst request
        target=apps.read_namespaced_deployment_scale('inference',NS,_request_timeout=(2,3)).spec.replicas
        if target==2 and len(pods)==len(ready)==2 and status==200 and state.get('ready_replicas')==2:
            states=state.get('replica_states',[])
            valid_cpu=not require_cpu or state.get('cpu_observation',{}).get('cpu_fraction_of_request') is not None
            matching={s.get('pod_uid') for s in states}=={p.metadata.uid for p in ready}
            if matching and (mode is None or state.get('policy')==mode) and valid_cpu and len(states)==2 and all(s.get('pod_uid') and s.get('queue')==0 and not s.get('busy') for s in states):
                return state
        time.sleep(.5)
    raise RuntimeError('Initial state is not two ready idle instrumented replicas')


def prepare(mode):
    started=time.perf_counter();core,apps,autos=apis()
    def scale(name,count):
        apps.patch_namespaced_deployment_scale(name,NS,dict(spec=dict(replicas=count)),_request_timeout=(2,3))
    # Remove the sole native actuator before disabling/resetting any prior arm.
    try: autos.delete_namespaced_horizontal_pod_autoscaler('benchmark-hpa',NS,_request_timeout=(2,3))
    except client.ApiException as failure:
        if failure.status!=404: raise
    scale('gateway',0)
    cutoff=time.monotonic()+90
    while pod_items(core,'app=jointsla-gateway'):
        if time.monotonic()>cutoff: raise RuntimeError('Old gateway did not drain')
        time.sleep(.5)
    scale('inference',2)
    # Fresh gateway process = fresh request history, optimistic cache and cooldown.
    apps.patch_namespaced_deployment('gateway',NS,dict(spec=dict(replicas=1,
        template=dict(spec=dict(containers=[dict(name='gateway',env=[dict(name='BENCHMARK_POLICY',value=mode)])])))),_request_timeout=(2,3))
    wait_gateway(apps)
    state=initial_state(core,mode,apps=apps)
    pod=pod_items(core,'app=jointsla-gateway')[0].metadata.name
    # Both backend cycle priors receive the same direct preconditioning, independent
    # of the treatment's router. Real model weights stay warm between trials.
    source="""import json
from prototype.gateway import fetch
s=fetch('http://127.0.0.1:8090/state')[1]
for e in s['endpoints']:
 assert fetch(e+'/benchmark/reset',{})[0]==200
 for i in range(8):
  c,r=fetch(e+'/infer',{'seed':i,'tier':'Gold','deadline_ms':2000,'request_id':'precondition-'+str(i)},timeout=60)
  assert c==200 and r['pretrained']
print(json.dumps({'preconditioned':len(s['endpoints'])}))
"""
    command('exec',pod,'--','python','-c',source)
    # Wait past CPU sample windows and controller cooldown for every treatment.
    time.sleep(SETTLE)
    if mode=='hpa':
        autos.create_namespaced_horizontal_pod_autoscaler(NS,hpa_document(),_request_timeout=(2,3))
        cutoff=time.monotonic()+45
        while time.monotonic()<cutoff:
            hpa=autos.read_namespaced_horizontal_pod_autoscaler('benchmark-hpa',NS,_request_timeout=(2,3))
            if hpa.status and any(c.type=='ScalingActive' and c.status=='True' for c in (hpa.status.conditions or [])):
                break
            time.sleep(1)
        else: raise RuntimeError('Native HPA has no valid CPU metric')
    state=initial_state(core,mode,require_cpu=True,apps=apps)
    state['preparation_seconds']=time.perf_counter()-started
    return state


def verify_run(folder,summary):
    import pandas as pd
    rows=pd.read_csv(Path(folder)/'burst/request_outcomes.csv')
    assert len(rows)==summary['offered'] and rows.request.nunique()==len(rows)
    assert ((rows.status!=200)|(rows.latency_ms>rows.deadline_ms)).equals(rows.sla_failure)
    completed=rows[rows.status==200]
    assert completed[['pod_uid','queue_ms','execution_ms','gateway_latency_ms','backend_latency_ms']].notna().all().all()
    assert (completed.pretrained==True).all()
    assert completed.request_id.equals(completed.request_id_echo)
    assert (completed.execution_ms>=0).all() and (completed.queue_ms>=0).all()
    assert (completed.backend_latency_ms>=completed.queue_ms+completed.execution_ms-.1).all()
    unknown=rows[(rows.status!=200)&rows.category.isin(['unknown_rejection','other_http_error'])]
    return dict(outcomes=len(rows),complete_timing_traces=len(completed),unknown_failures=len(unknown),
                categories=summary['categories'],workload_sha256=summary['workload_sha256'])


def trial(mode,seed,folder,count=1280,rate=120.):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    sampler=Sampler();sampler.thread.start()
    try:
        initial=prepare(mode);write(folder/'initial_state.json',initial)
        sampler.phase='burst'
        summary=load(URL,seed,folder/'burst',count,rate)
        sampler.phase='follow_up';time.sleep(FOLLOW)
        verified=verify_run(folder,summary)
        write(folder/'verification.json',dict(status='passed',policy=mode,seed=seed,**verified))
        print(json.dumps(dict(event='trial_completed',policy=mode,seed=seed,completed=summary['completed'],
                              offered=count,sla_failure_percent=100*summary['sla_failures']/count)),flush=True)
        return summary
    except Exception as error:
        write(folder/'verification.json',dict(status='failed',policy=mode,seed=seed,error=str(error)))
        raise
    finally:
        sampler.finish(folder)
        (folder/'gateway.log').write_text(command('logs','deployment/gateway'),encoding='utf-8')
        (folder/'events.json').write_text(command('get','events','-o','json'),encoding='utf-8')


def source_hashes():
    files=sorted((ROOT/'prototype/benchmark').glob('*.py'))+list((ROOT/'prototype/benchmark').glob('Dockerfile'))
    files+=[ROOT/'prototype/gateway.py',ROOT/'prototype/inference.py',ROOT/'prototype/http.py',ROOT/'prototype/controller.py',
            ROOT/'joint_sla_v2/policy.py',ROOT/'joint_routing/router.py',ROOT/'prototype/kubernetes/RESEARCH_EVALUATION_PROTOCOL.md',
            ROOT/'prototype/benchmark/gateway_provenance.json',ROOT/'prototype/benchmark/requirements-analysis.txt',ROOT/'tests/test_kubernetes_comparison.py']
    return {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def schedule():
    rng=random.Random(39107);base=list(MODES);rng.shuffle(base)
    rows=[]
    # Five randomized Latin cycles: each arm occupies every position five times.
    for cycle in range(5):
        rng.shuffle(base)
        rotations=list(range(6));rng.shuffle(rotations)
        for shift in rotations:
            block=len(rows)
            rows.append(dict(block=block,seed=1001+block,order=base[shift:]+base[:shift]))
    return rows


def freeze():
    manifest=MAIN/'manifest.json'
    if manifest.exists():
        frozen=json.loads(manifest.read_text(encoding='utf-8'))
        assert frozen['source_hashes']==source_hashes(),'Benchmark source changed after freeze'
        assert frozen['image_lock']==json.loads((CACHE/'benchmark-image-lock.json').read_text(encoding='utf-8'))
        return frozen
    acceptance=CACHE/'benchmark-pilot-acceptance-v2.json'
    assert acceptance.exists() and json.loads(acceptance.read_text())['passed']
    MAIN.mkdir(parents=True,exist_ok=False)
    runtime=json.loads(command('get','deployments','inference','gateway','-o','json'))
    control=subprocess.check_output(KUBE[:5]+['-n','kube-system','get','pods','-l','component=kube-controller-manager','-o','json'],text=True,timeout=30)
    frozen=dict(deployment_snapshot=runtime,controller_snapshot=json.loads(control),frozen_utc=utc(),protocol_version='kubernetes-comparison-v2',blocks=30,policies=list(MODES),
        schedule=schedule(),count=1280,rate_rps=120,concurrency=32,deadlines_ms=[200,400,800],
        settle_seconds=SETTLE,followup_seconds=FOLLOW,direct_precondition_per_backend=8,
        primary_comparison=['joint','reactive'],secondary_confirmatory=['static','hpa'],
        mechanism_arms=['joint_sq','reactive_joint'],bootstrap_resamples=10000,bootstrap_seed=39108,
        hpa_spec=hpa_document(),hpa_controller_defaults='kind v1.36.4 defaults; no behavior override',
        source_hashes=source_hashes(),image_lock=json.loads((CACHE/'benchmark-image-lock.json').read_text()),
        workload_sha256={str(s):hashlib.sha256(json.dumps(tape(s),sort_keys=True,separators=(',',':')).encode()).hexdigest() for s in range(1001,1031)},
        pilot_acceptance_sha256=hashlib.sha256(acceptance.read_bytes()).hexdigest())
    write(manifest,frozen);return frozen


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true');parser.add_argument('--run',action='store_true');parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args();apis()
    if args.pilot:
        folder=ROOT/'prototype/.cache'/('comparison_pilot_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
        results={}
        for mode in MODES:
            results[mode]=trial(mode,901,folder/mode,count=1280)
        # Longer native-HPA pipeline acceptance, excluded from main statistics.
        results['hpa_sustained_acceptance']=trial('hpa',902,folder/'hpa_sustained',count=4800)
        timeline=[json.loads(line) for line in (folder/'hpa_sustained/timeline.jsonl').read_text().splitlines()]
        assert max(r.get('target',0) for r in timeline)>=3,'Native HPA did not actuate during sustained acceptance'
        assert all(r['workload_sha256']==results['static']['workload_sha256'] for m,r in results.items() if m!='hpa_sustained_acceptance')
        write(CACHE/'benchmark-pilot-acceptance-v2.json',dict(passed=True,checked_utc=utc(),folder=str(folder),summaries=results,
            native_hpa_actuation_observed=True,source_hashes=source_hashes()))
        print('Pilot acceptance passed; pilot data are excluded from main.',flush=True)
    elif args.preflight:
        previous=json.loads((CACHE/'benchmark-pilot-acceptance.json').read_text())
        assert previous['passed'] and previous['native_hpa_actuation_observed']
        current=source_hashes()
        for name in ('prototype/benchmark/policies.py','prototype/benchmark/gateway_runtime.py','prototype/benchmark/inference.py','prototype/benchmark/load.py'):
            assert current[name]==previous['source_hashes'][name],'Serving/workload changed; repeat full pilot'
        folder=ROOT/'prototype/.cache'/('comparison_preflight_v2_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
        folder.mkdir(parents=True,exist_ok=False);results={}
        for mode in MODES:
            results[mode]=prepare(mode);write(folder/(mode+'.json'),results[mode])
            print(json.dumps(dict(event='preparation_accepted',policy=mode,seconds=results[mode]['preparation_seconds'])),flush=True)
        write(CACHE/'benchmark-pilot-acceptance-v2.json',dict(passed=True,checked_utc=utc(),folder=str(folder),
            previous_full_pilot_sha256=hashlib.sha256((CACHE/'benchmark-pilot-acceptance.json').read_bytes()).hexdigest(),
            unchanged_serving_and_workload=True,native_hpa_actuation_observed=True,
            preparation_seconds={m:r['preparation_seconds'] for m,r in results.items()},source_hashes=source_hashes()))
    elif args.run:
        frozen=freeze();total=30*len(MODES);finished=0
        for block in frozen['schedule']:
            for mode in block['order']:
                folder=MAIN/f'block_{block["block"]:02d}'/mode
                if (folder/'verification.json').exists():
                    record=json.loads((folder/'verification.json').read_text())
                    if record['status']!='passed': raise RuntimeError('Failed run retained; cannot selectively replay: '+str(folder))
                    assert record['workload_sha256']==frozen['workload_sha256'][str(block['seed'])]
                else:
                    trial(mode,block['seed'],folder)
                finished+=1
                elapsed=time.time()-datetime.fromisoformat(frozen['frozen_utc']).timestamp()
                write(MAIN/'progress.json',dict(finished=finished,total=total,updated_utc=utc(),
                    elapsed_seconds=elapsed,estimated_remaining_seconds=elapsed/finished*(total-finished)))
                print(f'Progress: {finished}/{total} paired-arm trials',flush=True)
        write(MAIN/'completion.json',dict(status='complete',finished=finished,finished_utc=utc()))
    else: parser.error('Choose --pilot, --preflight or --run')


if __name__=='__main__': main()
