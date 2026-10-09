"""Verify live infrastructure and preserve a small local QA record."""
import csv
import hashlib
import json
from pathlib import Path
import time
from urllib.request import urlopen
from prototype.gateway import fetch

ROOT=Path(__file__).resolve().parents[1]

def verify():
    state=fetch('http://127.0.0.1:8090/state')[1]
    assert state['ready_replicas']==2,state
    code,prediction=fetch('http://127.0.0.1:8090/infer',dict(tier='Gold',deadline_ms=200,seed=1),timeout=60)
    assert code==200 and prediction['pretrained'] and len(prediction['predictions'])==3
    targets=json.load(urlopen('http://127.0.0.1:9090/api/v1/targets'))['data']['activeTargets']
    assert len(targets)==3 and all(t['health']=='up' for t in targets),targets
    dashboard=json.load(urlopen('http://127.0.0.1:3000/api/dashboards/uid/jointsla-runtime'))['dashboard']
    assert len(dashboard['panels'])==8
    batches={}
    for folder in ['smoke-two-replicas','burst-three-replicas']:
        base=ROOT/'prototype'/'.cache'/folder
        rows=list(csv.DictReader((base/'request_outcomes.csv').open(encoding='utf-8')))
        summary=json.loads((base/'summary.json').read_text())
        assert len(rows)==summary['offered'] and len({row['request'] for row in rows})==len(rows)
        assert sum(row['status']=='200' for row in rows)==summary['completed']
        assert all(row['pretrained']=='True' for row in rows if row['status']=='200')
        batches[folder]=dict(summary,observed_routed_replicas=len({row['routed_to'] for row in rows if row['routed_to']}))
    frozen=json.loads((ROOT/'results/jointsla_v2_heldout/freeze_manifest.json').read_text())
    assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected for path,expected in frozen['source_hashes'].items())
    result=dict(real_pretrained_inference=True,docker_ready_replicas=2,prometheus_targets_up=3,grafana_panels=8,
                frozen_sources_unchanged=True,benchmarks=batches,kubernetes_cluster_validated=False,
                compose_scaling='manual; controller observe mode',paper_results_updated=False)
    (ROOT/'prototype/.cache/verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

if __name__=='__main__': print(json.dumps(verify(),indent=2))
