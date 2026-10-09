"""Provision a small namespace-local monitoring stack, reusing dashboard panels."""
import json
from pathlib import Path
import yaml
from prototype.kubernetes.final_dashboard import build_dashboard

ROOT=Path(__file__).resolve().parents[2]
NS='jointsla-prototype'

def render():
    directory=ROOT/'prototype/monitoring'
    prometheus={'global':{'scrape_interval':'2s','evaluation_interval':'5s'},'rule_files':['/etc/prometheus/alerts.yml'],'scrape_configs':[
        {'job_name':'gateway','static_configs':[{'targets':['gateway:8090']}]},
        {'job_name':'inference','dns_sd_configs':[{'names':['inference.jointsla-prototype.svc.cluster.local'],
                                                 'type':'A','port':8080,'refresh_interval':'2s'}]}]}
    dashboard=build_dashboard()
    (Path(__file__).parent/'final-dashboard.json').write_text(json.dumps(dashboard,indent=2),encoding='utf-8')
    objects=[]
    def config(name,data):
        objects.append(dict(apiVersion='v1',kind='ConfigMap',metadata=dict(name=name,namespace=NS),data=data))
    alerts={'groups':[{'name':'jointsla.infrastructure','rules':[
        {'alert':'JointSLAGatewayUnavailable','expr':'up{job="gateway"} == 0','for':'15s','labels':{'severity':'critical'},'annotations':{'summary':'Gateway metrics unavailable'}},
        {'alert':'JointSLATelemetryStale','expr':'time() - jointsla_gateway_snapshot_timestamp_seconds > 10','for':'15s','labels':{'severity':'warning'},'annotations':{'summary':'Controller telemetry is stale'}},
        {'alert':'JointSLANoReadyInference','expr':'jointsla_gateway_ready_replicas < 1','for':'10s','labels':{'severity':'critical'},'annotations':{'summary':'No warm inference endpoint'}},
        {'alert':'JointSLAReconciliationFailure','expr':'increase(jointsla_gateway_actions_total{outcome="failed"}[1m]) > 0','for':'10s','labels':{'severity':'warning'},'annotations':{'summary':'Kubernetes reconciliation failed'}}]}]}
    config('prometheus-config',{'prometheus.yml':yaml.safe_dump(prometheus,sort_keys=False),'alerts.yml':yaml.safe_dump(alerts,sort_keys=False)})
    config('grafana-datasource',{'prometheus.yaml':(directory/'provisioning/datasources/prometheus.yaml').read_text()})
    config('grafana-provider',{'default.yaml':(directory/'provisioning/dashboards/default.yaml').read_text()})
    config('grafana-dashboard',{'jointsla.json':json.dumps(dashboard)})
    for name,size in [('prometheus','2Gi'),('grafana','1Gi')]:
        objects.append(dict(apiVersion='v1',kind='PersistentVolumeClaim',metadata=dict(name=name+'-data',namespace=NS),
            spec={'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':size}}}))
    for name,image,port,nodeport,volumes in [
        ('prometheus','prom/prometheus:v3.5.0',9090,30091,[('prometheus-config','/etc/prometheus')]),
        ('grafana','grafana/grafana:12.1.0',3000,30092,[('grafana-datasource','/etc/grafana/provisioning/datasources'),
            ('grafana-provider','/etc/grafana/provisioning/dashboards'),('grafana-dashboard','/var/lib/grafana/dashboards')])]:
        container=dict(name=name,image=image,imagePullPolicy='IfNotPresent',ports=[{'containerPort':port}],
            volumeMounts=[dict(name=n,mountPath=p,readOnly=True) for n,p in volumes],
            resources={'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'500m','memory':'512Mi'}},
            readinessProbe={'httpGet':{'path':'/-/ready' if name=='prometheus' else '/api/health','port':port},'periodSeconds':2})
        if name=='grafana': container['env']=[{'name':'GF_AUTH_ANONYMOUS_ENABLED','value':'true'},
                                             {'name':'GF_AUTH_ANONYMOUS_ORG_ROLE','value':'Viewer'},
                                             {'name':'GF_SECURITY_ADMIN_PASSWORD','valueFrom':{'secretKeyRef':{'name':'grafana-admin','key':'password'}}}]
        if name=='prometheus': container['args']=['--config.file=/etc/prometheus/prometheus.yml','--storage.tsdb.path=/prometheus','--storage.tsdb.retention.time=7d','--storage.tsdb.retention.size=1500MB']
        live='/-/healthy' if name=='prometheus' else '/api/health'
        container['livenessProbe']={'httpGet':{'path':live,'port':port},'periodSeconds':10,'timeoutSeconds':2,'failureThreshold':3}
        container['startupProbe']={'httpGet':{'path':live,'port':port},'periodSeconds':2,'failureThreshold':60}
        container['readinessProbe'].update(timeoutSeconds=2,failureThreshold=1)
        container['securityContext']={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
        container['volumeMounts'] += [{'name':'data','mountPath':'/prometheus' if name=='prometheus' else '/var/lib/grafana'},{'name':'tmp','mountPath':'/tmp'}]
        uid=65534 if name=='prometheus' else 472
        objects.append(dict(apiVersion='apps/v1',kind='Deployment',metadata=dict(name=name,namespace=NS),
            spec=dict(replicas=1,strategy={'type':'Recreate'},selector={'matchLabels':{'app':name}},template={'metadata':{'labels':{'app':name}},
                'spec':{'automountServiceAccountToken':False,'containers':[container],
                        'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'runAsGroup':uid,'fsGroup':uid,'seccompProfile':{'type':'RuntimeDefault'}},
                        'volumes':[{'name':n,'configMap':{'name':n}} for n,p in volumes]+[{'name':'data','persistentVolumeClaim':{'claimName':name+'-data'}},{'name':'tmp','emptyDir':{'sizeLimit':'128Mi'}}]}})))
        objects.append(dict(apiVersion='v1',kind='Service',metadata=dict(name=name,namespace=NS),
            spec=dict(type='NodePort',selector={'app':name},ports=[dict(port=port,targetPort=port,nodePort=nodeport)])))
    (Path(__file__).parent/'monitoring.yaml').write_text(yaml.safe_dump_all(objects,sort_keys=False),encoding='utf-8')

if __name__=='__main__': render()
