"""Reconstruct the two recorded bursts and plot the immutable audit trajectories.

No simulation is rerun and no scientific result is rewritten. The small earlier
burst CSV is curated here so the comparison can be checked without host caches.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'prototype/kubernetes/evidence/final_dashboard'
AUDIT=ROOT/'prototype/kubernetes/evidence/infrastructure'


def build():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    previous=OUTPUT/'earlier_burst_request_outcomes.csv'
    if not previous.exists():
        shutil.copyfile(ROOT/'prototype/.cache/kubernetes_20261008T151215/burst/request_outcomes.csv',previous)
    final=pd.read_csv(AUDIT/'request_outcomes.csv')
    assert len(final)==1420
    rows=[]
    tiers=[]
    for run,frame in [('20261008T151215',pd.read_csv(previous)),
                      ('20261008T161511',final[final.phase=='burst'])]:
        completed=frame.status==200
        violations=(~completed)|(frame.latency_ms>frame.deadline_ms)
        assert violations.equals(frame.sla_failure)
        assert len(frame)==1280 and frame.request.nunique()==1280
        row=dict(run_utc=run,offered=len(frame),completed=int(completed.sum()),
                 on_time=int((~violations).sum()),late_completed=int((completed&violations).sum()),
                 rejected=int((frame.status==503).sum()),other_failed=int(((~completed)&(frame.status!=503)).sum()),
                 sla_failures=int(violations.sum()),sla_failure_percent=100*violations.mean(),
                 mean_completed_latency_ms=frame.loc[completed,'latency_ms'].mean(),
                 p95_completed_latency_ms=np.percentile(frame.loc[completed,'latency_ms'],95))
        rows.append(row)
        for tier,part in frame.groupby('tier'):
            failures=int(part.sla_failure.sum())
            tiers.append(dict(run_utc=run,tier=tier,offered=len(part),sla_failures=failures,
                              sla_failure_percent=100*failures/len(part)))
    assert [(r['sla_failures'],r['completed'],r['rejected']) for r in rows]==[(497,943,337),(605,852,428)]
    pd.DataFrame(rows).to_csv(OUTPUT/'burst_comparison.csv',index=False)
    pd.DataFrame(tiers).to_csv(OUTPUT/'burst_comparison_by_tier.csv',index=False)
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained')
    bottoms=np.zeros(2)
    for field,label,color in [('on_time','Completed within deadline','#22866a'),
                              ('late_completed','Completed late','#e8a23d'),
                              ('rejected','Rejected (503)','#c14a53')]:
        values=np.array([r[field] for r in rows])
        bars=ax.barh(['Earlier integration\n15:12:15 UTC','Final infrastructure audit\n16:15:11 UTC'],values,left=bottoms,label=label,color=color)
        ax.bar_label(bars,labels=[str(v) for v in values],label_type='center',color='white',fontsize=11)
        bottoms+=values
    ax.set(xlim=(0,1280),xlabel='Requests (1,280 offered in each separate run)',
           title='Same burst profile, separate wall-clock integration runs')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.17),ncol=3,frameon=False)
    fig.savefig(OUTPUT/'burst_comparison.png',dpi=170);plt.close(fig)
    timeline=pd.read_csv(AUDIT/'replica_timeline.csv')
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True,layout='constrained')
    for key,label in [('controller_target','JointSLA target'),('deployment_target','Deployment target'),
                      ('ready_by_controller','Routable ready')]:
        axes[0].step(timeline.elapsed_s,timeline[key],where='post',label=label)
    axes[0].set(ylabel='Replicas',ylim=(0,5),title='Final 1,420-outcome infrastructure audit: scaling and recovery')
    axes[0].legend(frameon=False,ncol=3)
    axes[1].plot(timeline.elapsed_s,timeline.queue,label='Observed queue',color='#c14a53')
    axes[1].plot(timeline.elapsed_s,timeline.rate_rps,label='Observed recent rate (requests/s)',color='#307ba7')
    axes[1].set(xlabel='Elapsed seconds from audit start',ylabel='Queue / observed requests per second',ylim=(0,None))
    axes[1].legend(frameon=False)
    fig.savefig(OUTPUT/'audit_scaling.png',dpi=170);plt.close(fig)
    manifest=dict(earlier_run='prototype/.cache/kubernetes_20261008T151215',
                  final_run='prototype/.cache/kubernetes_20261008T161511',
                  outcomes_verified=1420,comparison=rows,
                  protocol=dict(seed=23,offered=1280,rate_rps=120,concurrency=32,deadlines_ms=[200,400,800]),
                  sources={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [previous,AUDIT/'request_outcomes.csv',AUDIT/'replica_timeline.csv',AUDIT/'verdict.json']})
    (OUTPUT/'comparison_verification.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'verified_outcomes':1420,'bursts':[(r['run_utc'],r['sla_failures']) for r in rows]}))


if __name__=='__main__': build()
