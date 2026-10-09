"""Queue admission, real HTTP accounting, readiness and scoped actuation checks."""
import json
from types import SimpleNamespace as N
import threading
import time
from urllib.request import urlopen,Request
import pytest
from prototype.controller import plan,route
from prototype.inference import Inference
from prototype.adapters import KubernetesAdapter
from prototype.gateway import Gateway
from prototype.http import serve

def state(queue=0,busy=False,ready=True):
    return dict(queue=queue,busy=busy,ready=ready,cycle_ms=20.,variance_ms2=4.,vram_bytes=0)

def test_warm_floor_and_overload_are_bounded():
    assert plan([state()],0).desired_replicas==2
    assert plan([state(100)],200).desired_replicas==4
    assert plan([],0).desired_replicas==1

def test_routing_excludes_unready_and_accounts_queue():
    assert route([state(ready=False),state(10),state()],200)==2
    assert route([state(ready=False)],200) is None

def test_queue_admission_failure_accounting_and_drain():
    entered=threading.Event();release=threading.Event()
    class Model:
        load_seconds=.1
        def vram(self): return 0
        def predict(self,body): entered.set();release.wait(3);return {'predictions':[]}
    app=Inference(Model(),queue_limit=0)
    result=[]
    thread=threading.Thread(target=lambda:result.append(app.dispatch('POST','/infer',{})))
    thread.start();assert entered.wait(2)
    assert app.dispatch('POST','/infer',{})[0]==503
    release.set();thread.join(3)
    assert result[0][0]==200
    text=app.metrics.export().decode()
    assert 'jointsla_inference_requests_total{tier="Gold"} 2.0' in text
    assert 'jointsla_inference_sla_failures_total{tier="Gold"} 1.0' in text
    app.draining=True
    assert app.dispatch('GET','/ready')[0]==503
    assert app.dispatch('POST','/infer',{})[0]==503

def test_failed_inference_releases_slot():
    class Model:
        load_seconds=.1
        def vram(self): return 0
        def predict(self,body): raise RuntimeError('Model failed')
    app=Inference(Model(),0)
    for _ in range(2):
        with pytest.raises(RuntimeError): app.dispatch('POST','/infer',{})
    assert app.active_requests()==0
    assert 'outcome="failed",tier="Gold"} 2.0' in app.metrics.export().decode()

def test_kubernetes_scale_is_scoped_idempotent_and_bounded():
    calls=[]
    class Apps:
        def read_namespaced_deployment_scale(self,*args,**kwargs):
            return N(spec=N(replicas=2),metadata=N(resource_version='7'))
        def patch_namespaced_deployment_scale(self,*args,**kwargs): calls.append(args)
    adapter=KubernetesAdapter(Apps(),N())
    assert adapter.reconcile(2)==('unchanged',False)
    assert adapter.reconcile(1,ready=0)==('unchanged',False)
    assert adapter.reconcile(3)==('applied',True)
    assert calls[0][:2]==('inference','jointsla-prototype')
    assert calls[0][2]['metadata']['resourceVersion']=='7'
    with pytest.raises(ValueError): adapter.reconcile(5)

def test_gateway_real_http_path_and_failure_denominator():
    class Model:
        load_seconds=.1
        def vram(self): return 0
        def predict(self,body): return {'pretrained':False,'predictions':[]}
    server=serve(Inference(Model()),'127.0.0.1',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    class Adapter:
        def endpoints(self): return [f'http://127.0.0.1:{server.server_port}']
        def reconcile(self,target,ready=None): return 'observed',False
    gateway=Gateway(Adapter())
    try:
        gateway.refresh()
        code,result=gateway.dispatch('POST','/infer',{'tier':'Gold','deadline_ms':200})
        assert code==200 and result['gateway_latency_ms']>0
        assert gateway.states[0]['queue']==0
        gateway.last_refresh=0
        assert gateway.dispatch('POST','/infer',{})[0]==503
        assert 'jointsla_gateway_requests_total{tier="Gold"} 2.0' in gateway.metrics.export().decode()
    finally: server.shutdown();server.server_close()

@pytest.mark.parametrize('mode',['transport','draining'])
def test_failure_withdraws_replica_without_retrying_work(monkeypatch,mode):
    from prototype import gateway as module
    calls=[]
    def fetch(url,body=None,timeout=3):
        calls.append(url)
        if url=='http://bad/infer':
            if mode=='transport': raise OSError('Dead pod')
            return 503,{'error':'Replica draining'}
        return 200,{'predictions':[]}
    monkeypatch.setattr(module,'fetch',fetch)
    gateway=Gateway(N())
    gateway.endpoints=['http://bad','http://healthy']
    gateway.states=[state(),state()]
    gateway.last_refresh=time.monotonic()
    assert gateway.dispatch('POST','/infer',{})[0] in (502,503)
    assert calls==['http://bad/infer']
    assert gateway.states[0]['ready'] is False
    assert gateway.dispatch('POST','/infer',{})[0]==200
    assert calls==['http://bad/infer','http://healthy/infer']

def test_overload_rejection_keeps_healthy_replica(monkeypatch):
    from prototype import gateway as module
    monkeypatch.setattr(module,'fetch',lambda *a,**kw:(503,{'error':'Queue full'}))
    gateway=Gateway(N());gateway.endpoints=['http://busy'];gateway.states=[state()]
    gateway.last_refresh=time.monotonic()
    assert gateway.dispatch('POST','/infer',{})[0]==503
    assert gateway.states[0]['ready'] is True
