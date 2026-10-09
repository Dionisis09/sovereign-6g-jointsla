"""Reproducible offered request schedule; real wall-clock outcomes are measured."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
import json
from pathlib import Path
import random
import time
from prototype.gateway import fetch

def run(url, requests=100, concurrency=8, seed=1, output='prototype/.cache/load', rate_rps=None):
    rng=random.Random(seed)
    jobs=[dict(seed=rng.randrange(2**31),tier=['Gold','Silver','Bronze'][i%3],deadline_ms=[200,400,800][i%3]) for i in range(requests)]
    def one(item):
        i,body,offered=item;call_start=time.perf_counter()
        start=call_start if offered is None else offered
        try: status,result=fetch(url+'/infer',body,timeout=65)
        except (OSError,ValueError) as error: status,result=0,{'error':str(error)}
        elapsed=(time.perf_counter()-start)*1000
        return dict(request=i,tier=body['tier'],deadline_ms=body['deadline_ms'],status=status,latency_ms=elapsed,
                    client_queue_ms=(call_start-start)*1000,
                    sla_failure=status!=200 or elapsed>body['deadline_ms'],routed_to=result.get('routed_to',''),
                    input_kind=result.get('input_kind',''),pretrained=result.get('pretrained',False))
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures=[];origin=time.perf_counter()
        for i,body in enumerate(jobs):
            if rate_rps is not None: time.sleep(max(0,origin+i/rate_rps-time.perf_counter()))
            offered=time.perf_counter() if rate_rps is not None else None
            futures.append(pool.submit(one,(i,body,offered)))
        rows=sorted((f.result() for f in as_completed(futures)),key=lambda row:row['request'])
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    with (folder/'request_outcomes.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(seed=seed,rate_rps=rate_rps,offered=requests,completed=sum(r['status']==200 for r in rows),
                 sla_failure_rate=sum(r['sla_failure'] for r in rows)/requests,
                 failed_or_rejected_rate=sum(r['status']!=200 for r in rows)/requests,
                 rejected_rate=sum(r['status']==503 for r in rows)/requests,
                 transport_error_rate=sum(r['status']==0 for r in rows)/requests,
                 mean_client_latency_ms=sum(r['latency_ms'] for r in rows)/requests,
                 tier_sla_failure_rate={tier:sum(r['sla_failure'] for r in rows if r['tier']==tier)/sum(r['tier']==tier for r in rows)
                                       for tier in ('Gold','Silver','Bronze') if any(r['tier']==tier for r in rows)})
    (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8090')
    parser.add_argument('--requests',type=int,default=100)
    parser.add_argument('--concurrency',type=int,default=8)
    parser.add_argument('--seed',type=int,default=1)
    parser.add_argument('--output',default='prototype/.cache/load')
    parser.add_argument('--rate-rps',type=float,default=None)
    args=parser.parse_args()
    if args.requests<1 or args.concurrency<1: parser.error('Positive requests/concurrency required')
    if args.rate_rps is not None and (not __import__('math').isfinite(args.rate_rps) or args.rate_rps<=0): parser.error('Positive finite rate required')
    print(json.dumps(run(args.url,args.requests,args.concurrency,args.seed,args.output,args.rate_rps),indent=2))
