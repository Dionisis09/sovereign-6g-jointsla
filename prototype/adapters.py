"""Endpoint discovery and a namespace/deployment-scoped Kubernetes actuator."""
import os
import socket

class ObserveAdapter:
    def endpoints(self):
        explicit=os.getenv('INFERENCE_ENDPOINTS')
        if explicit: return sorted(set(explicit.split(',')))
        host=os.getenv('INFERENCE_HOST','inference')
        return sorted({f'http://{entry[4][0]}:8080' for entry in socket.getaddrinfo(host,8080,type=socket.SOCK_STREAM)})

    def reconcile(self, desired, ready=None):
        return 'observed',False

class KubernetesAdapter:
    """In-cluster client only; fixed deployment, ready non-terminating pods."""
    def __init__(self, apps=None, core=None, namespace='jointsla-prototype', deployment='inference'):
        if apps is None:
            from kubernetes import client,config
            config.load_incluster_config()
            configuration=client.Configuration.get_default_copy()
            configuration.retries=0  # bounded decision steps; outer control loop retries
            api=client.ApiClient(configuration)
            apps,core=client.AppsV1Api(api),client.CoreV1Api(api)
        self.apps,self.core,self.namespace,self.deployment=apps,core,namespace,deployment

    def endpoints(self):
        pods=self.core.list_namespaced_pod(self.namespace,label_selector='app=jointsla-inference',_request_timeout=(2,3)).items
        return sorted(f'http://{p.status.pod_ip}:8080' for p in pods if p.status.pod_ip and not p.metadata.deletion_timestamp
                      and any(c.type=='Ready' and c.status=='True' for c in (p.status.conditions or [])))

    def reconcile(self, desired, ready=None):
        if type(desired) is not int or not 1<=desired<=4: raise ValueError('Replica bounds are 1–4')
        current=self.apps.read_namespaced_deployment_scale(self.deployment,self.namespace,_request_timeout=(2,3))
        if ready==0 and current.spec.replicas>0: return 'unchanged',False
        if current.spec.replicas==desired: return 'unchanged',False
        self.apps.patch_namespaced_deployment_scale(self.deployment,self.namespace,
            {'metadata':{'resourceVersion':current.metadata.resource_version},'spec':{'replicas':desired}},_request_timeout=(2,3))
        return 'applied',True
