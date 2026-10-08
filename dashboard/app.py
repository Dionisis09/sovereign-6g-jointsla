"""Frozen research evidence with a separate, isolated live replay view."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import html
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dashboard import data_loader as dl, charts as ch, components as ui
from dashboard.metrics import METRICS, spec, policy_label, paired_table, wide_means
from dashboard.data_validation import validate
from dashboard.styles import apply

PAGES=['Overview','System & JointSLA','Synthetic Results','Scalability','Controller Optimization',
 'Strong Baseline','Hardware Profiling','Hardware-Grounded Reversal','Pressure Sweep','Tier Behavior',
 'Model Class Behavior','Mechanism Analysis','Burst Recovery','JointSLA-v2','v2 Held-out Results',
 'Performance–Resource Trade-off','SOVEREIGN / Intent','Experiment Timeline','Research Story','Data / Reproducibility','Live Experiments']
CORE=['sla_breach_rate','mean_request_latency_ms','p95_latency_ms','p99_latency_ms']
RESOURCES=['average_replicas','average_vram_residency_gib','cold_starts','total_actions']
STORY=['Synthetic success','Scalability','Strong comparator','Hardware profiling','Hardware reversal',
 'Pressure sweep','Controlled decomposition','Held-out v2','Operating-envelope conclusion']
QUESTION='Under which operating conditions does coupled placement, scaling, and queue-aware request routing improve edge-AI performance, and when do resource consolidation, limited warm capacity, and cold-start recovery reverse those benefits?'

st.set_page_config(page_title='JointSLA · Research evidence',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
with st.sidebar:
    st.title('JointSLA')
    st.caption('SOVEREIGN-6G · frozen research evidence')
    presentation=st.toggle('Presentation Mode',key='presentation')
    learn=st.toggle('Learning Mode',key='learning')
    page=st.radio('PROJECT',PAGES,key='page')
    st.divider()
    st.caption('Frozen evidence stays read-only. Live replays have separate outputs.')
apply(presentation)
ui.notice('Live execution — archived inputs, unchanged policies, isolated outputs.' if page=='Live Experiments' else 'Visualization only — no experiment execution or parameter tuning.')

@st.cache_data(show_spinner=False)
def startup_validation():return validate()
checks=startup_validation()
failed=checks[~checks.passed]
if not failed.empty:
    with st.expander(f'Data validation: {len(failed)} warnings'):
        st.dataframe(failed,width='stretch',hide_index=True)

def rel(dataset,filename):return 'results/'+dl.DIRECTORIES[dataset]+'/'+filename

def select_summary(dataset,filename='summary_statistics.csv',policy=True):
    data=dl.load_csv(dataset,filename)
    if data.empty:st.warning('Panel unavailable — source artifact not found.');return data,{}
    if not {'policy','metric','mean'}.issubset(data):
        st.warning('Panel unavailable — source artifact has an incompatible schema.');return pd.DataFrame(),{}
    scope={}
    dimensions=[c for c in ['scale','load_multiplier','tier','model_class','regime'] if c in data]
    cols=st.columns(max(1,len(dimensions)+int(policy)))
    for i,col in enumerate(dimensions):
        values=list(data[col].dropna().unique())
        if col=='scale':values=[v for v in ['SMALL','MEDIUM','LARGE'] if v in values]
        if col=='load_multiplier':values=sorted(values)
        with cols[i]:
            value=st.selectbox(col.replace('_',' ').title(),values,key=page+col,
                format_func=(lambda x:f'{x:.2f}×') if col=='load_multiplier' else str,
                index=values.index(1.) if col=='load_multiplier' and 1. in values else 0)
        scope[col]=value
    if policy:
        with cols[-1]:
            policies=list(data.policy.unique())
            preferred=[p for p in policies if p in ['sla_aware','joint_sla','joint_sla_v1','joint_sla_v2','mjo']]
            scope['policy']=st.multiselect('Policy',policies,default=preferred or policies,format_func=policy_label,key=page+'policies')
    return dl.filter_frame(data,**scope),scope

def grid(summary,metrics=CORE,x='policy',prefix='main'):
    if summary.empty or 'metric' not in summary:
        st.info('Panel unavailable — source artifact not found.');return
    cols=st.columns(2)
    for i,m in enumerate(metrics):
        with cols[i%2]:
            ui.chart(ch.metric_chart(summary,m,x,presentation),page+prefix+m)
            st.caption(spec(m)[3])

def stats(dataset,scope,metric=None):
    data=dl.filter_frame(dl.load_csv(dataset,'paired_tests.csv'),**{k:v for k,v in scope.items() if k!='policy'})
    if metric and 'metric' in data:data=data[data.metric==metric]
    if 'policy' in scope and {'policy_A','policy_B'}.issubset(data):
        data=data[data.policy_A.isin(scope['policy']) & data.policy_B.isin(scope['policy'])]
    if 'policy' in scope and 'comparator' in data:
        if 'joint_sla_v2' not in scope['policy']:data=data.iloc[:0]
        else:data=data[data.comparator.isin(scope['policy'])]
    ui.statistics(data,rel(dataset,'paired_tests.csv'))
    return paired_table(data)

def figures(dataset):
    with st.expander('Original verified figures / full source report'):
        folder=dl.discover()[dataset]/'figures'
        files=sorted(folder.glob('*.png'))
        if files:
            choice=st.selectbox('Original figure',[p.name for p in files],key=page+'originalfigure')
            st.image(str(folder/choice),caption=rel(dataset,'figures/'+choice),width='stretch')
        else:st.caption('Panel unavailable — source artifact not found.')
        report=dl.load_text(dataset)
        if report:
            st.download_button('Download original report',report,file_name=dataset.lower()+'_report.md',key=page+'reportdl')
            if not presentation:st.markdown(report)

def trajectories(dataset):
    """Lazy per-run slot/node files only, never request-level tapes."""
    with st.expander('Explore a frozen run · latency, burst peaks and node utilization'):
        if not st.checkbox('Load small slot / node trajectories',key=page+'load-trajectory'):return
        runs=dl.raw(dataset)
        if runs.empty or 'load_multiplier' not in runs:
            st.info('Panel unavailable — source artifact not found.');return
        cols=st.columns(3)
        loads=sorted(runs.load_multiplier.unique())
        with cols[0]:load=st.selectbox('Trajectory load',loads,index=loads.index(1.) if 1. in loads else 0,key=page+'trajload')
        with cols[1]:seed=st.selectbox('Trajectory seed',sorted(runs.seed.unique()),key=page+'trajseed')
        policies=list(runs.policy.unique())
        with cols[2]:policy=st.selectbox('GPU / CPU node-view policy',policies,format_func=policy_label,key=page+'trajpolicy')
        slots=[]
        for p in policies:
            filename=f'runs/load_{load:.2f}/seed_{int(seed):03d}/{p}/slot_trajectories.csv.gz'
            frame=dl.load_csv(dataset,filename)
            if not frame.empty:slots.append(frame.assign(policy=p,Policy=policy_label(p)))
        if not slots:
            st.info('Panel unavailable — source artifact not found.');return
        combined=pd.concat(slots,ignore_index=True)
        for metric,title,unit in [('latency_ms','Request cohort latency vs slot','ms'),('cumulative_sla_breach_pct','Cumulative arrival-cohort SLA failure rate','%'),('waiting_requests','Waiting requests vs slot','requests')]:
            if metric in combined:
                fig=px.line(combined,x='slot',y=metric,color='Policy',color_discrete_map=ch.COLORS)
                ui.chart(ch.finish(fig,title,unit,presentation),page+'traj'+metric)
        burst=slots[0][['slot','burst_service_fraction']].copy()
        burst['Bursting services (%)']=burst.burst_service_fraction*100
        ui.chart(ch.finish(px.area(burst,x='slot',y='Bursting services (%)',color_discrete_sequence=['#8793a8']),'Frozen burst exposure','% of services',presentation),page+'burstexposure')
        st.caption('Slot latency/SLA use frozen arrival-cohort accounting, including completions after the horizon where recorded. These curves are one selected seed, not a new 30-seed estimate. Cumulative percentages are already percent and are not multiplied by 100.')
        nodefile=f'runs/load_{load:.2f}/seed_{int(seed):03d}/{policy}/node_trajectories.csv.gz'
        nodes=dl.load_csv(dataset,nodefile)
        if not nodes.empty:
            for field,title in [('gpu_utilization','GPU compute utilization by node'),('cpu_utilization','CPU utilization by node'),('gpu_vram_reserved_fraction','VRAM reservation by node')]:
                matrix=nodes.pivot(index='node',columns='slot',values=field)*100
                fig=px.imshow(matrix,aspect='auto',color_continuous_scale=['#111d2d','#55b7ec'],zmin=0,zmax=100,labels={'x':'Slot','y':'Node','color':'%'})
                ui.chart(ch.finish(fig,title+' · '+policy_label(policy),'Node',presentation),page+'nodes'+field)
            ui.evidence(nodes,rel(dataset,nodefile),'Selected node trajectory / CSV export')
        ui.evidence(combined,rel(dataset,f'runs/load_{load:.2f}/seed_{int(seed):03d}/*/slot_trajectories.csv.gz'),'Selected slot trajectories / CSV export')

def generic(dataset,conclusion=None):
    summary,scope=select_summary(dataset)
    if summary.empty:return
    ui.cards(summary,['sla_breach_rate'])
    metric=st.selectbox('Metric',CORE+RESOURCES+['controller_total_instrumented_mean_ms','controller_cpu_ms_per_request'],format_func=lambda m:spec(m)[0],key=page+'metric')
    ui.chart(ch.metric_chart(summary,metric,presentation=presentation),page+'chosen')
    tabs=st.tabs(['QoS','Resources','Seed explorer'])
    with tabs[0]:grid(summary)
    with tabs[1]:
        resource_metrics=RESOURCES.copy()
        if 'average_vram_residency_gib' not in summary.metric.values:
            resource_metrics[1]='vram_gb_seconds'
        grid(summary,resource_metrics,prefix='resources')
    with tabs[2]:
        frame=dl.filter_frame(dl.raw(dataset),**scope)
        if not frame.empty:
            seed=st.selectbox('Seed',['All']+sorted(frame.seed.unique().tolist()),key=page+'seed')
            ui.chart(ch.distribution(frame,metric,presentation),page+'distribution')
            shown=frame if seed=='All' else frame[frame.seed==seed]
            columns=[c for c in ['seed','policy','traffic_hash','workload_hash',*CORE,*RESOURCES] if c in shown]
            ui.evidence(shown[columns],rel(dataset,'raw_policy_results.csv' if dataset in ['Synthetic','Baseline'] else 'raw_results.csv'))
    stats(dataset,scope,metric)
    ui.evidence(summary,rel(dataset,'summary_statistics.csv'))
    if conclusion:ui.notice(conclusion)
    figures(dataset)

if page=='Live Experiments':
    from dashboard.live_page import render
    render(presentation)
elif page=='Overview':
    st.title('When Coupled Edge-AI Orchestration Helps — and When It Hurts')
    st.write('Hardware-grounded characterization of performance, resource, and recovery trade-offs')
    st.info(QUESTION)
    cols=st.columns(4)
    messages=[('Synthetic regime','JointSLA improves SLA + latency'),('Hardware-grounded 1×','JointSLA-v1 loses aggregate SLA'),
              ('High pressure 2×','JointSLA-v1 strongly improves tail latency'),('Held-out v2','Gold improves; overall trade-off remains')]
    for col,(title,text) in zip(cols,messages):
        with col:st.markdown(f'<div class="story"><b>{title}</b><p>{text}</p></div>',unsafe_allow_html=True)
    ui.flow(STORY)
    summary=dl.filter_frame(dl.load_csv('Held-out'),load_multiplier=1.,policy=['sla_aware','joint_sla_v1','joint_sla_v2'])
    st.subheader('Held-out 1× · 30 paired seeds, 31–60')
    grid(summary,['sla_breach_rate','Gold_breach_rate'])
    with st.expander('Explain the paper in 60 seconds'):
        st.write('Edge AI needs decisions about where services run, how many replicas remain ready, and which replica receives each request. JointSLA couples those decisions. Synthetic results were strong and benefits persisted at tested scales. Hardware-derived execution, memory and readiness costs reversed the aggregate SLA conclusion. Higher load restored a strong latency advantage, without a statistically supported aggregate-SLA crossover. Controlled analysis links the trade-off to VRAM, warm capacity and cold recovery interactions. A frozen v2 mitigation improves Gold relative to v1 but does not eliminate the overall trade-off. The contribution is an operating-envelope characterization.')
    st.subheader('Final scientific contribution')
    st.write('1. A coupled placement/scaling/routing system as the experimental subject; this alone is not claimed as novel.\n\n2. Characterization across tested scale and offered load.\n\n3. Hardware-grounded evidence that synthetic conclusions can reverse.\n\n4. Mechanism analysis linking consolidation, warm capacity, VRAM and recovery.\n\n5. Held-out mitigation revealing the remaining priority/performance/resource trade-off.')
    ui.evidence(summary,rel('Held-out','summary_statistics.csv'))

elif page=='System & JointSLA':
    st.title('System & JointSLA')
    ui.flow(['Request','Network transfer','CPU preprocessing','GPU inference','CPU postprocessing','Deadline check'])
    ui.flow(['CPU','GPU execution units','VRAM','Bandwidth','Service / node queues'])
    ui.flow(['Replica allocation','Cold readiness','Ready / warm','Scale-out','Scale-in or migration'])
    st.write('SLA tiers provide deadlines and relative orchestration priority. They do not imply preemptive execution or guaranteed admission. A replica reserves resources; ready replicas can serve immediately, while cold replicas must become ready first.')
    st.subheader('Routing illustration · explanatory values, not experimental evidence')
    cols=st.columns(2)
    with cols[0]:queue_a=st.slider('Replica A queue delay (ms)',0,200,80,step=5)
    with cols[1]:queue_b=st.slider('Replica B queue delay (ms)',0,200,10,step=5)
    example=pd.DataFrame({'Replica':['A · near','B · farther'],'Network (ms)':[2,8],'Illustrative queue (ms)':[queue_a,queue_b],'Compute (ms)':[6,6]})
    example['Illustrative total (ms)']=example.iloc[:,1:].sum(axis=1)
    st.dataframe(example,hide_index=True,width='stretch')
    ui.notice(f'Nearest-node chooses A. An illustrative queue-aware minimum estimate chooses {"A" if queue_a+2<=queue_b+8 else "B"}. This is arithmetic teaching material, not a replay of JointSLA routing.')
    with st.expander('Inputs and decision boundary'):
        st.write('Service metadata + current/past telemetry → placement/scaling decisions and a separate routing choice → simulated execution → monitoring feedback. No future arrivals are read by the controller.')

elif page=='Synthetic Results':
    st.title('Synthetic results · original 30-seed regime')
    ui.notice('SLA-aware versus JointSLA-v1 is the focal comparison. Other policies and routing ablations are available in the selector.')
    generic('Synthetic','Benefits are scoped to this original synthetic regime. Hardware-grounded results below change the conclusion.')
    with st.expander('Earlier static / reactive / periodic baseline'):
        base=dl.load_csv('Baseline');grid(base,prefix='baseline');ui.evidence(base,rel('Baseline','summary_statistics.csv'))

elif page=='Scalability':
    st.title('Scalability · tested system sizes')
    ui.flow(['SMALL · 5 nodes / 20 services','MEDIUM · 10 / 40','LARGE · 20 / 80'])
    summary=dl.filter_frame(dl.load_csv('Scalability'),policy=['sla_aware','joint_sla'])
    grid(summary,x='scale',prefix='scale_compare')
    grid(summary,['average_replicas','vram_gb_seconds','total_actions','controller_total_instrumented_mean_ms'],x='scale',prefix='scale_resources')
    ui.notice('JointSLA retains statistically supported benefits as system size increases, without algorithm retuning. This applies to the tested synthetic sizes only.')
    generic('Scalability')

elif page=='Controller Optimization':
    st.title('Controller implementation optimization')
    frame=dl.load_csv('Controller','controller_performance_before_after.csv')
    if frame.empty:st.warning('Panel unavailable — source artifact not found.')
    else:
        statistic=st.selectbox('Timing statistic',['mean','median','p95'])
        data=frame.melt(id_vars=['scale'],value_vars=[f'{p}_full_controller_{statistic}_ms' for p in ['legacy','optimized']],var_name='Implementation',value_name='ms')
        data['Implementation']=data.Implementation.str.split('_').str[0]
        fig=px.bar(data,x='scale',y='ms',color='Implementation',barmode='group',color_discrete_sequence=['#8793a8','#55b7ec'])
        if statistic=='mean':fig.add_hline(y=10,line_dash='dash',annotation_text='10 ms mean budget')
        ui.chart(ch.finish(fig,'Full controller · '+statistic,'ms',presentation),'controller-timing')
        speed=frame[['scale','speedup_full_controller','speedup_snapshot']].melt(id_vars='scale',var_name='Component',value_name='Speedup')
        ui.chart(ch.finish(px.bar(speed,x='scale',y='Speedup',color='Component',barmode='group',color_discrete_sequence=['#55b7ec','#e5ad63']),'Measured implementation speedup','×',presentation),'controller-speed')
        ui.evidence(frame,rel('Controller','controller_performance_before_after.csv'))
        ui.evidence(dl.load_csv('Controller','full_30seed_equivalence.csv'),rel('Controller','full_30seed_equivalence.csv'))
    ui.notice('Implementation optimization only — scientific decisions and outcomes unchanged.')
    figures('Controller')

elif page=='Strong Baseline':
    st.title('Strong comparator · MJO')
    ui.notice('MJO is an optimization-inspired strong comparator, not an exact reproduction of a published algorithm.')
    generic('MJO','Mixed findings: JointSLA has aggregate-SLA and controller-cost advantages in tested comparisons; MJO protects Gold better and wins LARGE p99. Inspect the selected scale and frozen tests.')
    summary=dl.load_csv('MJO')
    scale=st.selectbox('Operating-point scale',['SMALL','MEDIUM','LARGE'],key='mjo_scatter_scale')
    points=wide_means(dl.filter_frame(summary,scale=scale))
    ui.chart(ch.operating_points(points,'controller_cpu_ms_per_request','sla_breach_rate',presentation),'mjo-cost')
    grid(dl.filter_frame(summary,scale=scale),['Gold_breach_rate','Silver_breach_rate','Bronze_breach_rate','controller_cpu_ms_per_request'],prefix='tiers')

elif page=='Hardware Profiling':
    st.title('Physical hardware profiling')
    hardware=dl.load_json('Profiling','hardware_info.json')
    st.write(hardware.get('cpu_model',ui.UNAVAILABLE))
    for device in hardware.get('devices',[]):
        st.write(f'{device["name"]} · {device["total_vram_bytes"]/2**30:.2f} GiB physical VRAM')
    st.caption(hardware.get('background_load_caveat',''))
    profile=dl.load_csv('Profiling','model_profile_summary.csv')
    cold=dl.load_csv('Profiling','cold_start_summary.csv')
    if not profile.empty:
        model=st.multiselect('Models',list(profile.model.unique()),default=list(profile.model.unique()))
        statistic=st.selectbox('Measured statistic',['mean','median','p95','p99'])
        subset=profile[profile.model.isin(model) & profile.stage.isin(['cpu_pre','input_upload','gpu_inference','cpu_post'])]
        fig=px.bar(subset,x='model',y=statistic,color='stage',barmode='group',color_discrete_sequence=['#55b7ec','#8793a8','#e5ad63','#ba9af0'])
        ui.chart(ch.finish(fig,'Measured pipeline stage latency','ms',presentation),'profile-stages')
        coldsel=cold[cold.model.isin(model)&cold.stage.eq('cold_start_total')] if {'model','stage'}.issubset(cold) else pd.DataFrame()
        combined=pd.concat([subset[subset.stage.eq('gpu_inference')].assign(Cost='Steady GPU inference'),coldsel.assign(Cost='Cold readiness')])
        ui.chart(ch.finish(px.bar(combined,x='model',y=statistic,color='Cost',barmode='group',color_discrete_sequence=['#55b7ec','#e5ad63']),'Steady inference versus cold readiness','ms',presentation),'profile-cold')
        ui.notice('Steady-state inference is only a few milliseconds, while cold readiness can be tens to hundreds of milliseconds.')
        memory=dl.load_csv('Profiling','vram_summary.csv')
        if not memory.empty:
            memory=memory[memory.model.isin(model)].copy()
            for c in list(memory):
                if c.endswith('_bytes'):memory[c.replace('_bytes','_gib')]=memory[c]/2**30
            ui.evidence(memory,rel('Profiling','vram_summary.csv'),'VRAM · original bytes and presentation-only GiB conversion')
        ui.evidence(subset,rel('Profiling','model_profile_summary.csv'))
        ui.evidence(coldsel,rel('Profiling','cold_start_summary.csv'))
    else:st.warning('Panel unavailable — source artifact not found.')
    figures('Profiling')

elif page=='Hardware-Grounded Reversal':
    st.title('Hardware grounding reverses the aggregate SLA conclusion')
    ui.flow(['Fewer allocated replicas','Less warm capacity','More cold recovery exposure'])
    generic('Hardware','Resource economy and QoS move in opposite directions in this DIRECT / 1× regime. The controlled decomposition explores interactions; this view alone does not establish a unique cause.')

elif page=='Pressure Sweep':
    st.title('Operating envelope · offered load 0.50×–2.00×')
    full=dl.load_csv('Pressure')
    summary,scope=select_summary('Pressure')
    ui.cards(summary,['sla_breach_rate','p95_latency_ms'])
    selected_metric=st.selectbox('Selected-load metric',CORE+RESOURCES+['mean_queue_delay_ms'],format_func=lambda m:spec(m)[0],key='pressure-card-metric')
    if selected_metric not in ['sla_breach_rate','p95_latency_ms']:ui.cards(summary,[selected_metric])
    all_loads=dl.filter_frame(full,policy=scope.get('policy',[]))
    grid(all_loads,CORE,x='load_multiplier')
    grid(all_loads,['average_replicas','average_vram_residency_gib','mean_queue_delay_ms','total_actions'],x='load_multiplier',prefix='pressure-resources')
    paired=paired_table(dl.load_csv('Pressure','paired_tests.csv'))
    for m in CORE:
        if {'sla_aware','joint_sla'}.issubset(scope.get('policy',[])):
            ui.chart(ch.paired_chart(paired,m,presentation=presentation),page+'delta'+m)
    ui.notice('At 2× the mean SLA difference changes sign, but statistical support for an aggregate-SLA crossover is insufficient. High pressure restores strong mean/p95/p99 latency advantages for v1.')
    stats('Pressure',scope)
    ui.evidence(summary,rel('Pressure','summary_statistics.csv'))
    ui.evidence(dl.filter_frame(dl.load_csv('Pressure','paired_seed_differences.csv'),**{k:v for k,v in scope.items() if k!='policy'}),rel('Pressure','paired_seed_differences.csv'))
    figures('Pressure')
    trajectories('Pressure')

elif page in ['Tier Behavior','Model Class Behavior']:
    st.title(page+' · pressure sweep')
    dimension='tier' if page=='Tier Behavior' else 'model_class'
    filename=dimension+'_summary_statistics.csv'
    full=dl.load_csv('Pressure',filename)
    summary,scope=select_summary('Pressure',filename)
    subset=dl.filter_frame(full,**{k:v for k,v in scope.items() if k!='load_multiplier'})
    grid(subset,x='load_multiplier')
    ui.notice('Gold remains a persistent v1 weakness; Bronze benefits at high pressure.' if dimension=='tier' else 'No single model class alone explains the reversal. These are subgroup outcomes, not independent causal effects.')
    ui.evidence(summary,rel('Pressure',filename));figures('Pressure')

elif page=='Mechanism Analysis':
    st.title('Controlled decomposition · D0–D7')
    definitions=dl.load_json('Mechanism','regime_definitions.json')
    if definitions:
        st.dataframe(pd.DataFrame.from_dict(definitions.get('regimes',{}),orient='index'),width='stretch')
    paired=paired_table(dl.load_csv('Mechanism','paired_differences.csv'))
    chosen=paired[paired.metric.eq('sla_breach_rate')].copy() if not paired.empty else paired
    if not chosen.empty:
        chosen['Delta (pp)']=chosen.delta*100
        fig=px.bar(chosen,x='regime',y='Delta (pp)',color='Delta (pp)',color_continuous_scale=['#55b7ec','#e5ad63'])
        fig.add_hline(y=0,line_dash='dash');fig.update_layout(coloraxis_showscale=False)
        ui.chart(ch.finish(fig,'JointSLA-v1 − SLA-aware · aggregate SLA','percentage points',presentation),'decomp')
        st.caption('Exploratory 10-seed decomposition. Paired CI is not supplied in this artifact; no CI was invented.')
    factor=dl.load_csv('Mechanism','factor_effects.csv')
    if not factor.empty:
        factor=factor[factor.metric.eq('sla_breach_rate')].copy();factor['Attribution (pp)']=factor.shapley_reversal_contribution*100
        ui.chart(ch.finish(px.bar(factor,x='factor',y='Attribution (pp)',color_discrete_sequence=['#e5ad63']),'Shapley-style reversal attribution','percentage points',presentation),'attribution')
    ui.notice('Execution time alone does not explain the reversal. These values include interaction effects. Do not interpret them as independent physical causal effects.')
    ui.evidence(chosen,rel('Mechanism','paired_differences.csv'))
    ui.evidence(factor,rel('Mechanism','factor_effects.csv'))
    ui.evidence(dl.load_csv('Mechanism','interaction_effects.csv'),rel('Mechanism','interaction_effects.csv'))
    figures('Mechanism')

elif page=='Burst Recovery':
    st.title('Burst recovery · warm capacity matters')
    dataset=st.selectbox('Evidence series',['Pressure','Mechanism','Held-out'])
    filename='burst_seed_summary.csv' if dataset=='Held-out' else 'burst_summary.csv'
    frame=dl.load_csv(dataset,filename)
    if not frame.empty:
        for dim in ['load_multiplier','regime']:
            if dim in frame:
                vals=sorted(frame[dim].unique());value=st.selectbox(dim.replace('_',' ').title(),vals,index=vals.index(1.) if 1. in vals else vals.index('D7') if 'D7' in vals else 0)
                frame=frame[frame[dim]==value]
        for m in ['preburst_active_replicas','queue_growth','recovery_window_breach_rate','mean_recovery_after_burst_slots','mean_first_scaleout_delay_slots','scaleout_count']:
            ui.chart(ch.distribution(frame,m,presentation),'burst'+m)
        st.caption('Frozen seed-level burst summaries. Recovery and scale-out delays are conditional on observed events; censored fractions and window counts remain in the source table. Recovery windows can overlap.')
        ui.evidence(frame,rel(dataset,filename))
    else:st.warning('Panel unavailable — source artifact not found.')
    ui.flow(['Aggressive consolidation','Fewer warm replicas','Burst arrives','Queue grows','Cold readiness delay','SLA violations'])
    ui.notice('Warm replica: ready immediately. Cold replica: must become ready before serving requests. This process diagram summarizes a mechanism hypothesis supported by controlled comparisons, not a unique causal proof.')
    figures(dataset)
    if dataset in ['Pressure','Held-out']:trajectories(dataset)

elif page=='JointSLA-v2':
    st.title('JointSLA-v2 · mechanism-driven mitigation test')
    ui.flow(['v1 decisions and routing','Recovery-aware warm headroom','Bounded Gold protection'])
    st.write('Routing remains v1. A scale-in guard and bounded Gold repair operate under the same action budget, using current/past information. This is one frozen mitigation candidate, evaluated for both benefits and costs.')
    ui.flow(['Development · seeds 101–105','Freeze','Held-out · seeds 31–60'])
    manifest=dl.load_json('Held-out','freeze_manifest.json')
    with st.expander('Freeze integrity / exact frozen settings'):
        st.json({k:manifest.get(k) for k in ['timestamp','statement','parameters','config_sha256','protected_history']})
        st.code(rel('Held-out','freeze_manifest.json'))
    generic('Development','Development data were used to design the single candidate. They are not independent held-out confirmation.')

elif page=='v2 Held-out Results':
    st.title('JointSLA-v2 · independent held-out results')
    generic('Held-out','v2 improves Gold relative to v1 but does not remove the fundamental trade-off. At 2× it loses v1’s high-pressure latency advantage; aggregate SLA remains worse.')
    trajectories('Held-out')
    full=dl.load_csv('Held-out')
    for load in [1.,2.]:
        st.subheader(f'{load:.0f}× · Gold protection versus resource cost')
        grid(dl.filter_frame(full,load_multiplier=load),['Gold_breach_rate','average_replicas','average_vram_residency_gib','total_actions'],prefix=str(load)+'gold')

elif page=='Performance–Resource Trade-off':
    st.title('Observed performance–resource operating points')
    dataset=st.selectbox('Evidence',['Held-out','Pressure'])
    summary=dl.load_csv(dataset)
    loads=sorted(summary.load_multiplier.unique()) if 'load_multiplier' in summary else []
    if loads:
        load=st.select_slider('Offered load',options=loads,value=1. if 1. in loads else loads[0],format_func=lambda x:f'{x:.2f}×')
        points=wide_means(dl.filter_frame(summary,load_multiplier=load))
        for x,y in [('average_replicas','sla_breach_rate'),('average_replicas','Gold_breach_rate'),('average_vram_residency_gib','p95_latency_ms'),('total_actions','sla_breach_rate')]:
            ui.chart(ch.operating_points(points,x,y,presentation),'tradeoff'+x+y)
        ui.evidence(points,rel(dataset,'summary_statistics.csv'),'Source means · pivoted for descriptive scatter')
    ui.notice('Descriptive observed operating points. No mathematical or global Pareto optimality is claimed.')

elif page=='SOVEREIGN / Intent':
    st.title('SOVEREIGN-6G · Pillar 3 and the orchestration boundary')
    st.write('Primary technical fit: Distributed Inference Fabric (§1.2.4.1, proposal printed pp. 28–29). Architectural bridge: Digital Service Orchestrator in Pillar 2 (§1.2.3.1, p. 25). This is a conceptual positioning of the completed study.')
    st.caption('Dashed boxes: SOVEREIGN architectural context. Solid boxes: decision and execution mechanisms implemented in the research simulator.')
    ui.flow(['Business / service intent','Intent management','Structured SLA/resource requirements','Digital Service Orchestrator','JointSLA decision function','Placement / scaling / routing','Simulated edge continuum','Monitoring / SLA assurance'],context=[0,1,3])
    st.write('JointSLA can be positioned as a candidate resource-orchestration decision function within an intent-driven Digital Service Orchestrator.')
    cols=st.columns(2)
    with cols[0]:
        st.subheader('Existing requirements / workload inputs')
        st.write('Tier · deadline · priority · CPU requirement · VRAM requirement · bandwidth · ingress · payload. Model class is derived by the experiment, rather than supplied through an intent API.')
    with cols[1]:
        st.subheader('Not represented')
        st.write('Availability SLA · geographic affinity · data residency · explicit device compatibility · percentile-specific SLOs · full intent translation / negotiation.')
    ui.notice('No full SOVEREIGN integration, TMF-921 implementation or real 6G deployment is claimed. Physical profiling informs simulated execution costs; the multi-node serving system remains simulated.')
    mapping=dl.ROOT/'docs'/'SOVEREIGN_INTENT_MAPPING.md'
    with st.expander('Existing mapping document / Mermaid source'):
        if mapping.exists():st.markdown(mapping.read_text(encoding='utf-8'))
        else:st.info('Panel unavailable — source artifact not found.')
        mermaid=dl.ROOT/'docs'/'figures'/'sov6g_intent_jointsla_architecture.mmd'
        if mermaid.exists():st.code(mermaid.read_text(encoding='utf-8'),language='mermaid')

elif page=='Experiment Timeline':
    st.title('How the research evolved')
    events=[('Synthetic baseline','Baseline'),('30-seed verification','Baseline'),('Joint routing','Synthetic'),('Scalability','Scalability'),('Controller optimization','Controller'),('Strong MJO comparator','MJO'),('Physical hardware profiling','Profiling'),('Hardware-grounded reversal','Hardware'),('Pressure sweep','Pressure'),('D0–D7 decomposition','Mechanism'),('Burst analysis','Mechanism'),('v2 development','Development'),('Freeze','Held-out'),('Held-out seeds 31–60','Held-out'),('Operating-envelope conclusion','Held-out')]
    for i,(title,dataset) in enumerate(events,1):
        with st.container(border=True):
            cols=st.columns([1,8,5])
            cols[0].markdown(f'### {i:02}')
            cols[1].write(title)
            cols[2].caption(rel(dataset,'report.md'))
    st.caption('Sequence of research stages, not a fabricated calendar chronology.')

elif page=='Research Story':
    st.title('What did we learn?')
    for title,text in [
      ('1 · Synthetic','JointSLA produces strong latency and aggregate-SLA benefits in the original regime.'),
      ('2 · Scale','Benefits persist at the three tested synthetic scales.'),
      ('3 · Hardware grounding','Aggregate SLA reverses when execution, VRAM and cold readiness use measured profiles.'),
      ('4 · Mechanism','VRAM, limited warm capacity and recovery interact. Execution alone is insufficient to explain the reversal.'),
      ('5 · Mitigation','Gold protection improves relative to v1, while resource cost and high-pressure latency expose the remaining trade-off.')]:
        with st.container(border=True):st.subheader(title);st.write(text)
    ui.notice('Coupled edge-AI orchestration has an operating envelope, not a universal performance advantage.')
    st.subheader('Negative / mixed findings')
    st.write('Gold remains worse for v1. No statistically supported aggregate-SLA crossover was established. MJO wins LARGE p99. v2 loses v1’s high-pressure latency advantage and moves closer to baseline resource usage.')

elif page=='Data / Reproducibility':
    st.title('Data lineage & reproducibility')
    validation=dl.load_json('Held-out','validation.json')
    cols=st.columns(2)
    cols[0].metric('Held-out exported outcomes verified',f'{validation.get("exported_request_outcomes_verified",0):,}' if validation else ui.UNAVAILABLE)
    cols[1].metric('No lost / duplicate requests',str(validation.get('no_lost_or_duplicate_requests',ui.UNAVAILABLE)))
    report=dl.load_text('Held-out')
    testlines=[line for line in report.splitlines() if '244' in line and ('test' in line.lower() or 'pass' in line.lower())]
    st.write('Frozen report test record: '+(' '.join(testlines) if testlines else ui.UNAVAILABLE))
    st.caption('The frozen research test record is distinct from dashboard verification performed after this interface was created.')
    ui.evidence(checks,'dashboard/data_validation.py','Read-only startup validation')
    dataset=st.selectbox('Evidence directory',list(dl.DIRECTORIES))
    root=dl.discover()[dataset]
    if root.exists():
        sources=[p for p in sorted(root.iterdir()) if p.is_file() and p.suffix in ['.csv','.json','.md','.txt']]
        st.dataframe(pd.DataFrame({'Relative path':[str(p.relative_to(dl.ROOT)) for p in sources],'Bytes':[p.stat().st_size for p in sources]}),hide_index=True,width='stretch')
        chosen=st.selectbox('Inspect small artifact',[p.name for p in sources],key='source-artifact') if sources else None
        if chosen:
            path=root/chosen
            if path.stat().st_size>5_000_000:st.info('Large artifact intentionally not loaded. Inspect locally; request-level rows are excluded from default dashboard loading.')
            elif path.suffix=='.csv':ui.evidence(dl.load_csv(dataset,chosen),rel(dataset,chosen))
            elif path.suffix=='.json':st.json(dl.load_json(dataset,chosen));st.code(rel(dataset,chosen))
            else:st.markdown(dl.load_text(dataset,chosen));st.code(rel(dataset,chosen))
    for name in ['DATA_SOURCES.md','CLAIMS.md','SUPERVISOR_DEMO.md']:
        path=Path(__file__).parent/name
        with st.expander(name):
            if path.exists():st.markdown(path.read_text(encoding='utf-8'))

if learn:
    st.divider();st.subheader('Learning Mode · plain-language explanations');ui.learning()
if presentation:st.caption('Presentation Mode: larger typography and plots; long technical context stays in expanders.')
st.caption(f'View: {page} · '+('Isolated live replay' if page=='Live Experiments' else 'Frozen evidence only'))
