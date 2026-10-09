"""Build the provisioned dashboard from explicit metric definitions."""
import json
from pathlib import Path

QUERIES=[
 ('Gateway p95 latency','histogram_quantile(0.95, sum by (le) (rate(jointsla_gateway_latency_seconds_bucket[1m])))','s'),
 ('Finalized SLA failures by tier','100 * sum by (tier) (rate(jointsla_gateway_sla_failures_total[1m])) / clamp_min(sum by (tier) (rate(jointsla_gateway_outcomes_total[1m])), 1e-9)','percent'),
 ('Replica waiting queues','jointsla_inference_queue','short'),
 ('Ready and desired replicas','jointsla_gateway_ready_replicas','short'),
 ('Actual CUDA allocated VRAM (zero for CPU)','jointsla_inference_vram_bytes','bytes'),
 ('Control actions by outcome','increase(jointsla_gateway_actions_total[1m])','short'),
 ('Failed/rejected finalized requests','sum by (tier, outcome) (rate(jointsla_gateway_outcomes_total{outcome!="completed"}[1m]))','reqps'),
 ('Measured control-step wall time','jointsla_gateway_decision_seconds','s')]

panels=[]
for i,(title,expr,unit) in enumerate(QUERIES):
    targets=[dict(refId='A',expr=expr,legendFormat='{{tier}} {{instance}} {{outcome}}')]
    if i==3: targets.append(dict(refId='B',expr='jointsla_gateway_desired_replicas',legendFormat='desired'))
    panels.append(dict(id=i+1,type='timeseries',title=title,gridPos=dict(x=(i%2)*12,y=(i//2)*8,w=12,h=8),
                       datasource=dict(type='prometheus',uid='prometheus'),targets=targets,
                       fieldConfig=dict(defaults=dict(unit=unit),overrides=[]),options={}))
dashboard=dict(uid='jointsla-runtime',title='JointSLA · real inference prototype',schemaVersion=41,version=1,
               refresh='5s',time=dict(**{'from':'now-15m','to':'now'}),panels=panels)
target=Path(__file__).parent/'dashboards'/'jointsla.json'
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(dashboard,indent=2),encoding='utf-8')
