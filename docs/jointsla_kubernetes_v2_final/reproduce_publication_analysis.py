from pathlib import Path
import json,shutil,argparse
import numpy as np,pandas as pd
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description='Regenerate publication analysis from existing frozen CSVs without rerunning traffic.')
parser.add_argument('--output',type=Path,default=R/'.cache/publication_v2_reproduction')
O=parser.parse_args().output.resolve()
assert not O.is_relative_to(R/'results') and not O.is_relative_to(R/'prototype'),'Do not write into frozen experiment trees'
(O/'tables').mkdir(exist_ok=True,parents=True);(O/'figures').mkdir(exist_ok=True)
S=R/'prototype/kubernetes/evidence/comparison_v2';d=pd.read_csv(S/'runs.csv');p=pd.read_csv(S/'paired_comparisons.csv');c=pd.read_csv(S/'failure_categories.csv')
order=['static','reactive','hpa','joint','joint_sq','reactive_joint'];labels=['Static-2 / RR','Reactive / SQ','Native HPA / SQ','JointSLA','Joint scaler / SQ','Reactive / Joint router'];short=['Static-2','Reactive','Native HPA','JointSLA','Joint scaler / SQ','Reactive / Joint router']
assert len(d)==180 and d.groupby('policy').size().eq(30).all() and d.offered.sum()==230400
metrics=['sla_failure_percent','p95_completed_latency_ms','rejection_percent','target_replica_seconds','ready_replica_seconds','gold_sla_failure_percent','silver_sla_failure_percent','bronze_sla_failure_percent','mean_completed_latency_ms','mean_backend_queue_ms','mean_execution_ms','observed_cpu_core_seconds','observed_throttled_period_percent']
rows=[]
for a in order:
 part=d[d.policy==a];r={'policy':a,'label':labels[order.index(a)],'n':30}
 for m in metrics:r[m+'_mean']=part[m].mean();r[m+'_std']=part[m].std(ddof=1)
 r['on_time_requests_mean']=(part.offered*(1-part.sla_failure_percent/100)).mean()
 r['target_replica_seconds_per_on_time_request']=r['target_replica_seconds_mean']/r['on_time_requests_mean']
 rows.append(r)
summary=pd.DataFrame(rows);summary.to_csv(O/'tables/policy_summary.csv',index=False)
shutil.copyfile(S/'paired_comparisons.csv',O/'tables/paired_sla_comparisons.csv');shutil.copyfile(S/'runs.csv',O/'tables/all_180_runs.csv')
tiers=[]
for a in order:
 for t,n in [('Gold',427),('Silver',427),('Bronze',426)]:
  counts=c[(c.policy==a)&(c.tier==t)].groupby('category')['count'].sum()
  offered=int(counts.sum());failed=int(counts.drop('completed_on_time',errors='ignore').sum())
  assert offered==30*n
  tiers.append({'policy':a,'tier':t,'offered':offered,'failed':failed,'on_time':offered-failed,'sla_failure_percent':100*failed/offered,'mean_run_rate_percent':summary.set_index('policy').loc[a,t.lower()+'_sla_failure_percent_mean'],'run_std_percent':summary.set_index('policy').loc[a,t.lower()+'_sla_failure_percent_std']})
pd.DataFrame(tiers).to_csv(O/'tables/per_tier_failures.csv',index=False)
c.groupby(['policy','tier','category'])['count'].sum().to_csv(O/'tables/failure_attribution.csv')
rng=np.random.default_rng(271830);resources=[]
for b in ['reactive','static','hpa','joint_sq','reactive_joint']:
 x=d.pivot(index='block',columns='policy',values='target_replica_seconds');diff=(x['joint']-x[b]).to_numpy();ci=np.percentile(diff[rng.integers(0,30,size=(10000,30))].mean(axis=1),[2.5,97.5]);base=summary.set_index('policy').loc[b];j=summary.set_index('policy').loc['joint']
 resources.append({'baseline':b,'joint_minus_baseline_target_rs_mean':diff.mean(),'ci95_low':ci[0],'ci95_high':ci[1],'ratio_of_mean_target_rs':j.target_replica_seconds_mean/base.target_replica_seconds_mean,'increase_percent_of_mean_target_rs':100*(j.target_replica_seconds_mean/base.target_replica_seconds_mean-1),'sla_failure_reduction_pp':float(-p[p.comparison=='joint minus '+b].sla_failure_difference_pp.iloc[0]),'extra_rs_per_additional_on_time_request':diff.mean()/(j.on_time_requests_mean-base.on_time_requests_mean)})
