"""Interactive live execution view, distinct from frozen evidence."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.live_experiments import execute,POLICIES,LIVE_ROOT,PRIMARY
from dashboard.metrics import spec,policy_label
from dashboard import charts as ch,components as ui

def render(presentation=False):
    st.title('Live experiments · execute and verify')
    st.write('Run the unchanged SLA-aware, JointSLA-v1 and JointSLA-v2 engines against archived held-out input tapes. These are fresh simulations, not animations of stored results. Outputs stay separate from the paper evidence.')
    ui.notice('Live replay validates repeatability for the selected cases. It does not replace the frozen 30-seed statistical analysis or establish universal superiority.')
    with st.form('live-run'):
        columns=st.columns(3)
        with columns[0]:load=st.selectbox('Live scenario',[1.,2.],format_func=lambda x:f'{x:.0f}× · hardware-grounded · 10 nodes / 40 services')
        with columns[1]:seeds=st.multiselect('Archived seeds (maximum 3)',list(range(31,61)),default=[31])
        with columns[2]:policies=st.multiselect('Policies to execute',POLICIES,default=list(POLICIES),format_func=policy_label)
        submitted=st.form_submit_button('Run live paired experiment',type='primary')
    if submitted:
        progress=st.progress(0.,text='Starting isolated replay…')
        try:
            with st.spinner('Executing real simulator policies and auditing request outcomes…'):
                st.session_state['live_result']=execute(load,seeds,policies,lambda fraction,text:progress.progress(fraction,text=text))
            st.success('Simulation complete. Live outputs saved independently of frozen research artifacts.')
        except Exception as error:st.error(f'Live run stopped: {error}')
    if 'live_result' not in st.session_state:return
    output,raw,manifest=st.session_state['live_result']
    st.subheader('Fresh execution results')
    st.caption(f'Run {manifest["run_id"]} · {manifest["load_multiplier"]:.0f}× · {len(manifest["seeds"])} selected seed(s)')
    if manifest['all_primary_match']:st.success('All 10 checked scientific metrics match the frozen values for these same seeds and policies.')
    else:st.warning('Some metrics differ from the frozen reference. Inspect the comparison; frozen results were not changed.')
    shown=raw[['seed','policy',*PRIMARY,'average_vram_residency_gib']].copy()
    for metric in shown:
        if metric in PRIMARY:shown[metric]=shown[metric]*spec(metric)[2]
    st.dataframe(shown,width='stretch',hide_index=True)
    st.caption('Breach columns are percent; latency is ms. These are individual-run metrics, not 30-seed confidence intervals. Execution-time measurements can vary with laptop load.')
    for metric in ['sla_breach_rate','p95_latency_ms','Gold_breach_rate','average_replicas']:
        data=raw.copy();data['Policy']=data.policy.map(policy_label);data['Value']=data[metric]*spec(metric)[2];data['Seed']=data.seed.astype(str)
        fig=px.bar(data,x='Policy',y='Value',color='Policy',facet_col='Seed',color_discrete_map=ch.COLORS)
        ui.chart(ch.finish(fig,'Live · '+spec(metric)[0],spec(metric)[1],presentation),'live'+metric)
    cols=st.columns(2)
    with cols[0]:seed=st.selectbox('Live trajectory seed',manifest['seeds'])
    with cols[1]:policy=st.selectbox('Live node-view policy',manifest['policies'],format_func=policy_label)
    trajectories=[]
    for p in manifest['policies']:
        frame=pd.read_csv(Path(output)/f'seed_{seed:03d}'/p/'slot_trajectories.csv.gz')
        trajectories.append(frame.assign(Policy=policy_label(p)))
    slots=pd.concat(trajectories,ignore_index=True)
    for metric,title,unit in [('latency_ms','Live request-cohort latency','ms'),('cumulative_sla_breach_pct','Live cumulative arrival-cohort SLA failures','%'),('waiting_requests','Live waiting queue','requests')]:
        ui.chart(ch.finish(px.line(slots,x='slot',y=metric,color='Policy',color_discrete_map=ch.COLORS),title,unit,presentation),'live-trajectory'+metric)
    nodes=pd.read_csv(Path(output)/f'seed_{seed:03d}'/policy/'node_trajectories.csv.gz')
    matrix=nodes.pivot(index='node',columns='slot',values='gpu_utilization')*100
    ui.chart(ch.finish(px.imshow(matrix,aspect='auto',zmin=0,zmax=100,color_continuous_scale=['#111d2d','#55b7ec'],labels={'x':'Slot','y':'Node','color':'%'}),'Live GPU utilization · '+policy_label(policy),'Node',presentation),'livegpu')
    st.download_button('Download live metrics CSV',raw.to_csv(index=False).encode('utf-8'),file_name='live_results.csv',mime='text/csv')
    st.download_button('Download live audit manifest',(Path(output)/'manifest.json').read_bytes(),file_name='live_manifest.json',mime='application/json')
    with st.expander('Reproducibility audit / frozen comparison / output location'):
        st.json(manifest)
        st.dataframe(pd.read_csv(Path(output)/'frozen_comparison.csv'),hide_index=True,width='stretch')
        st.code(str(Path(output).relative_to(LIVE_ROOT.parent.parent.parent)),language=None)
