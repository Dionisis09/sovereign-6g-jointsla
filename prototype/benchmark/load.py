"""Paced reproducible request tape; absolute times and response details retained."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
import hashlib
import json
from pathlib import Path
import random
import time
from prototype.gateway import fetch


def tape(seed,count=1280,rate=120.):
    rng=random.Random(seed)
    return [dict(request=i,input_seed=rng.randrange(2**31),tier=('Gold','Silver','Bronze')[i%3],
                 deadline_ms=(200,400,800)[i%3],scheduled_offset_s=i/rate) for i in range(count)]


def category(status,result,latency,deadline):
    if status==200: return 'completed_late' if latency>deadline else 'completed_on_time'
    if status==0: return 'client_transport_error'
    reason=result.get('error','')
    reasons={'Queue full':'queue_full','Replica draining':'replica_draining',
             'No fresh ready replica':'no_fresh_ready_replica','HTTP handler capacity exceeded':'http_handler_saturation',
             'Replica unavailable; request not retried to avoid duplicate execution':'backend_transport_error'}
    return reasons.get(reason,'unknown_rejection' if status==503 else 'other_http_error')


def run(url,seed,folder,count=1280,rate=120.,concurrency=32,phase='burst'):
    jobs=tape(seed,count,rate);folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    text=json.dumps(jobs,sort_keys=True,separators=(',',':'))
    (folder/'workload.json').write_text(text,encoding='utf-8')
    origin=time.perf_counter();wall=time.time()
    def one(job,offered,offered_wall):
        dispatched=time.perf_counter();dispatch_wall=time.time()
        body=dict(seed=job['input_seed'],tier=job['tier'],deadline_ms=job['deadline_ms'],request_id=f'{phase}-{seed}-{job["request"]}')
        transport_error=None
        try: status,result=fetch(url+'/infer',body,timeout=65)
        except (OSError,ValueError) as failure: status,result=0,{};transport_error=str(failure)
        finished=time.perf_counter();finish_wall=time.time();elapsed=(finished-offered)*1000
        row=dict(job,request_id=body['request_id'],scheduled_unix_s=wall+job['scheduled_offset_s'],
            offered_unix_s=offered_wall,dispatch_unix_s=dispatch_wall,completed_unix_s=finish_wall,
            offer_lag_ms=(offered-origin-job['scheduled_offset_s'])*1000,
            status=status,latency_ms=elapsed,client_queue_ms=(dispatched-offered)*1000,
            client_call_ms=(finished-dispatched)*1000,sla_failure=status!=200 or elapsed>job['deadline_ms'],
            category=category(status,result,elapsed,job['deadline_ms']),error_reason=result.get('error'),transport_error=transport_error,
            routed_to=result.get('routed_to'),pod_name=result.get('pod_name'),pod_uid=result.get('pod_uid'),
            gateway_latency_ms=result.get('gateway_latency_ms'),backend_latency_ms=result.get('latency_ms'),
            queue_ms=result.get('queue_ms'),execution_ms=result.get('execution_ms'),model_load_seconds=result.get('model_load_seconds'),
            pretrained=result.get('pretrained'),request_id_echo=result.get('request_id'))
        return row
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures=[]
        for job in jobs:
            time.sleep(max(0,origin+job['scheduled_offset_s']-time.perf_counter()))
            offered=time.perf_counter();offered_wall=time.time()
            futures.append(pool.submit(one,job,offered,offered_wall))
        rows=sorted((future.result() for future in as_completed(futures)),key=lambda r:r['request'])
    with (folder/'request_outcomes.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(seed=seed,offered=count,completed=sum(r['status']==200 for r in rows),
        sla_failures=sum(r['sla_failure'] for r in rows),workload_sha256=hashlib.sha256(text.encode()).hexdigest(),
        started_unix_s=wall,finished_unix_s=time.time(),rate_rps=rate,concurrency=concurrency,
        categories={k:sum(r['category']==k for r in rows) for k in sorted({r['category'] for r in rows})})
    (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary
