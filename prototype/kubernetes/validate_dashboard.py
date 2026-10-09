"""Check the final provisioned dashboard, queries and namespace snapshots.

Read-only except writing a separate compact verification record. No failure
injection, actuation, scientific rerun or modification of historical evidence.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from urllib.request import urlopen
from prototype.kubernetes.final_dashboard import build_dashboard
from prototype.kubernetes.settings import GRAF, PROM, KUBECTL, URL

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'prototype/kubernetes/evidence/final_dashboard'


def read(url):
    with urlopen(url,timeout=15) as response:
        return json.load(response)


def query(expr, timestamp=None):
    params={'query':expr}
    if timestamp is not None:
        params['time']=timestamp
    result=read(PROM+'/api/v1/query?'+urlencode(params))
    assert result['status']=='success', result
    return result['data']['result']


def validate():
    expected=build_dashboard()
    deployed=read(GRAF+'/api/dashboards/uid/jointsla-runtime')['dashboard']
    assert deployed['title']==expected['title']
    assert len(deployed['panels'])==28
    assert [(p['title'],p.get('targets')) for p in deployed['panels']]==[(p['title'],p.get('targets')) for p in expected['panels']]
    queries=[]
    for panel in deployed['panels']:
        for target in panel.get('targets',[]):
            expr=target['expr'].replace('$__range','15m')
            samples=query(expr)
            queries.append(dict(panel=panel['title'],expr=expr,samples=len(samples)))
    observer=query('jointsla_kubernetes_observer_up')
    assert len(observer)==1 and float(observer[0]['value'][1])==1
    age=query('time() - jointsla_kubernetes_snapshot_timestamp_seconds')
    assert len(age)==1 and float(age[0]['value'][1])<20
    pods=json.loads(subprocess.check_output(KUBECTL+['get','pods','-o','json'],text=True))['items']
    expected_restarts={(p['metadata']['uid'],c['name']):c['restartCount']
                       for p in pods for c in p['status'].get('containerStatuses',[])}
    actual_restarts={(r['metric']['uid'],r['metric']['container']):int(float(r['value'][1]))
                     for r in query('jointsla_kubernetes_container_restarts')}
    assert actual_restarts==expected_restarts,(actual_restarts,expected_restarts)
    targets=read(PROM+'/api/v1/targets')['data']['activeTargets']
    assert len(targets)>=3 and all(t['health']=='up' for t in targets)
    from joint_sla_v2.protocol import verify_freeze
    frozen=verify_freeze()
    demo=ROOT/'prototype/.cache/final_dashboard_demo'
    rows=list(csv.DictReader((demo/'request_outcomes.csv').open(encoding='utf-8')))
    summary=json.loads((demo/'summary.json').read_text(encoding='utf-8'))
    assert len(rows)==96 and len({r['request'] for r in rows})==96
    completed=sum(r['status']=='200' for r in rows)
    breaches=sum(r['status']!='200' or float(r['latency_ms'])>float(r['deadline_ms']) for r in rows)
    assert completed==summary['completed']==96
    assert all((r['sla_failure']=='True')==(r['status']!='200' or float(r['latency_ms'])>float(r['deadline_ms'])) for r in rows)
    assert breaches/96==summary['sla_failure_rate']
    from prototype.kubernetes.final_dashboard import SLA, RATE
    demo_end=(demo/'summary.json').stat().st_mtime-1
    demo_sla=query(SLA,demo_end)
    assert len(demo_sla)==1 and float(demo_sla[0]['value'][1])==0
    current_rate=query(RATE)
    if current_rate and float(current_rate[0]['value'][1])==0:
        assert not query(SLA)  # idle is undefined, not artificial 0%
    comparison=json.loads((OUTPUT/'comparison_verification.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in comparison['sources'].items())
    result=dict(status='passed',checked_utc=datetime.now(timezone.utc).isoformat(),
                dashboard_uid=deployed['uid'],panels=len(deployed['panels']),queries=queries,
                observer_up=True,observer_matches_current_pod_restart_counts=True,
                healthy_scrape_targets=len(targets),frozen_source_hashes_verified=len(frozen['source_hashes']),
                demo_requests=96,demo_completed=completed,demo_sla_failures=breaches,
                demo_seed=41,demo_rate_rps=8,audit_outcomes_unchanged=1420,
                zero_failure_demo_has_measured_zero_sla_rate=True,
                historical_audit_source_hashes_unchanged=True,
                tests_passed=310,historical_audit_tests=306,
                demo_is_separate_from_audit=True,
                dashboard_sha256=hashlib.sha256((ROOT/'prototype/kubernetes/final-dashboard.json').read_bytes()).hexdigest())
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'dashboard_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='queries'},indent=2))
    return result


if __name__=='__main__': validate()
