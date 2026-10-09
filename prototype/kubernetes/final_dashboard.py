"""Final local Grafana view: live serving telemetry plus dated audit evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RATE = 'sum(rate(jointsla_gateway_outcomes_total[1m]))'
# Tier counters are lazily created. Absence before any failure means zero only
# when a matching finalized-outcome series exists; no traffic stays undefined.
SLA = f'(100 * (sum(rate(jointsla_gateway_sla_failures_total[1m])) or (0 * {RATE})) / {RATE}) and ({RATE} > 0)'


def build_dashboard():
    verdict = json.loads((ROOT / 'prototype/kubernetes/evidence/infrastructure/verdict.json').read_text(encoding='utf-8'))
    panels = []

    def text(title, content, y, h):
        panels.append(dict(id=len(panels)+1, type='text', title=title,
                           gridPos=dict(x=0,y=y,w=24,h=h),
                           options=dict(mode='markdown',content=content)))

    def metric(title, queries, unit, x, y, w=12, h=8, stat=False, description=''):
        defaults = dict(unit=unit, min=0, noValue='No data',
                        color=dict(mode='palette-classic'))
        if unit == 'percent':
            defaults['max'] = 100
        if stat:
            defaults.update(decimals=1 if unit in ('percent','reqps') else 0,
                            color=dict(mode='fixed',fixedColor='blue'))
        panel = dict(id=len(panels)+1, type='stat' if stat else 'timeseries',
            title=title, description=description, gridPos=dict(x=x,y=y,w=w,h=h),
            datasource=dict(type='prometheus',uid='prometheus'),
            targets=[dict(refId=chr(65+i),expr=q,legendFormat=label,instant=stat)
                     for i,(label,q) in enumerate(queries)],
            fieldConfig=dict(defaults=defaults,overrides=[]),
            options=dict(reduceOptions=dict(calcs=['lastNotNull'],fields='',values=False),
                         colorMode='value',graphMode='none') if stat else dict(
                             legend=dict(displayMode='list',placement='bottom'),
                             tooltip=dict(mode='multi',sort='none')))
        panels.append(panel)

    text('JointSLA · local Kubernetes prototype complete',
         f"**Validated audit · 8 October 2026 UTC:** {verdict['tests_passed']} tests passed · "
         f"{verdict['request_outcomes_verified']:,} verified request outcomes · 8/8 drain responses. "
         "**Snapshot evidence, not live counters.** Live metrics refresh every 5 s. "
         "Completed can still be late; no traffic means no latency/SLA sample.",0,5)
    for x,title,q,unit in [
        (0,'Target replicas','jointsla_gateway_desired_replicas','short'),
        (6,'Ready replicas','jointsla_gateway_ready_replicas','short'),
        (12,'Request load (1m)','sum(rate(jointsla_gateway_requests_total[1m]))','reqps'),
        (18,'SLA failures % (1m)',SLA,'percent')]:
        metric(title,[('',q)],unit,x,3,w=6,h=4,stat=True,
               description='Live gateway measurement. SLA denominator: finalized application requests; late, rejected and failed count as failures.')
    for x,title,q in [
        (0,'Completed requests','sum(jointsla_gateway_outcomes_total{outcome="completed"})'),
        (6,'SLA failure count','sum(jointsla_gateway_sla_failures_total) or (0 * sum(jointsla_gateway_outcomes_total))'),
        (12,'Applied scale actions','sum(jointsla_gateway_actions_total{outcome="applied"}) or (0 * jointsla_gateway_snapshot_timestamp_seconds)'),
        (18,'Restarts (current pods)','sum(jointsla_kubernetes_container_restarts)')]:
        metric(title,[('',q)],'short',x,7,w=6,h=4,stat=True,
               description='Request/action totals are exact application counters since the current gateway process started; they reset on restart and are independent of the selected time range. Restarts are Kubernetes restartCount for current pod UIDs; deletion/replacement is not a restart.')

    metric('Request load and completed throughput',[
        ('Offered','sum(rate(jointsla_gateway_requests_total[1m]))'),
        ('Completed','sum(rate(jointsla_gateway_outcomes_total{outcome="completed"}[1m]))')], 'reqps',0,11)
    metric('Completed latency · mean and p95',[
        ('Mean','1000 * sum(rate(jointsla_gateway_latency_seconds_sum[1m])) / sum(rate(jointsla_gateway_latency_seconds_count[1m]))'),
        ('p95 estimate','1000 * histogram_quantile(0.95, sum by (le) (rate(jointsla_gateway_latency_seconds_bucket[1m])))')], 'ms',12,11,
        description='Gateway completion latency only; excludes rejected/failed calls and client-side waits. p95 is a histogram estimate, distinct from the exact client CSV p95.')
    metric('SLA failures by tier · late + rejected + failed',[
        ('{{tier}}','(100 * (sum by (tier) (rate(jointsla_gateway_sla_failures_total[1m])) or (0 * sum by (tier) (rate(jointsla_gateway_outcomes_total[1m])))) / sum by (tier) (rate(jointsla_gateway_outcomes_total[1m]))) and (sum by (tier) (rate(jointsla_gateway_outcomes_total[1m])) > 0)')], 'percent',0,19)
    metric('Request outcomes by tier',[
        ('{{tier}} / {{outcome}}','sum by (tier,outcome) (rate(jointsla_gateway_outcomes_total[1m]))')], 'reqps',12,19,
        description='Completed = successful execution, even if late. SLA satisfaction is tracked separately.')
    metric('Scaling and warm recovery · target vs ready',[
        ('JointSLA target','jointsla_gateway_desired_replicas'),
        ('Deployment target','jointsla_kubernetes_deployment_replicas'),
        ('Routable ready','jointsla_gateway_ready_replicas')], 'short',0,27)
    metric('Waiting queues per inference replica',[
        ('{{instance}}','jointsla_inference_queue')], 'short',12,27)
    metric('JointSLA actions · applied / failed / observed',[
        ('{{outcome}}','sum by (outcome) (increase(jointsla_gateway_actions_total[1m]))')], 'short',0,35,
        description='Applied actions are actual inference scaling patches; unchanged decisions are omitted. These counters do not include Kubernetes pod replacements.')
    metric('Container restarts · failure and recovery evidence',[
        ('{{pod}} / {{container}}','jointsla_kubernetes_container_restarts')], 'short',12,35,
        description='Kubernetes restartCount per pod UID. Replacements have a new UID; the old time series ends. A restart can be a liveness intervention, not necessarily a crash.')
    metric('Pod readiness · warm-up / replacement / recovery',[
        ('{{pod}} / ready','jointsla_kubernetes_pod_ready'),
        ('{{pod}} / terminating','jointsla_kubernetes_pod_terminating')], 'short',0,43,
        description='Namespace-scoped API snapshots every 5 s. Ready excludes terminating pods. Pod name and UID distinguish replacement from a container restart; short transitions may occur between polls.')
    metric('Pod waiting and last termination reasons',[
        ('{{pod}} / waiting {{reason}}','jointsla_kubernetes_container_waiting'),
        ('{{pod}} / last {{reason}}','jointsla_kubernetes_container_last_termination')], 'short',12,43,
        description='No data means no waiting/last-termination reason recorded. Last termination is historical state, not an ongoing failure or a new event count.')
    metric('Serving process CPU · cores',[
        ('{{job}} {{instance}}','rate(jointsla_inference_process_cpu_seconds_total[1m]) or rate(jointsla_gateway_process_cpu_seconds_total[1m])')], 'short',0,51,
        description='Linux process CPU, not node/cgroup-wide utilization. One core = 1.0.')
    metric('Serving process RAM · resident memory',[
        ('{{job}} {{instance}}','jointsla_inference_process_resident_memory_bytes or jointsla_gateway_process_resident_memory_bytes')], 'bytes',12,51,
        description='Resident memory of serving processes, not total container or physical-host memory.')
    metric('Actual allocated CUDA VRAM · zero in CPU mode',[
        ('{{instance}}','jointsla_inference_vram_bytes')], 'bytes',0,59)
    metric('JointSLA decision-step wall time',[
        ('Decision','1000 * jointsla_gateway_decision_seconds')], 'ms',12,59)
    metric('Telemetry freshness',[
        ('Controller','time() - jointsla_gateway_snapshot_timestamp_seconds'),
        ('Kubernetes API snapshot','time() - jointsla_kubernetes_snapshot_timestamp_seconds')], 's',0,67)
    metric('Scrape and Kubernetes observer health',[
        ('Scrape {{job}} {{instance}}','up{job=~"gateway|inference"}'),
        ('Kubernetes last API poll','jointsla_kubernetes_observer_up')], 'short',12,67)
    metric('HTTP saturation rejections · before tier parsing',[
        ('{{job}} {{instance}}','increase(jointsla_gateway_http_saturation_rejections_total[1m]) or increase(jointsla_inference_http_saturation_rejections_total[1m])')], 'short',0,75,
        description='Separate transport-level counter. Not included in parsed application tier denominators; client outcome CSV includes every offered request.')
    metric('Infrastructure alerts',[
        ('{{alertname}} / {{alertstate}}','ALERTS{alertname=~"JointSLA.*"}')], 'short',12,75,
        description='No data means no active pending/firing alerts; local rule evaluation, no external notification receiver.')
    text('Two recorded burst runs · keep separate from live metrics',
         '| Run (UTC, 8 Oct 2026) | Offered | Completed | SLA failures | Rejected | Mean / p95 completed client latency |\n'
         '|---|---:|---:|---:|---:|---:|\n'
         '| Earlier integration · 15:12:15 | 1,280 | 943 | 497 / 1,280 = **38.83%** | 337 | 168.84 / 308.85 ms |\n'
         '| Final infrastructure audit · 16:15:11 | 1,280 | 852 | 605 / 1,280 = **47.27%** | 428 | 204.57 / 307.12 ms |\n\n'
         'Same paced 120 requests/s, seed 23, concurrency 32 and Gold/Silver/Bronze deadlines 200/400/800 ms; separate wall-clock runs at different infrastructure revisions. '
         '**+8.44 percentage points; no causal or paired statistical claim. Neither meets <15%.** '
         'Sources: `prototype/kubernetes/evidence/verification.json` and `evidence/infrastructure/summary.csv`; '
         'the 1,420-outcome audit also includes 60 baseline and 80 recovery requests. Frozen paper experiments are unchanged.',83,9)
    for panel in panels[1:]:
        panel['gridPos']['y'] += 2  # Keep the audit card legible in narrow panels.
    return dict(uid='jointsla-runtime',title='JointSLA · Final local infrastructure dashboard',
                schemaVersion=41,version=2,refresh='5s',time={'from':'now-15m','to':'now'},
                tags=['JointSLA','local-prototype','validated'],panels=panels)
