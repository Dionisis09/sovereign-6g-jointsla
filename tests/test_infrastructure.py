"""Infrastructure boundaries; no infrastructure creation or scientific reruns."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace as N
import pytest
import yaml
from prototype.adapters import KubernetesAdapter
from prototype.gateway import Gateway,fetch
from prototype.http import Handler,serve,shutdown_gracefully
from prototype.inference import Inference
from prototype.kubernetes.deploy import deployment_documents

ROOT=Path(__file__).resolve().parents[1]

class Model:
    load_seconds=.1
    def vram(self): return 0
    def predict(self,body): return {'predictions':[1,2,3]}

def test_live_is_independent_of_ready_and_detects_stuck_worker():
    app=Inference(Model())
    app.begin_drain()
    assert app.dispatch('GET','/ready')[0]==503
    assert app.dispatch('GET','/live')[0]==200
    app.busy=True;app.compute_started=time.monotonic()-61
    assert app.dispatch('GET','/live')[0]==503

def test_gateway_live_detects_stuck_loop_but_not_dependency_unavailability():
    gateway=Gateway(N())
    assert gateway.dispatch('GET','/ready')[0]==503
    assert gateway.dispatch('GET','/live')[0]==200
    gateway.control_heartbeat=time.monotonic()-31
    assert gateway.dispatch('GET','/live')[0]==503

def test_drain_finishes_admitted_work_and_rejects_new_work():
    entered=threading.Event();release=threading.Event()
    class Blocking(Model):
        def predict(self,body): entered.set();assert release.wait(5);return super().predict(body)
    app=Inference(Blocking())
    server=serve(app,'127.0.0.1',0)
    loop=threading.Thread(target=server.serve_forever,daemon=True);loop.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        with ThreadPoolExecutor(2) as pool:
            request=pool.submit(fetch,url+'/infer',{})
            assert entered.wait(2)
            drain=pool.submit(shutdown_gracefully,server,app,5)
            for _ in range(100):
                if app.draining: break
                time.sleep(.01)
            assert fetch(url+'/ready')[0]==503
            assert fetch(url+'/infer',{})[0]==503
            assert not drain.done() and app.active_requests()==1
            release.set()
            assert request.result(timeout=3)[0]==200
            drain.result(timeout=3)
        assert app.active_requests()==0 and server.pending()==0
    finally:
        release.set();server.shutdown();server.server_close();loop.join(2)

def test_drain_waits_for_http_response_after_application_completes(monkeypatch):
    entered=threading.Event();release=threading.Event()
    original=Handler.end_headers
    def delayed_headers(handler):
        if handler.path=='/infer': entered.set();assert release.wait(5)
        return original(handler)
    monkeypatch.setattr(Handler,'end_headers',delayed_headers)
    app=Inference(Model());server=serve(app,'127.0.0.1',0)
    loop=threading.Thread(target=server.serve_forever,daemon=True);loop.start()
    try:
        with ThreadPoolExecutor(2) as pool:
            response=pool.submit(fetch,f'http://127.0.0.1:{server.server_port}/infer',{})
            assert entered.wait(2)
            assert app.active_requests()==0 and server.pending()==1
            drain=pool.submit(shutdown_gracefully,server,app,5)
            time.sleep(.05);assert not drain.done()
            release.set()
            assert response.result(timeout=3)[1]['predictions']==[1,2,3]
            drain.result(timeout=3)
    finally:
        release.set();server.shutdown();server.server_close();loop.join(2)

def test_no_reconcile_after_gateway_drain():
    class Adapter:
        def endpoints(self): raise AssertionError('Discovery during drain')
        def reconcile(self,*args): raise AssertionError('Action during drain')
    gateway=Gateway(Adapter());gateway.begin_drain();gateway.refresh()
    assert gateway.dispatch('GET','/ready')[0]==503

def test_control_loop_recovers_from_api_failure_without_policy_change(monkeypatch):
    from prototype import gateway as module
    attempts=[]
    class Adapter:
        def endpoints(self):
            attempts.append(1)
            if len(attempts)==1: raise OSError('API temporarily unavailable')
            return ['http://warm-one','http://warm-two']
        def reconcile(self,target,ready):
            assert target==2 and ready==2
            gateway.stop.set()
            return 'unchanged',False
    monkeypatch.setattr(module,'fetch',lambda *a,**kw:(200,dict(ready=True,queue=0,busy=False,cycle_ms=20.,variance_ms2=4.,vram_bytes=0)))
    gateway=Gateway(Adapter(),interval=.001)
    gateway.run_control()
    assert len(attempts)==2 and gateway.dispatch('GET','/ready')[0]==200
    assert 'outcome="failed"} 1.0' in gateway.metrics.export().decode()
    assert gateway.last_decision['desired_replicas']==2

def test_discovery_excludes_terminating_and_cold_pods_and_bounds_api_timeout():
    def pod(ip,ready=True,terminating=False):
        return N(metadata=N(deletion_timestamp='now' if terminating else None),status=N(pod_ip=ip,conditions=[N(type='Ready',status='True' if ready else 'False')]))
    class Core:
        def list_namespaced_pod(self,namespace,**kwargs):
            assert namespace=='jointsla-prototype' and kwargs['_request_timeout']==(2,3)
            return N(items=[pod('1'),pod('2',ready=False),pod('3',terminating=True)])
    assert KubernetesAdapter(N(),Core()).endpoints()==['http://1:8080']

def test_scale_conflict_is_not_blindly_retried_or_counted_as_applied():
    calls=[]
    class Apps:
        def read_namespaced_deployment_scale(self,*args,**kwargs):
            assert kwargs['_request_timeout']==(2,3)
            return N(spec=N(replicas=2),metadata=N(resource_version='old'))
        def patch_namespaced_deployment_scale(self,*args,**kwargs):
            calls.append(args);assert kwargs['_request_timeout']==(2,3)
            raise RuntimeError('409 conflict')
    with pytest.raises(RuntimeError,match='409'): KubernetesAdapter(Apps(),N()).reconcile(3)
    assert len(calls)==1 and calls[0][2]['metadata']['resourceVersion']=='old'

@pytest.mark.parametrize('name',['inference','gateway','prometheus','grafana'])
def test_manifests_have_resource_probe_and_security_guards(name):
    docs=[]
    for file in ['prototype.yaml','monitoring.yaml']:
        docs.extend(yaml.safe_load_all((ROOT/'prototype/kubernetes'/file).read_text(encoding='utf-8')))
    doc=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']==name)
    pod=doc['spec']['template']['spec'];container=pod['containers'][0]
    assert pod['securityContext']['runAsNonRoot']
    assert container['securityContext']['capabilities']['drop']==['ALL']
    assert not container['securityContext']['allowPrivilegeEscalation']
    assert container['securityContext']['readOnlyRootFilesystem']
    for key in ['startupProbe','readinessProbe','livenessProbe']:
        assert container[key]['httpGet']['port'] in (8080,8090,9090,3000)
    for scope in ['requests','limits']: assert {'cpu','memory'}<=container['resources'][scope].keys()
    if name=='gateway': assert doc['spec']['strategy']['type']=='Recreate'
    if name in ('inference','gateway'): assert pod['terminationGracePeriodSeconds']>60

def test_redeploy_preserves_controller_replica_ownership_and_immutable_images():
    docs=list(yaml.safe_load_all((ROOT/'prototype/kubernetes/prototype.yaml').read_text()))
    images={'inference':'jointsla-inference:123456789abcdef0','gateway':'jointsla-gateway:123456789abcdef0'}
    for replicas in (None,2,4):
        rendered=deployment_documents(copy.deepcopy(docs),images,replicas)
        inference=next(d for d in rendered if d['kind']=='Deployment' and d['metadata']['name']=='inference')
        assert inference['spec']['replicas']==(1 if replicas is None else replicas)
        assert inference['spec']['template']['spec']['containers'][0]['imagePullPolicy']=='Never'

def test_monitoring_has_bounded_persistent_storage_and_valid_alerts():
    docs=list(yaml.safe_load_all((ROOT/'prototype/kubernetes/monitoring.yaml').read_text()))
    assert {d['metadata']['name'] for d in docs if d['kind']=='PersistentVolumeClaim'}=={'grafana-data','prometheus-data'}
    config=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='prometheus-config')['data']
    assert len(yaml.safe_load(config['alerts.yml'])['groups'][0]['rules'])==4
    assert yaml.safe_load(config['prometheus.yml'])['rule_files']==['/etc/prometheus/alerts.yml']
    dashboard=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='grafana-dashboard')
    assert len(json.loads(dashboard['data']['jointsla.json'])['panels'])==28

def test_http_thread_saturation_returns_bounded_rejection():
    app=Inference(Model());server=serve(app,'127.0.0.1',0)
    server.slots=threading.BoundedSemaphore(1)
    server.slots.acquire()
    loop=threading.Thread(target=server.serve_forever,daemon=True);loop.start()
    try:
        assert fetch(f'http://127.0.0.1:{server.server_port}/infer',{})[0]==503
        assert fetch(f'http://127.0.0.1:{server.server_port}/live')[0]==200
        assert fetch(f'http://127.0.0.1:{server.server_port}/ready')[0]==200
        assert 'jointsla_inference_http_saturation_rejections_total 1.0' in app.metrics.export().decode()
    finally: server.slots.release();server.shutdown();server.server_close();loop.join(2)

def test_gateway_refuses_non_object_backend_response(monkeypatch):
    from prototype import gateway as module
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,size): return b'[1,2,3]'
    monkeypatch.setattr(module.request,'urlopen',lambda *args,**kw:Response())
    with pytest.raises(ValueError,match='JSON object'): fetch('http://backend/state')

def test_gateway_refuses_oversized_backend_response(monkeypatch):
    from prototype import gateway as module
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,size): return b'x'*size
    monkeypatch.setattr(module.request,'urlopen',lambda *args,**kw:Response())
    with pytest.raises(ValueError,match='too large'): fetch('http://backend/state')

def test_csv_validation_rejects_duplicate_and_false_sla_evidence(tmp_path):
    import csv
    from prototype.kubernetes.validate_runtime import validate_outcomes
    rows=[dict(request=0,status=200,latency_ms=50,deadline_ms=200,sla_failure='False',pretrained='True'),
          dict(request=1,status=503,latency_ms=1,deadline_ms=200,sla_failure='True',pretrained='False')]
    def write():
        with (tmp_path/'request_outcomes.csv').open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(offered=2,completed=1,sla_failure_rate=.5)
    write();assert validate_outcomes(tmp_path,summary)==2
    rows[1]['request']=0;write()
    with pytest.raises(AssertionError): validate_outcomes(tmp_path,summary)
    rows[1]['request']=1;rows[1]['sla_failure']='False';write()
    with pytest.raises(AssertionError): validate_outcomes(tmp_path,summary)

@pytest.mark.parametrize('bad_identity',['namespace','uid','pid'])
def test_failure_injection_refuses_unowned_container_or_node_init(monkeypatch,bad_identity):
    from prototype.kubernetes import validate_infrastructure as module
    pod={'metadata':{'namespace':'jointsla-prototype','uid':'owned','labels':{'app':'jointsla-gateway'}},
         'status':{'containerStatuses':[{'containerID':'containerd://abc'}]}}
    info={'info':{'pid':12},'status':{'labels':{'io.kubernetes.pod.uid':'owned','io.kubernetes.pod.namespace':'jointsla-prototype','io.kubernetes.container.name':'gateway'}}}
    if bad_identity=='namespace': pod['metadata']['namespace']='other'
    if bad_identity=='uid': info['status']['labels']['io.kubernetes.pod.uid']='other'
    if bad_identity=='pid': info['info']['pid']=1
    monkeypatch.setattr(module.subprocess,'check_output',lambda *a,**kw:json.dumps(info))
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**kw:pytest.fail('Must not signal this container'))
    with pytest.raises(ValueError): module.signal_gateway(pod,'KILL')