pd.DataFrame(resources).to_csv(O/'tables/resource_tradeoff.csv',index=False)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False});colors=['#7F8896','#C9823B','#5478AE','#147F6C','#70A89B','#916B9C']
claims={'schema':'publication_v1','blocks':30,'trials':180,'outcomes':230400,'policies':rows,'paired_sla':p.astype(object).where(pd.notna(p),None).to_dict('records'),'tiers':tiers,'resource_tradeoffs':resources,'resource_bootstrap_seed':271830,'resource_bootstrap_resamples':10000,'resource_analysis_role':'additional descriptive/exploratory analysis, no new experiments','primary':{'joint_sla':rows[3]['sla_failure_percent_mean'],'reactive_sla':rows[1]['sla_failure_percent_mean'],'effect_pp':11.5390625,'ci_low_pp':-13.984375,'ci_high_pp':-9.057291666666668,'holm_p':3.725290298461914e-8,'cost_increase_percent':resources[0]['increase_percent_of_mean_target_rs']}}
(O/'canonical_results.json').write_text(json.dumps(claims,indent=2,allow_nan=False),encoding='utf-8')
ablations=[]
for x in claims['paired_sla'][3:]:
 b=x['comparison'].removeprefix('joint minus ');a=summary.set_index('policy').loc[b]
 ablations.append(dict(x,comparator_sla_mean=a.sla_failure_percent_mean,comparator_sla_std=a.sla_failure_percent_std,comparator_target_replica_seconds_mean=a.target_replica_seconds_mean,comparator_target_replica_seconds_std=a.target_replica_seconds_std,interpretation='router effect not established' if b=='joint_sq' else 'consistent with scaling/headroom contribution; exploratory'))
pd.DataFrame(ablations).to_csv(O/'tables/ablation_results.csv',index=False)
for m,title,y,name in [('sla_failure_percent','All-offered SLA failures','SLA failures (%)','01_sla_failures'),('p95_completed_latency_ms','Completed-request p95 latency','Mean of per-run p95 values (ms)','02_p95_latency'),('rejection_percent','HTTP 503 rejection rate','HTTP 503 / all offered (%)','03_http503'),('target_replica_seconds','Target replica-time cost','Target replica-seconds','04_replica_cost')]:
 fig,ax=plt.subplots(figsize=(9,4.4),layout='constrained');means=summary[m+'_mean'];stds=summary[m+'_std'];ax.bar(np.arange(6),means,yerr=stds,color=colors,capsize=4);ax.set_xticks(np.arange(6),[s.replace(' / ','\n') for s in short],fontsize=8);ax.set(ylabel=y,title=title+' (mean ± sample SD, 30 blocks)');ax.set_ylim(0,400 if m=='p95_completed_latency_ms' else 140 if m=='target_replica_seconds' else 100)
 if m=='sla_failure_percent':ax.axhline(15,color='#AA3143',ls='--',label='15% target');ax.legend(frameon=False)
 fig.savefig(O/f'figures/{name}.png',dpi=180);fig.savefig(O/f'figures/{name}.pdf');plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4.4),layout='constrained')
for i,t in enumerate(['gold','silver','bronze']):ax.bar(np.arange(6)+(i-1)*.24,summary[t+'_sla_failure_percent_mean'],.24,label=t.title(),yerr=summary[t+'_sla_failure_percent_std'],capsize=2)
ax.set_xticks(np.arange(6),[s.replace(' / ','\n') for s in short],fontsize=8);ax.set(ylabel='All-offered SLA failures per tier (%)',ylim=(0,110),title='Tier failures (mean ± sample SD, 30 blocks)');ax.legend(frameon=False,ncol=3);fig.savefig(O/'figures/05_tier_failures.png',dpi=180);fig.savefig(O/'figures/05_tier_failures.pdf');plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4.4),layout='constrained')
for i,r in p.iterrows():ax.errorbar(r.sla_failure_difference_pp,4-i,xerr=[[r.sla_failure_difference_pp-r.ci95_low_pp],[r.ci95_high_pp-r.sla_failure_difference_pp]],fmt='o',color=colors[3] if i<3 else '#916B9C',capsize=4)
ax.axvline(0,color='#333333',ls='--');ax.set_yticks(range(5),list(p.comparison)[::-1]);ax.set(xlabel='JointSLA minus comparator (percentage points)',title='Paired SLA effects (95% block-bootstrap intervals)');fig.savefig(O/'figures/06_paired_and_ablations.png',dpi=180);fig.savefig(O/'figures/06_paired_and_ablations.pdf');plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4.4),layout='constrained')
for i,a in enumerate(order):
 part=d[d.policy==a];ax.scatter(part.target_replica_seconds,part.sla_failure_percent,color=colors[i],s=16,alpha=.28);ax.scatter(summary.iloc[i].target_replica_seconds_mean,summary.iloc[i].sla_failure_percent_mean,color=colors[i],marker='D',s=65,label=short[i])
ax.set(xlabel='Target replica-seconds (burst + fixed 20 s follow-up)',ylabel='All-offered SLA failures (%)',title='Lower failures use more target replica-time',ylim=(0,100));ax.legend(frameon=False,ncol=2,fontsize=8);fig.savefig(O/'figures/07_performance_cost.png',dpi=180);fig.savefig(O/'figures/07_performance_cost.pdf');plt.close(fig)
print(summary[['label','sla_failure_percent_mean','target_replica_seconds_mean']].to_string(index=False));print(pd.DataFrame(resources).to_string(index=False))

