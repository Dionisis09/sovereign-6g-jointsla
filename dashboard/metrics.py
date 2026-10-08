"""Display conversions only; frozen inference is never recomputed."""
import pandas as pd

POLICIES = {
 'static':'Static', 'reactive':'Reactive', 'periodic':'Periodic',
 'sla_aware':'SLA-aware', 'joint_sla':'JointSLA-v1', 'joint_sla_v1':'JointSLA-v1',
 'joint_sla_v2':'JointSLA-v2', 'mjo':'MJO', 'sla_rr':'SLA + round robin',
 'sla_shortest_queue':'SLA + shortest queue', 'joint_no_queue':'JointSLA without queue',
 'joint_no_slack':'JointSLA without slack',
}
METRICS = {
 'vram_gb_seconds':('Integrated VRAM reservation','source GB·s',1.,'Frozen legacy reservation integral. Synthetic nominal GB units are not relabeled as measured binary GiB.'),
 'sla_breach_rate':('SLA breaches','%',100.,'All-offered request failure fraction: completed requests beyond deadline plus dropped/unplaced failures. Percentages are means across seeds, not pooled rates.'),
 'mean_request_latency_ms':('Mean request latency','ms',1.,'Mean end-to-end request latency per run, then mean across seeds.'),
 'p95_latency_ms':('p95 latency','ms',1.,'Within-run request latency 95th percentile; displayed mean across seeds is not a pooled percentile.'),
 'p99_latency_ms':('p99 latency','ms',1.,'Within-run request latency 99th percentile; displayed mean across seeds is not a pooled percentile.'),
 'average_replicas':('Average replicas','replicas',1.,'Time-average allocated replica count across the entire pool.'),
 'average_vram_residency_gib':('VRAM residency','GiB',1.,'Frozen time-average model memory reservation across the pool; GiB uses 2^30 bytes.'),
 'cold_starts':('Cold starts','events',1.,'Count of replica creation/readiness events in a run; see lifecycle definition in the source report.'),
 'total_actions':('Total actions','actions',1.,'Accepted scaling and migration actions during the run.'),
 'mean_queue_delay_ms':('Mean queue delay','ms',1.,'Frozen per-request waiting-delay aggregate; includes the queues defined by the source experiment.'),
 'controller_total_instrumented_mean_ms':('Controller overhead','ms',1.,'Mean full instrumented control step, including snapshot construction.'),
 'controller_cpu_ms_per_request':('Controller CPU/request','ms/request',1.,'Frozen total controller CPU cost normalized by request count.'),
 'Gold_breach_rate':('Gold breaches','%',100.,'Fraction of Gold requests exceeding their own deadline; seed mean.'),
 'Silver_breach_rate':('Silver breaches','%',100.,'Fraction of Silver requests exceeding their own deadline; seed mean.'),
 'Bronze_breach_rate':('Bronze breaches','%',100.,'Fraction of Bronze requests exceeding their own deadline; seed mean.'),
 'average_gpu_utilization':('GPU utilization','%',100.,'Time-average compute utilization; distinct from reserved VRAM.'),
 'preburst_active_replicas':('Ready replicas/service before burst','replicas/service',1.,'Seed-level mean ready service replicas immediately before each burst.'),
 'queue_growth':('Burst queue growth','requests',1.,'Mean increase in waiting requests during service burst windows.'),
 'recovery_window_breach_rate':('Recovery-window breaches','%',100.,'Frozen requests exceeding their deadline in the defined recovery windows; overlapping windows are not global request counts.'),
 'mean_recovery_after_burst_slots':('Recovery after burst','slots',1.,'Conditional observed recovery time; inspect censoring fraction alongside it.'),
 'mean_first_scaleout_delay_slots':('First scale-out delay','slots',1.,'Conditional observed first scale-out delay; missing events are censored, not zero.'),
 'scaleout_count':('Scale-outs per burst','events/burst',1.,'Frozen seed-level average scaling count in burst windows.'),
}

def policy_label(policy):
    return POLICIES.get(policy, str(policy))

def spec(metric):
    if metric in METRICS:
        return METRICS[metric]
    factor = 100. if metric.endswith('_rate') or metric.endswith('_fraction') else 1.
    unit = '%' if factor == 100. else ('ms' if metric.endswith('_ms') else 'source units')
    return metric.replace('_',' ').capitalize(), unit, factor, 'Definition and population: inspect the source report.'

def display_value(value, metric):
    return float(value) * spec(metric)[2] if pd.notna(value) else float('nan')

def ci(row, metric):
    """Parse existing asymmetric bounds; missing intervals stay missing."""
    low, high = row.get('ci95_lower'), row.get('ci95_upper')
    return (display_value(low,metric), display_value(high,metric)) if pd.notna(low) and pd.notna(high) else (None,None)

def paired_table(frame):
    """Adapt three frozen paired schemas while preserving their declared direction."""
    if frame.empty:
        return frame.copy()
    out=frame.copy()
    if 'absolute_difference' in out:
        out['delta']=out['absolute_difference']
        out['lower']=out['difference_ci95_lower']; out['upper']=out['difference_ci95_upper']
        # Verified source schema defines B minus A.
        out['comparison']=out['policy_B'].map(policy_label)+' − '+out['policy_A'].map(policy_label)
    elif 'delta_v2_minus_comparator' in out:
        out['delta']=out['delta_v2_minus_comparator']
        out['lower']=out['delta_ci95_lower'];out['upper']=out['delta_ci95_upper']
        out['comparison']='JointSLA-v2 − '+out['comparator'].map(policy_label)
    elif 'delta_joint_minus_sla' in out:
        out['delta']=out['delta_joint_minus_sla']
        out['lower']=out.get('delta_ci95_lower',float('nan'));out['upper']=out.get('delta_ci95_upper',float('nan'))
        out['comparison']='JointSLA-v1 − SLA-aware'
    return out

def paired_lookup(frame, metric, **dimensions):
    out=paired_table(frame)
    for c,v in {'metric':metric,**dimensions}.items():
        if c in out:
            out=out[out[c]==v]
    return out

def wide_means(summary):
    keys=[c for c in ['load_multiplier','scale','regime','policy'] if c in summary]
    return summary.pivot(index=keys,columns='metric',values='mean').reset_index() if not summary.empty else pd.DataFrame()
