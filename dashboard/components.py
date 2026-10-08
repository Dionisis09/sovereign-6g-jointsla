"""Source inspection, metrics and learning aids."""
import html
import pandas as pd
import streamlit as st
from dashboard.metrics import spec, policy_label, ci

UNAVAILABLE='Not available in frozen results'
HELP={
 'What is SLA?':'A service deadline or promise. Here, requests are checked against their individual end-to-end latency deadline.',
 'What is p95?':'The latency below which 95% of requests in one run finish. Our charts average the per-run p95 across seeds.',
 'What is a replica?':'One deployed instance of a service pipeline. Multiple replicas can share the work.',
 'What is VRAM?':'GPU memory occupied by models and tensors. Memory capacity and GPU execution capacity are different constraints.',
 'What is cold start?':'The time a new replica needs to load and become ready. It cannot immediately absorb a burst.',
 'What is warm capacity?':'Replicas already ready to process requests when traffic arrives.',
 'What does paired seed mean?':'Competing policies receive the same workload and arrivals for each seed. Their difference is compared within that pair.',
 'What is a 95% CI?':'An uncertainty interval from the frozen statistical analysis. It is neither the range of all requests nor a guarantee for future traffic.',
 'What is Wilcoxon?':'A paired statistical test that uses the ranks of nonzero differences rather than assuming normally distributed differences.',
 'What is Holm correction?':'An adjustment for testing multiple comparisons, reducing the risk of false positive claims.',
 'What does held-out validation mean?':'Seeds not used to design or select the candidate. v2 was frozen before evaluation on seeds 31–60.',
}

def notice(text):st.markdown('<div class="notice">'+html.escape(text)+'</div>',unsafe_allow_html=True)

def flow(steps, context=()):
    boxes=[]
    for i,s in enumerate(steps):
        boxes.append('<span class="step '+('boundary' if i in context else '')+'">'+html.escape(s)+'</span>')
    st.markdown('<div class="flow">'+'<span>→</span>'.join(boxes)+'</div>',unsafe_allow_html=True)

def learning():
    for question,answer in HELP.items():
        with st.expander(question):st.write(answer)

def cards(summary, metrics):
    if summary.empty:
        st.info('Panel unavailable — source artifact not found.');return
    policies=list(summary.policy.unique()) if 'policy' in summary else []
    for metric in metrics:
        label,unit,_,helptext=spec(metric)
        cols=st.columns(max(1,len(policies)))
        for col,policy in zip(cols,policies):
            rows=summary[(summary.policy==policy)&(summary.metric==metric)]
            with col:
                if len(rows)!=1:st.metric(policy_label(policy)+' · '+label,UNAVAILABLE,help=helptext);continue
                row=rows.iloc[0];value=row['mean']*spec(metric)[2]
                st.metric(policy_label(policy)+' · '+label,f'{value:,.2f} {unit}',help=helptext)
                low,high=ci(row,metric)
                if low is not None:st.caption(f'95% CI {low:,.2f}–{high:,.2f} · n={int(row["n"])} seeds')

def evidence(frame, source, title='Source data / CSV export'):
    with st.expander(title):
        st.code(source,language=None)
        if frame.empty:st.info('Panel unavailable — source artifact not found.');return
        st.dataframe(frame,width='stretch',hide_index=True)
        st.download_button('Download displayed rows as CSV',frame.to_csv(index=False).encode('utf-8'),
            file_name=source.replace('/','_')+'.csv',mime='text/csv',key=source+title)

def chart(fig, key):
    if fig is None:st.info(UNAVAILABLE)
    else:st.plotly_chart(fig,width='stretch',key=key,config={'displaylogo':False,'toImageButtonOptions':{'format':'png','scale':2}})

def statistics(frame,source):
    evidence(frame,source,'Statistical details · frozen analysis')
