"""Build benchmark-only images and install native metrics-server in the owned lab."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.request import urlopen
import yaml

ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'.cache/kubernetes-validation'
KUBE=['kubectl','--kubeconfig',str(CACHE/'config'),'--context','kind-jointsla-validation']
NS='jointsla-prototype'


def command(*args,input=None):
    return subprocess.check_output(list(map(str,args)),cwd=ROOT,input=input,text=True,timeout=600)


def setup():
    nodes=json.loads(command(*KUBE,'get','nodes','-o','json'))['items']
    assert [n['metadata']['name'] for n in nodes]==['jointsla-validation-control-plane']
    primary=json.loads((ROOT/'.cache/kubernetes/image-lock.json').read_text(encoding='utf-8'))
    bases={name:'jointsla-'+name+':'+primary[name]['image_id'].split(':')[1][:16] for name in ('gateway','inference')}
    images={};archive=[]
    for name in ('gateway','inference'):
        print('Building benchmark '+name,flush=True)
        command('docker','build','--target',name,'-f','prototype/benchmark/Dockerfile',
                '--build-arg','GATEWAY_IMAGE='+bases['gateway'],'--build-arg','INFERENCE_IMAGE='+bases['inference'],
                '-t','jointsla-benchmark-'+name+':build','.')
        info=json.loads(command('docker','image','inspect','jointsla-benchmark-'+name+':build'))[0]
        tag='jointsla-benchmark-'+name+':'+info['Id'].split(':')[1][:16]
        command('docker','tag','jointsla-benchmark-'+name+':build',tag)
        images[name]=dict(tag=tag,id=info['Id']);archive.append(tag)
    vendor_url='https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml'
    with urlopen(vendor_url,timeout=60) as response: vendor=response.read()
    docs=list(yaml.safe_load_all(vendor))
    deployment=next(d for d in docs if d['kind']=='Deployment')
    container=deployment['spec']['template']['spec']['containers'][0]
    source=container['image'];command('docker','pull',source)
    details=json.loads(command('docker','image','inspect',source))[0]
    digest=next(d for d in details['RepoDigests'] if 'metrics-server' in d)
    container['image']=digest
    container['args'].append('--kubelet-insecure-tls')  # owned kind lab self-signed kubelets only
    container['resources']['limits']={'cpu':'500m','memory':'512Mi'}
    command('docker','image','save','--platform','linux/amd64','-o',CACHE/'benchmark-images.tar',*archive)
    command(ROOT/'.cache/bin/kind.exe','load','image-archive',CACHE/'benchmark-images.tar','--name','jointsla-validation')
    command(*KUBE,'apply','-f','-',input=yaml.safe_dump_all(docs,sort_keys=False))
    command(*KUBE,'-n','kube-system','rollout','status','deployment/metrics-server','--timeout=180s')
    for name in ('gateway','inference'):
        spec=json.loads(command(*KUBE,'-n',NS,'get','deployment',name,'-o','json'))
        podspec=spec['spec']['template']['spec'];c=podspec['containers'][0]
        c['image']=images[name]['tag'];c['imagePullPolicy']='Never'
        c['env']=[e for e in c.get('env',[]) if e['name'] not in ('BENCHMARK_POLICY','POD_NAME','POD_UID')]
        c['env'] += [{'name':'POD_NAME','valueFrom':{'fieldRef':{'fieldPath':'metadata.name'}}},
                     {'name':'POD_UID','valueFrom':{'fieldRef':{'fieldPath':'metadata.uid'}}}]
        if name=='gateway': c['env'].append({'name':'BENCHMARK_POLICY','value':'joint'})
        spec.pop('status',None)
        for field in ('managedFields','resourceVersion','uid','creationTimestamp','generation'):
            spec['metadata'].pop(field,None)
        command(*KUBE,'-n',NS,'apply','-f','-',input=json.dumps(spec))
    role=json.loads(command(*KUBE,'-n',NS,'get','role','jointsla-controller','-o','json'))
    role['rules']=[r for r in role['rules'] if r['apiGroups']!=['metrics.k8s.io']]
    role['rules'].append({'apiGroups':['metrics.k8s.io'],'resources':['pods'],'verbs':['get','list']})
    command(*KUBE,'-n',NS,'replace','-f','-',input=json.dumps(role))
    for name in ('gateway','inference'):
        command(*KUBE,'-n',NS,'rollout','status','deployment/'+name,'--timeout=180s')
    record=dict(lab='kind-jointsla-validation',images=images,base_images=bases,
                metrics_server=dict(version='v0.9.0',image=digest,vendor_url=vendor_url,
                    vendor_manifest_sha256=hashlib.sha256(vendor).hexdigest(),kind_kubelet_insecure_tls=True))
    (CACHE/'benchmark-image-lock.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    (CACHE/'metrics-server.vendor.yaml').write_bytes(vendor)
    (CACHE/'metrics-server.deployed.yaml').write_text(yaml.safe_dump_all(docs,sort_keys=False),encoding='utf-8')
    print(json.dumps(record,indent=2),flush=True)


if __name__=='__main__': setup()
