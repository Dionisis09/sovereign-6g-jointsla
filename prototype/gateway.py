"""Live telemetry -> JointSLA-derived decisions -> real HTTP routing/optional K8s scaling."""
import argparse
from collections import deque
from dataclasses import asdict
import json
import os
import threading
import time
from urllib import request,error
from prototype.adapters import ObserveAdapter,KubernetesAdapter
from prototype.controller import plan,route
from prototype.http import run_server,request_parameters
from prototype.telemetry import Metrics

def fetch(url,body=None,timeout=3):
    req=request.Request(url,data=json.dumps(body).encode() if body is not None else None,
                        headers={'Content-Type':'application/json'})
    def read_json(response):
        raw=response.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('Backend response too large')
        payload=json.loads(raw)
        if not isinstance(payload,dict): raise ValueError('Backend must return a JSON object')
        return payload
    try:
        with request.urlopen(req,timeout=timeout) as response: return response.status,read_json(response)
    except error.HTTPError as failure:
        try:
            with failure: return failure.code,read_json(failure)
        except (ValueError,OSError): pass
        return failure.code,{'error':f'Backend HTTP {failure.code}'}

class Gateway:
    def __init__(self, adapter, interval=2., cooldown=30.):
        self.adapter,self.interval,self.cooldown=adapter,interval,cooldown
        self.metrics=Metrics('gateway')
        self.lock,self.refresh_lock=threading.Lock(),threading.Lock()
        self.endpoints,self.states=[],[]
        self.arrivals=deque()
        self.last_action=float('-inf')
        self.last_refresh=0.
        self.last_decision={}
        self.stop=threading.Event()
        self.draining=False
        self.active=0
        self.control_heartbeat=time.monotonic()

    def refresh(self):
        with self.refresh_lock:
            if self.stop.is_set(): return
            started=time.perf_counter()
            now=time.monotonic()
            endpoints=[];states=[]
            for endpoint in self.adapter.endpoints():
                try:
                    code,state=fetch(endpoint+'/state',timeout=.5)
                    if code==200 and state.get('ready'):
                        endpoints.append(endpoint);states.append(state)
                except (OSError,ValueError): continue
            with self.lock:
                while self.arrivals and self.arrivals[0]<now-10: self.arrivals.popleft()
                rate=len(self.arrivals)/10
            decision=plan(states,rate,float(os.getenv('CONTROL_DEADLINE_MS','200')),
                          float(os.getenv('COLD_START_SECONDS','10')))
            with self.lock:
                self.endpoints,self.states=endpoints,states
                self.last_refresh=now
                self.last_decision=asdict(decision)
                self.last_decision.update(observed_rate_rps=rate,snapshot_unix_s=time.time())
            self.metrics.ready.set(0 if self.draining else decision.ready_replicas)
            self.metrics.desired.set(decision.desired_replicas)
            self.metrics.queue.set(decision.queue)
            self.metrics.vram.set(sum(s['vram_bytes'] for s in states))
            self.metrics.snapshot_time.set(time.time())
            if not self.stop.is_set() and now-self.last_action>=self.cooldown:
                outcome,changed=self.adapter.reconcile(decision.desired_replicas,decision.ready_replicas)
                if outcome!='unchanged': self.metrics.actions.labels(outcome).inc()
                if changed: self.last_action=now
                if outcome!='unchanged':
                    print(json.dumps(dict(event='reconciliation',unix_s=time.time(),backend=type(self.adapter).__name__,
                                          outcome=outcome,**asdict(decision),observed_rate_rps=rate)),flush=True)
            self.metrics.decision_seconds.set(time.perf_counter()-started)

    def run_control(self):
        while not self.stop.is_set():
            try: self.refresh()
            except Exception as failure:
                self.metrics.actions.labels('failed').inc()
                print(json.dumps({'control_error':str(failure)}),flush=True)
            finally:
                self.control_heartbeat=time.monotonic()
            self.stop.wait(self.interval)

    def dispatch(self, method,path,body=None):
        if method=='GET' and path=='/metrics': return 200,self.metrics.export()
        if method=='GET' and path=='/live':
            healthy=self.draining or time.monotonic()-self.control_heartbeat<max(30,3*self.interval)
            return (200 if healthy else 503),{'healthy':healthy}
        if method=='GET' and path=='/state':
            with self.lock: return 200,dict(self.last_decision,endpoints=[e for e,s in zip(self.endpoints,self.states) if s['ready']],backend=type(self.adapter).__name__)
        if method=='GET' and path=='/ready':
            with self.lock: ready=not self.draining and any(s['ready'] for s in self.states) and time.monotonic()-self.last_refresh<max(5,3*self.interval)
            return (200 if ready else 503),{'ready':ready}
        if method!='POST' or path!='/infer': return 404,{'error':'Unknown endpoint'}
        tier,deadline=request_parameters(body)
        start=time.perf_counter()
        self.metrics.offered.labels(tier).inc()
        with self.lock:
            self.arrivals.append(time.monotonic())
            states=[dict(s) for s in self.states]
            endpoints=list(self.endpoints)
            generation=self.last_refresh
            stale=self.draining or time.monotonic()-self.last_refresh>max(5,3*self.interval)
            selected=None if stale else route(states,deadline)
            if selected is not None:
                self.states[selected]['queue']+=1
                self.active+=1
        if selected is None:
            self.metrics.finish(tier,time.perf_counter()-start,deadline,'rejected')
            return 503,{'error':'No fresh ready replica'}
        try:
            code,result=fetch(endpoints[selected]+'/infer',body,timeout=60)
            elapsed=time.perf_counter()-start
            self.metrics.finish(tier,elapsed,deadline,'completed' if code==200 else 'rejected' if code==503 else 'failed')
            if code in (502,504) or code==503 and result.get('error')=='Replica draining':
                self.withdraw(endpoints[selected])
            return code,dict(result,gateway_latency_ms=elapsed*1000,gateway_sla_breach=code!=200 or elapsed*1000>deadline,
                             routed_to=endpoints[selected])
        except (OSError,ValueError):
            self.withdraw(endpoints[selected])
            self.metrics.finish(tier,time.perf_counter()-start,deadline,'failed')
            return 502,{'error':'Replica unavailable; request not retried to avoid duplicate execution'}
        finally:
            with self.lock:
                self.active-=1
                if generation==self.last_refresh: self.states[selected]['queue']=max(0,self.states[selected]['queue']-1)

    def active_requests(self):
        with self.lock: return self.active

    def begin_drain(self):
        with self.lock:
            self.draining=True
            self.stop.set()
            self.metrics.ready.set(0)
        with self.refresh_lock: pass  # finish an already bounded reconciliation

    def withdraw(self,endpoint):
        """Quarantine unavailable endpoint for subsequent requests; never replay work."""
        with self.lock:
            for address,state in zip(self.endpoints,self.states):
                if address==endpoint: state['ready']=False
            ready=sum(s['ready'] for s in self.states)
            self.last_decision['ready_replicas']=ready
            self.metrics.ready.set(ready)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8090')))
    parser.add_argument('--host',default=os.getenv('HOST','127.0.0.1'))
    args=parser.parse_args()
    adapter=KubernetesAdapter() if os.getenv('BACKEND','observe')=='kubernetes' else ObserveAdapter()
    gateway=Gateway(adapter)
    if isinstance(adapter,KubernetesAdapter):
        from prototype.kubernetes.observability import KubernetesSnapshotCollector
        collector=KubernetesSnapshotCollector(adapter)
        gateway.metrics.registry.register(collector)
        threading.Thread(target=collector.run,args=(gateway.stop,),daemon=True).start()
    thread=threading.Thread(target=gateway.run_control,daemon=True);thread.start()
    try: run_server(gateway,args.host,args.port)
    finally:
        gateway.stop.set()
        thread.join(timeout=10)

if __name__=='__main__': main()
