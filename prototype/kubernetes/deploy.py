"""Idempotent deployment to the dedicated local kind cluster; no global context."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from urllib.request import urlopen
import yaml

ROOT=Path(__file__).resolve().parents[2]
NODE_IMAGE='kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed'
NS='jointsla-prototype'

def run(*args, capture=False, timeout=900, input=None):
    print('Running:', ' '.join(str(a) for a in args),flush=True)
    return subprocess.run(list(map(str,args)),cwd=ROOT,check=True,text=True,input=input,
                          stdout=subprocess.PIPE if capture else None,timeout=timeout).stdout

def kind_binary():
    binary=ROOT/'.cache/bin/kind.exe'
    if os.name=='nt':
        binary.parent.mkdir(parents=True,exist_ok=True)
        if not binary.exists():
            with urlopen('https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/kind-windows-amd64',timeout=60) as source:
                raw=source.read()
            if hashlib.sha256(raw).hexdigest()!='4b22adaa135368c5a465d56bbd8e520cbea87272a06ca00b6078e7b81515c9fc':
                raise RuntimeError('kind download checksum mismatch')
            binary.write_bytes(raw)
        if hashlib.sha256(binary.read_bytes()).hexdigest()!='4b22adaa135368c5a465d56bbd8e520cbea87272a06ca00b6078e7b81515c9fc':
            raise RuntimeError('Local kind checksum mismatch')
        return binary
    binary=shutil.which('kind')
    if not binary or 'v0.33.0' not in run(binary,'version',capture=True):
        raise RuntimeError('Install kind v0.33.0 on Linux; use an amd64 Docker daemon')
    return binary

def deployment_documents(objects, images, current_replicas=None):
    """Use immutable local image IDs; preserve the actuator-owned replica count."""
    for obj in objects:
        if obj.get('kind')=='Deployment':
            name=obj['metadata']['name']
            container=obj['spec']['template']['spec']['containers'][0]
            container['image']=images[name]
            container['imagePullPolicy']='Never' if name in ('gateway','inference') else 'IfNotPresent'
            if name=='inference' and current_replicas is not None:
                obj['spec']['replicas']=current_replicas
    return objects

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--skip-build',action='store_true',help='Reuse already built local application images')
    parser.add_argument('--validate',action='store_true',help='Also run controlled traffic and destructive recovery checks in this owned lab')
    parser.add_argument('--lab',choices=['prototype','validation'],default='prototype',help='Validation uses a separate fresh cluster and ports')
    args=parser.parse_args()
    os.environ['JOINTSLA_LAB']=args.lab
    from prototype.kubernetes.settings import CLUSTER,CACHE,OFFSET
    CACHE.mkdir(parents=True,exist_ok=True)
    info=json.loads(run('docker','info','--format','{{json .}}',capture=True))
    if info['OSType']!='linux' or info['Architecture'] not in ('x86_64','amd64'):
        raise RuntimeError('Requires Docker Linux containers on amd64')
    run('kubectl','version','--client')
    kind=kind_binary()
    clusters=run(kind,'get','clusters',capture=True).splitlines()
    if CLUSTER not in clusters:
        kind_config=yaml.safe_load((ROOT/'prototype/kubernetes/kind.yaml').read_text())
        for node in kind_config['nodes']:
            for port in node.get('extraPortMappings',[]): port['hostPort']+=OFFSET
        config_path=CACHE/'kind.yaml'
        config_path.write_text(yaml.safe_dump(kind_config))
        run(kind,'create','cluster','--name',CLUSTER,'--config',config_path,
            '--kubeconfig',CACHE/'config','--image',NODE_IMAGE,'--wait','120s')
    else:
        config=run(kind,'get','kubeconfig','--name',CLUSTER,capture=True)
        (CACHE/'config').write_text(config,encoding='utf-8')
    kubectl=['kubectl','--kubeconfig',CACHE/'config','--context','kind-'+CLUSTER]
    nodes=json.loads(run(*kubectl,'get','nodes','-o','json',capture=True))['items']
    if [n['metadata']['name'] for n in nodes]!=[CLUSTER+'-control-plane']:
        raise RuntimeError('Refusing an unexpected cluster topology')
    if not args.skip_build: run('docker','compose','-f','prototype/compose.yaml','build')
    source_images={'inference':'jointsla-prototype-inference:latest','gateway':'jointsla-prototype-gateway:latest',
                   'prometheus':'prom/prometheus@sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996',
                   'grafana':'grafana/grafana@sha256:6ac590e7cabc2fbe8d7b8fc1ce9c9f0582177b334e0df9c927ebd9670469440f'}
    images={};digests={};archive_tags=[]
    for name,source in source_images.items():
        if name in ('prometheus','grafana'): run('docker','pull',source)
        details=json.loads(run('docker','image','inspect',source,capture=True))[0]
        image_id=details['Id'];tag='jointsla-'+name+':'+image_id.split(':')[1][:16]
        run('docker','tag',source,tag)
        archive_tags.append(tag)
        images[name]=tag if name in ('gateway','inference') else source
        digests[name]=dict(image_id=image_id,source=source,repo_digests=details.get('RepoDigests',[]))
    run('docker','image','save','--platform','linux/amd64','--output',CACHE/'images-amd64.tar',*archive_tags)
    run(kind,'load','image-archive',CACHE/'images-amd64.tar','--name',CLUSTER)
    from prototype.kubernetes.render_monitoring import render
    render()
    objects=[]
    for name in ('prototype.yaml','local-services.yaml','monitoring.yaml'):
        objects.extend(yaml.safe_load_all((ROOT/'prototype/kubernetes'/name).read_text(encoding='utf-8')))
    query=subprocess.run(list(map(str,[*kubectl,'-n',NS,'get','deployment','inference','-o','json'])),capture_output=True,text=True)
    replicas=json.loads(query.stdout)['spec']['replicas'] if query.returncode==0 else None
    # On bootstrap absence is expected; other API failures must not reset live replicas.
    if query.returncode and 'NotFound' not in query.stderr:
        raise RuntimeError(query.stderr)
    objects=deployment_documents(objects,images,replicas)
    password_file=CACHE/'grafana-admin-password'
    if not password_file.exists(): password_file.write_text(secrets.token_urlsafe(32),encoding='utf-8')
    run(*kubectl,'apply','-f','-',input=yaml.safe_dump(objects[0]))
    secret={'apiVersion':'v1','kind':'Secret','metadata':{'name':'grafana-admin','namespace':NS},
            'type':'Opaque','stringData':{'password':password_file.read_text()}}
    run(*kubectl,'apply','-f','-',input=yaml.safe_dump(secret))
    rendered=yaml.safe_dump_all(objects,sort_keys=False)
    (CACHE/'deployed.yaml').write_text(rendered,encoding='utf-8')
    run(*kubectl,'apply','-f','-',input=rendered)
    # Recreate monitoring only when provisioning changes (ConfigMap mounts alone are not reloads).
    config_hash=hashlib.sha256(yaml.safe_dump_all([o for o in objects if o['kind']=='ConfigMap'],sort_keys=False).encode()).hexdigest()
    for name in ('prometheus','grafana'):
        patch={'spec':{'template':{'metadata':{'annotations':{'jointsla/config-hash':config_hash}}}}}
        run(*kubectl,'-n',NS,'patch','deployment',name,'--type=merge','-p',json.dumps(patch))
    for name in images: run(*kubectl,'-n',NS,'rollout','status','deployment/'+name,'--timeout=300s',timeout=330)
    (CACHE/'image-lock.json').write_text(json.dumps(digests,indent=2),encoding='utf-8')
    from prototype.kubernetes.validate_infrastructure import smoke
    smoke()
    if args.validate:
        run(sys.executable,'-m','prototype.kubernetes.validate_runtime')
        run(sys.executable,'-m','prototype.kubernetes.validate_infrastructure')
    print(f'Deployment ready: gateway {8091+OFFSET}, Prometheus {9091+OFFSET}, Grafana {3001+OFFSET} (host loopback).',flush=True)

if __name__=='__main__': main()
