"""Benchmark-only policy hooks. JointSLA functions are imported unchanged."""
from collections import deque
from datetime import datetime, timezone
import json
import os
import time
from prototype.adapters import KubernetesAdapter
from prototype.controller import Decision, plan, route
from joint_routing.router import choose

MODES=('static','reactive','hpa','joint','joint_sq','reactive_joint')


class Adapter(KubernetesAdapter):
    def reconcile(self,desired,ready=None):
        if os.getenv('BENCHMARK_POLICY','joint') in ('static','hpa'):
            return 'unchanged',False
        return super().reconcile(desired,ready)


class Policy:
    def __init__(self,adapter,mode=None):
        self.adapter=adapter
        self.mode=mode or os.getenv('BENCHMARK_POLICY','joint')
        if self.mode not in MODES: raise ValueError('Unknown benchmark policy')
        self.rr=0
        self.history=deque()
        self.observation={}

    def cpu(self,states):
        from kubernetes import client
        from kubernetes.utils.quantity import parse_quantity
        names={s.get('pod_name') for s in states if s['ready']}
        api=client.CustomObjectsApi(self.adapter.apps.api_client)
        data=api.list_namespaced_custom_object('metrics.k8s.io','v1beta1',self.adapter.namespace,'pods',_request_timeout=(2,3))
        values=[];details=[]
        for item in data['items']:
            if item['metadata']['name'] not in names: continue
            stamp=datetime.fromisoformat(item['timestamp'].replace('Z','+00:00')).timestamp()
            age=time.time()-stamp
            if not 0<=age<=30: continue
            usage=sum(float(parse_quantity(c['usage']['cpu'])) for c in item['containers'])
            values.append(usage/.5)  # identical 500m inference CPU request
            details.append(dict(pod=item['metadata']['name'],cpu_cores=usage,timestamp=item['timestamp'],window=item['window']))
        return (sum(values)/len(values) if len(values)==len(names) and names else None),details

    def plan(self,states,rate,deadline=200.,cold=10.):
        now=time.monotonic()
        current=self.adapter.apps.read_namespaced_deployment_scale(self.adapter.deployment,self.adapter.namespace,_request_timeout=(2,3)).spec.replicas
        cpu=None;details=[];failure=None
        try: cpu,details=self.cpu(states)
        except Exception as error: failure=str(error)
        while self.history and self.history[0][0]<now-10: self.history.popleft()
        if cpu is not None: self.history.append((now,cpu))
        smoothed=sum(v for _,v in self.history)/len(self.history) if self.history else None
        self.observation=dict(cpu_fraction_of_request=cpu,trailing_cpu_fraction=smoothed,resource_metrics=details,cpu_error=failure)
        ready=sum(s['ready'] for s in states)
        queue=sum(s['queue']+int(s['busy']) for s in states)
        if self.mode in ('joint','joint_sq'):
            decision=plan(states,rate,deadline,cold)
        elif self.mode in ('reactive','reactive_joint'):
            target=current
            if cpu is not None and smoothed is not None:
                if smoothed>.8: target=min(4,current+1)
                elif smoothed<.2: target=max(2,current-1)
            decision=Decision(target,ready,queue,'CPU threshold 80/20; missing/stale CPU holds target')
        else:
            decision=Decision(2 if self.mode=='static' else current,ready,queue,'Fixed replicas' if self.mode=='static' else 'Native HPA owns scaling')
        print(json.dumps(dict(event='benchmark_decision',unix_s=time.time(),policy=self.mode,target=decision.desired_replicas,
                              ready=ready,queue=queue,**self.observation)),flush=True)
        return decision

    def route(self,states,deadline):
        if self.mode in ('joint','reactive_joint'): return route(states,deadline)
        candidates=[dict(id=i,queue_length=s['queue'],busy=s['busy']) for i,s in enumerate(states) if s['ready']]
        policy='sla_rr' if self.mode=='static' else 'sla_shortest_queue'
        selected=choose(candidates,deadline,policy,self.rr)
        if selected is not None: self.rr+=1
        return selected
