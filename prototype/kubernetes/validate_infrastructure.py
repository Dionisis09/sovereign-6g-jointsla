"""Live infrastructure checks, deliberately separate from frozen experiments.

Only the owned local kind namespace is touched. The full run deletes an inference
pod, kills the gateway process, and restarts the two monitoring Deployments.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import base64
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from prototype.gateway import fetch
from prototype.kubernetes.validate_runtime import kubectl,ROOT,URL

from prototype.kubernetes.settings import PROM,GRAF,CACHE,CLUSTER,NS

def signal_gateway(pod, signal_name):
    """Signal only the owned gateway from its ancestor (kind node) PID namespace.

    Linux namespace PID 1 ignores unhandled SIGKILL/SIGSTOP sent by a child exec.
    Verify CRI identity before touching a node PID; never target the node's init.
    """
    if signal_name not in ('KILL','STOP','CONT'): raise ValueError('Unsupported signal')
    if pod['metadata']['namespace']!=NS or pod['metadata']['labels'].get('app')!='jointsla-gateway':
        raise ValueError('Refusing a non-owned gateway')
    container=pod['status']['containerStatuses'][0]['containerID']
    if not container.startswith('containerd://'): raise ValueError('Expected local kind containerd')
    node=CLUSTER+'-control-plane'
    info=json.loads(subprocess.check_output(['docker','exec',node,'crictl','inspect',container.split('://')[1]],text=True,timeout=15))
    labels=info['status']['labels'];pid=info['info']['pid']
    if (labels.get('io.kubernetes.pod.uid')!=pod['metadata']['uid'] or
        labels.get('io.kubernetes.pod.namespace')!=NS or labels.get('io.kubernetes.container.name')!='gateway' or
        type(pid) is not int or pid<=1): raise ValueError('CRI identity/PID mismatch')
    subprocess.run(['docker','exec',node,'/bin/kill','-'+signal_name,str(pid)],check=True,timeout=15)
    return pid

def wait(predicate, seconds=180):
    cutoff=time.monotonic()+seconds
    last=None
    while time.monotonic()<cutoff:
        try:
            last=predicate()
            if last: return last
        except (OSError,ValueError,subprocess.CalledProcessError): pass
        time.sleep(1)
    raise AssertionError(f'Condition timed out ({seconds}s); last={last}')

def query(expr, timestamp=None):
    params={'query':expr}
    if timestamp is not None: params['time']=timestamp
    code,result=fetch(PROM+'/api/v1/query?'+urlencode(params))
    assert code==200 and result['status']=='success',result
    return result['data']['result']

def smoke():
    # A rollout can finish between two telemetry snapshots. Do not send the
    # validation request using a pre-rollout cache or retry already executed work.
    started=time.time()
    wait(lambda: fetch(URL+'/ready')[0]==200 and fetch(URL+'/state')[1].get('snapshot_unix_s',0)>=started)
    code,result=fetch(URL+'/infer',{'seed':123,'tier':'Gold','deadline_ms':200})
    assert code==200 and result['pretrained'] is True and len(result['predictions'])==3,result
    targets=wait(lambda: healthy_targets())
    code,dashboard=fetch(GRAF+'/api/dashboards/uid/jointsla-runtime')
    assert code==200 and len(dashboard['dashboard']['panels'])>=8
    print('Smoke passed: real pretrained inference, healthy metrics, provisioned Grafana.',flush=True)
    return {'inference':result,'healthy_targets':[{'labels':t['labels'],'health':t['health']} for t in targets],'grafana_panels':len(dashboard['dashboard']['panels'])}

def healthy_targets():
    code,result=fetch(PROM+'/api/v1/targets')
    targets=result.get('data',{}).get('activeTargets',[])
    return targets if code==200 and len(targets)>=3 and all(t['health']=='up' for t in targets) else None

def grafana(path, body=None):
    password=(CACHE/'grafana-admin-password').read_text()
    auth=base64.b64encode(('admin:'+password).encode()).decode()
    request=Request(GRAF+path,data=json.dumps(body).encode() if body is not None else None,
                    headers={'Authorization':'Basic '+auth,'Content-Type':'application/json'})
    with urlopen(request,timeout=5) as response: return json.load(response)

def main():
    out=ROOT/'prototype/.cache'/('infrastructure_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    out.mkdir(parents=True)
    report={'status':'running','output':str(out),'started_utc':datetime.now(timezone.utc).isoformat()}
    try:
        report['smoke']=smoke()
        deployments=json.loads(kubectl('get','deployments','-o','json'))['items']
        for d in deployments:
            for c in d['spec']['template']['spec']['containers']:
                assert all(probe in c for probe in ('readinessProbe','livenessProbe','startupProbe'))
                assert all(k in c['resources'][scope] for scope in ('requests','limits') for k in ('cpu','memory'))
                assert c['securityContext']['readOnlyRootFilesystem']
        report['probe_resource_security_deployments']=[d['metadata']['name'] for d in deployments]
        rules=fetch(PROM+'/api/v1/rules')[1]['data']['groups']
        assert len(rules)==1 and len(rules[0]['rules'])==4 and all(r['health']=='ok' for r in rules[0]['rules'])
        report['alerts']=[r['name'] for r in rules[0]['rules']]
        account='system:serviceaccount:jointsla-prototype:jointsla-controller'
        checks={}
        for verb,resource,subresource,expected in [('patch','deployments/inference','scale','yes'),('patch','deployments/gateway','scale','no'),('get','secrets',None,'no'),('delete','pods',None,'no')]:
            # kubectl returns 1 for an expected denial.
            from prototype.kubernetes.validate_runtime import KUBECTL
            command=[*KUBECTL,'auth','can-i',verb,resource,'--as='+account]
            if subresource: command.append('--subresource='+subresource)
            result=subprocess.run(command,capture_output=True,text=True,timeout=15)
            key=verb+' '+resource+('/'+subresource if subresource else '')
            checks[key]=result.stdout.strip()
            assert checks[key]==expected,(command,result.stdout,result.stderr)
        report['rbac']=checks
        print('Probe/resource/security and least-privilege checks passed.',flush=True)
        wait(lambda: fetch(URL+'/state')[1].get('ready_replicas')==2)
        pods=json.loads(kubectl('get','pods','-l','app=jointsla-inference','-o','json'))['items']
        victim=next(p for p in pods if not p['metadata'].get('deletionTimestamp') and any(c['type']=='Ready' and c['status']=='True' for c in p['status']['conditions']))
        from prototype.kubernetes.validate_runtime import KUBECTL
        forward=subprocess.Popen([*KUBECTL,'port-forward','pod/'+victim['metadata']['name'],'18085:8080'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0)
        direct='http://127.0.0.1:18085'
        try:
            wait(lambda: fetch(direct+'/ready')[0]==200,30)
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures=[pool.submit(fetch,direct+'/infer',{'seed':i,'deadline_ms':60000},60) for i in range(8)]
                def queued():
                    state=fetch(direct+'/state')[1]
                    return state if state['queue']>0 else None
                before=wait(queued,10)
                kubectl('exec',victim['metadata']['name'],'--','python','-c','import os,signal; os.kill(1,signal.SIGTERM)')
                responses=[f.result() for f in futures]
            kubectl('delete','pod',victim['metadata']['name'],'--wait=false')
            assert all(code==200 and len(r['predictions'])==3 for code,r in responses),responses
            report['pod_drain']={'queued_before_sigterm':before['queue'],'busy_before_sigterm':before['busy'],'requests':8,'complete_http_responses':8,'removed_uid':victim['metadata']['uid'],
                                'outcomes':[{'request':i,'status':code,'prediction_count':len(r['predictions'])} for i,(code,r) in enumerate(responses)]}
        finally:
            forward.terminate();forward.wait(timeout=10)
        warm_samples=[]
        def recovered():
            pods=json.loads(kubectl('get','pods','-l','app=jointsla-inference','-o','json'))['items']
            state=fetch(URL+'/state')[1]
            endpoints=state.get('endpoints',[])
            for p in pods:
                if p['metadata']['uid']==victim['metadata']['uid']: continue
                ready=any(c['type']=='Ready' and c['status']=='True' for c in p['status'].get('conditions',[]))
                if not ready:
                    ip=p.get('status',{}).get('podIP')
                    assert not ip or 'http://'+ip+':8080' not in endpoints
                    warm_samples.append({'uid':p['metadata']['uid'],'ready':False,'routed':False})
            return state.get('ready_replicas')==2 and all(p['metadata']['uid']!=victim['metadata']['uid'] for p in pods)
        wait(recovered)
        report['warmup_exclusion_samples']=warm_samples
        print('SIGTERM: 8 complete responses; cold replacement excluded until ready.',flush=True)
        gateway=json.loads(kubectl('get','pods','-l','app=jointsla-gateway','-o','json'))['items'][0]
        initial_restarts=gateway['status']['containerStatuses'][0]['restartCount']
        signal_gateway(gateway,'KILL')
        def restarted():
            p=json.loads(kubectl('get','pod',gateway['metadata']['name'],'-o','json'))
            return p['status']['containerStatuses'][0]['restartCount']>initial_restarts and fetch(URL+'/ready')[0]==200
        wait(restarted)
        report['gateway_crash_recovery']={'uid':gateway['metadata']['uid'],'restart_count_increased':True,'ready_after_restart':True}
        print('Gateway process crash recovered.',flush=True)
        smoke()
        # SIGSTOP leaves PID 1 alive but unable to serve. Probes must restart it;
        # observability must expose the real outage, not just loaded rule syntax.
        stopped=json.loads(kubectl('get','pod',gateway['metadata']['name'],'-o','json'))
        restart_before=stopped['status']['containerStatuses'][0]['restartCount']
        signal_gateway(stopped,'STOP')
        try:
            wait(lambda: any(a['labels'].get('alertname')=='JointSLAGatewayUnavailable' and a['state']=='firing'
                             for a in fetch(PROM+'/api/v1/alerts')[1]['data']['alerts']),60)
            def probe_restarted():
                p=json.loads(kubectl('get','pod',gateway['metadata']['name'],'-o','json'))
                return p['status']['containerStatuses'][0]['restartCount']>restart_before and fetch(URL+'/ready')[0]==200
            wait(probe_restarted,180)
            report['liveness_recovery']={'hung_process_restarted':True,'gateway_unavailable_alert_fired':True}
            print('Hung gateway: outage alert fired and liveness restarted the container.',flush=True)
        finally:
            # Safe if already restarted; resume a stopped PID if validation fails.
            try: signal_gateway(json.loads(kubectl('get','pod',gateway['metadata']['name'],'-o','json')),'CONT')
            except (ValueError,KeyError,subprocess.SubprocessError): pass
        smoke()
        # Counters are born lazily after the first request in a restarted process.
        # Capture a confirmed sample BEFORE monitoring restart, rather than asking
        # for a historical timestamp that can precede the counter's creation.
        wait(lambda: query('jointsla_gateway_requests_total'))
        timestamp=time.time()
        history=query('jointsla_gateway_requests_total',timestamp)
        assert history
        marker='infra-validation-'+out.name
        annotation=grafana('/api/annotations',{'text':marker,'tags':['infrastructure-validation'],'time':int(time.time()*1000)})
        report['grafana_annotation_id']=annotation['id']
        for name in ('prometheus','grafana'):
            kubectl('rollout','restart','deployment/'+name)
            kubectl('rollout','status','deployment/'+name,'--timeout=120s')
        wait(lambda: fetch(GRAF+'/api/health')[0]==200)
        assert query('jointsla_gateway_requests_total',timestamp)==history
        annotations=grafana('/api/annotations?'+urlencode({'tags':'infrastructure-validation','limit':100}))
        assert any(a['id']==annotation['id'] and a['text']==marker for a in annotations)
        report['monitoring_restart_persistence']={'prometheus_historical_samples_preserved':True,'grafana_annotation_preserved':True}
        report['final_smoke']=smoke()
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=repr(error))
        raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__': main()
