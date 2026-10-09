"""Describe recorded failures without inferring unrecorded rejection causes.

Reads existing client CSVs only. Source hashes, tier counts and a precise evidence
boundary accompany the output; no deployment or frozen experiment is changed.
"""
import hashlib
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'prototype/kubernetes/evidence/research_gap_audit'


def analyze():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    sources={
        'earlier_integration':ROOT/'prototype/kubernetes/evidence/final_dashboard/earlier_burst_request_outcomes.csv',
        'final_infrastructure_audit':ROOT/'prototype/kubernetes/evidence/infrastructure/request_outcomes.csv'}
    records=[];classification=[]
    for run,path in sources.items():
        frame=pd.read_csv(path)
        if 'phase' in frame:
            frame=frame[frame.phase=='burst'].copy()
        assert len(frame)==1280 and frame.request.nunique()==1280
        completed=frame.status==200
        late=completed&(frame.latency_ms>frame.deadline_ms)
        assert ((~completed)|late).equals(frame.sla_failure)
        frame['category']='other_failed'
        frame.loc[completed&~late,'category']='completed_on_time'
        frame.loc[late,'category']='completed_late'
        rejected=frame.status==503
        routed=frame.routed_to.fillna('').ne('')
        frame.loc[rejected&routed,'category']='backend_503_reason_unrecorded'
        frame.loc[rejected&~routed,'category']='unrouted_503_reason_unrecorded'
        frame['run']=run
        classification.extend(frame[['run','request','tier','status','category','latency_ms','client_queue_ms','deadline_ms','routed_to']].to_dict('records'))
        for tier,part in frame.groupby('tier'):
            done=part.status==200
            delayed=done&(part.latency_ms>part.deadline_ms)
            records.append(dict(run=run,tier=tier,offered=len(part),
                completed=int(done.sum()),completed_on_time=int((done&~delayed).sum()),
                late_completed=int(delayed.sum()),rejected_503=int((part.status==503).sum()),
                backend_503_reason_unrecorded=int((part.category=='backend_503_reason_unrecorded').sum()),
                other_failed=int((part.category=='other_failed').sum()),
                sla_failures=int(part.sla_failure.sum()),sla_failure_percent=100*part.sla_failure.mean(),
                late_even_after_excluding_client_queue=int((delayed&((part.latency_ms-part.client_queue_ms)>part.deadline_ms)).sum()),
                mean_client_queue_ms_late=float(part.loc[delayed,'client_queue_ms'].mean()) if delayed.any() else None))
    final=[r for r in records if r['run']=='final_infrastructure_audit']
    assert sum(r['sla_failures'] for r in final)==605
    assert sum(r['rejected_503'] for r in final)==428
    assert sum(r['late_completed'] for r in final)==177
    assert next(r for r in final if r['tier']=='Gold')['late_completed']==177
    pd.DataFrame(records).to_csv(OUTPUT/'failure_by_tier.csv',index=False)
    pd.DataFrame(classification).to_csv(OUTPUT/'request_classification.csv',index=False)
    verdict=dict(status='descriptive_audit_passed',policy_comparison_performed=False,
        causal_attribution_performed=False,independent_repetitions=1,
        repetitions_definition='One recorded final burst; earlier revision is not an independent replicate of it.',
        observed_final_burst=dict(offered=1280,on_time=675,late_completed=177,
            late_gold=177,backend_503_reason_unrecorded=428,other_failed=0,
            sla_failures=605,sla_failure_percent=47.265625,
            late_even_excluding_client_queue=176),
        missing_evidence=['Per-request response error/rejection reason',
            'Backend execution and queue duration retained in client CSV',
            'Absolute offer/dispatch/completion timestamps and pod UID mapping',
            'Identical Kubernetes baseline runs and paired independent blocks'],
        source_hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.values()})
    (OUTPUT/'failure_audit.json').write_text(json.dumps(verdict,indent=2),encoding='utf-8')
    print(json.dumps(verdict['observed_final_burst'],indent=2))


if __name__=='__main__': analyze()
