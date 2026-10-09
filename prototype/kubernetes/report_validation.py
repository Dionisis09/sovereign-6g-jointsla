"""Publish compact observations/figures from the latest successful live run."""
import json
from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]

def main():
    run=sorted((ROOT/'prototype/.cache').glob('kubernetes_*/verification.json'))[-1]
    result=json.loads(run.read_text(encoding='utf-8'))
    assert result['status']=='passed'
    destination=Path(__file__).parent/'evidence'
    destination.mkdir(exist_ok=True)
    timeline=pd.read_csv(run.parent/'replica_timeline.csv')
    shutil.copyfile(run.parent/'replica_timeline.csv',destination/'replica_timeline.csv')
    compact={k:result[k] for k in ['status','physical_hosts','kubernetes_nodes','cpu_inference','pretrained',
                                  'peak_deployment_replicas','final_ready_replicas','applied_controller_actions',
                                  'paper_statistics_updated']}
    compact['source_run']=str(run.parent.relative_to(ROOT))
    rows=[]
    for phase in ['baseline','burst','failure']:
        frame=pd.read_csv(run.parent/phase/'request_outcomes.csv')
        assert len(frame)==result[phase]['offered'] and not frame.request.duplicated().any()
        completed=frame[frame.status==200]
        rows.append(dict(phase=phase,offered=len(frame),completed=len(completed),
            sla_failure_pct=100*result[phase]['sla_failure_rate'],
            failed_or_rejected_pct=100*result[phase]['failed_or_rejected_rate'],
            mean_completed_latency_ms=completed.latency_ms.mean(),
            p95_completed_latency_ms=completed.latency_ms.quantile(.95),
            serving_endpoints=completed.routed_to.nunique()))
    summary=pd.DataFrame(rows);summary.to_csv(destination/'summary.csv',index=False)
    compact['summary']=rows
    (destination/'verification.json').write_text(json.dumps(compact,indent=2),encoding='utf-8')
    fig,axes=plt.subplots(2,1,figsize=(10,6.5),sharex=True,layout='constrained')
    axes[0].step(timeline.elapsed_s,timeline.deployment_target,where='post',label='Deployment target',color='#146baf')
    axes[0].step(timeline.elapsed_s,timeline.ready_by_deployment,where='post',label='Ready pods',color='#239f82')
    axes[0].set_ylabel('Actual Kubernetes replicas');axes[0].set_ylim(0,5);axes[0].set_yticks(range(5));axes[0].legend(loc='upper left')
    axes[1].plot(timeline.elapsed_s,timeline.queue,color='#d16e36',label='Observed queue')
    axes[1].set_ylabel('Observed waiting / busy requests');axes[1].set_xlabel('Elapsed validation time (s)')
    for ax in axes:
        ax.grid(alpha=.2)
        for phase,color in [('burst','#e5aa53'),('scale_in','#9fc1d1'),('failure_recovery','#bc9aca')]:
            subset=timeline[timeline.phase==phase]
            if len(subset): ax.axvspan(subset.elapsed_s.min(),subset.elapsed_s.max(),alpha=.15,color=color,
                                      label=phase.replace('_',' ').title() if ax is axes[0] else None)
    axes[0].legend(loc='upper left',ncol=2,fontsize=9)
    axes[0].set_title('Real CPU inference on local Kubernetes · automatic warm repair, burst scaling and recovery')
    fig.savefig(destination/'scaling.png',dpi=170);plt.close(fig)
    lines=['# Kubernetes integration observations','',
        'Validated locally on 8 October 2026 (Europe/Athens). This is a functional',
        'integration test on one physical host and one kind node, using real pretrained',
        'CPU MobileNet inference. It is not a paired paper experiment or production benchmark.','',
        'The controller performed **1 → 2 → 4 → 2** replica reconciliation. New ready',
        'pods served traffic. After one pod was deleted, Kubernetes replaced it and',
        'the gateway excluded the failed endpoint without retrying the failed request.','',
        '| Phase | Offered | Completed | SLA failures (all offered) | Failed/rejected | Mean completed latency |',
        '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['phase']} | {row['offered']} | {row['completed']} | {row['sla_failure_pct']:.2f}% | {row['failed_or_rejected_pct']:.2f}% | {row['mean_completed_latency_ms']:.1f} ms |")
    lines.extend(['','Burst traffic was paced at 120 requests/s, 1280 requests total,',
        'with client concurrency bounded at 32. Gold/Silver/Bronze deadlines were',
        '200/400/800 ms; the service uses FIFO admission, not tier-priority queues.',
        'The burst still violated the <15% SLA objective; successful actuation is',
        'not evidence of SLA superiority. Rejected requests remain SLA failures.',
        'Completed latency excludes failed/rejected calls to avoid a deceptively low mean.','',
        '![Observed scaling and queue trajectory](evidence/scaling.png)','',
        'Compact sources: [summary](evidence/summary.csv), [timeline](evidence/replica_timeline.csv),',
        '[actuation verification](evidence/verification.json). Full per-request outcomes,',
        f"pod snapshots and logs remain locally in `{compact['source_run']}`.",'',
        'The earlier unpaced stress test exposed repeated routing to a failed pod.',
        'That run is retained locally. Endpoint withdrawal was fixed, tested, and',
        'validated again; the revised burst workload means these runs are not a paired',
        'performance comparison. Frozen scientific sources/results are unchanged.'])
    (Path(__file__).parent/'VALIDATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(summary.to_string(index=False))

if __name__=='__main__': main()
