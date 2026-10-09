"""Read-only presentation of the completed Kubernetes comparison v2 package."""
from pathlib import Path
import hashlib
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dashboard import charts as ch, components as ui

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path('docs/jointsla_kubernetes_v2_final')
ORDER = ['static', 'reactive', 'hpa', 'joint', 'joint_sq', 'reactive_joint']
COLORS = dict(zip(ORDER, ['#8793a8', '#e2a65b', '#659bd8', '#4fc4ad', '#91cdbf', '#c895d5']))
TABLES = ['policy_summary', 'paired_sla_comparisons', 'all_180_runs', 'per_tier_failures',
          'failure_attribution', 'resource_tradeoff', 'ablation_results']


def asset_path(name, root=ROOT):
    """Resolve a publication asset; reject traversal and unrelated project files."""
    folder = (Path(root) / PACKAGE).resolve()
    path = (folder / name).resolve()
    if not path.is_relative_to(folder):
        raise ValueError('Publication asset escapes package')
    return path


@st.cache_data(show_spinner=False)
def _load(folder, stamps):
    folder = Path(folder)
    claims = json.loads((folder / 'canonical_results.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder / 'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    names = ['canonical_results.json'] + [f'tables/{name}.csv' for name in TABLES]
    for name in names:
        path = folder / name
        if path.stat().st_size > 2_000_000:
            raise ValueError('Publication summary exceeds the small-artifact limit')
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files'][name]['sha256']:
            raise ValueError(f'Publication checksum mismatch: {name}')
    tables = {name: pd.read_csv(folder / f'tables/{name}.csv') for name in TABLES}
    if len(tables['all_180_runs']) != claims['trials'] or int(tables['all_180_runs'].offered.sum()) != claims['outcomes']:
        raise ValueError('Publication run counts do not match canonical claims')
    return claims, tables


def load(root=ROOT):
    """Load only verified small aggregates; never raw request tapes or the ZIP."""
    folder = (Path(root) / PACKAGE).resolve()
    names = ['canonical_results.json', 'PACKAGE_MANIFEST.json'] + [f'tables/{name}.csv' for name in TABLES]
    stamps = tuple((name, (folder / name).stat().st_mtime_ns, (folder / name).stat().st_size) for name in names)
    return _load(str(folder), stamps)


def means_chart(claims, metric, title, unit, presentation=False):
    """Bars use existing run means and sample SD, not invented confidence bounds."""
    fig = go.Figure()
    for p in claims['policies']:
        fig.add_trace(go.Bar(name=p['label'], x=[p['label']], y=[p[metric + '_mean']],
            marker_color=COLORS[p['policy']], error_y=dict(type='data', array=[p[metric + '_std']], visible=True),
            hovertemplate='%{x}<br>Mean %{y:.2f}<br>Error bar: sample SD<extra></extra>'))
    if metric == 'sla_failure_percent':
        fig.add_hline(y=15, line_dash='dash', line_color='#e58795', annotation_text='15% target remains unmet')
    fig = ch.finish(fig, title + ' · mean ± sample SD, 30 blocks', unit, presentation)
    fig.update_layout(showlegend=False)
    return fig


def paired_chart(frame, presentation=False):
    fig = go.Figure()
    for r in frame.itertuples():
        effect = r.sla_failure_difference_pp
        fig.add_trace(go.Scatter(x=[effect], y=[r.comparison.replace('joint minus ', 'JointSLA minus ')],
            mode='markers', name=r.comparison, showlegend=False,
            marker=dict(size=11, color='#c895d5' if 'exploratory' in r.role else '#4fc4ad'),
            error_x=dict(type='data', symmetric=False, array=[r.ci95_high_pp-effect], arrayminus=[effect-r.ci95_low_pp]),
            customdata=[[r.ci95_low_pp, r.ci95_high_pp, r.role]],
            hovertemplate='%{y}<br>%{x:.2f} pp<br>95% CI [%{customdata[0]:.2f}, %{customdata[1]:.2f}]<br>%{customdata[2]}<extra></extra>'))
    fig.add_vline(x=0, line_dash='dash', line_color='#a7b5c8')
    fig.update_yaxes(autorange='reversed')
    fig = ch.finish(fig, 'Paired SLA effects · frozen 95% block-bootstrap intervals', 'Comparison', presentation)
    fig.update_xaxes(title='JointSLA minus comparator (percentage points)')
    fig.update_layout(margin=dict(l=275,r=30,t=70,b=65))
    return fig


def cost_chart(claims, runs, presentation=False):
    fig = go.Figure()
    for p in claims['policies']:
        data = runs[runs.policy == p['policy']]
        fig.add_trace(go.Scatter(x=data.target_replica_seconds, y=data.sla_failure_percent,
            name=p['label'], mode='markers', legendgroup=p['policy'],
            marker=dict(color=COLORS[p['policy']], size=7, opacity=.45), customdata=data[['seed']],
            hovertemplate='Seed %{customdata[0]}<br>%{x:.2f} replica s<br>%{y:.2f}% failures<extra>%{fullData.name}</extra>'))
        fig.add_trace(go.Scatter(x=[p['target_replica_seconds_mean']], y=[p['sla_failure_percent_mean']],
            name=p['label']+' mean', legendgroup=p['policy'], showlegend=False, mode='markers',
            marker=dict(color=COLORS[p['policy']], symbol='diamond', size=16),
            hovertemplate='Policy mean<br>%{x:.2f} replica s<br>%{y:.2f}% failures<extra>%{fullData.name}</extra>'))
    fig = ch.finish(fig, 'Performance versus target replica-time · trials and policy means', 'All-offered SLA failures (%)', presentation)
    fig.update_xaxes(title='Target replica-seconds · burst through last response + 20 s')
    fig.update_layout(height=510,margin=dict(l=65,r=225,t=85,b=85),
                      legend=dict(orientation='v',x=1.01,y=1,font_size=13))
    return fig


def headline(claims):
    p = claims['primary']
    cols = st.columns(4)
    cols[0].metric('JointSLA SLA failures', f"{p['joint_sla']:.2f}%")
    cols[1].metric('Reactive SLA failures', f"{p['reactive_sla']:.2f}%")
    cols[2].metric('Paired reduction', f"{p['effect_pp']:.2f} pp")
    cols[3].metric('Additional target replica-time', f"+{p['cost_increase_percent']:.2f}%")
    st.caption(f"Completed Kubernetes comparison v2 · {claims['blocks']} paired blocks · {claims['trials']} trials · {claims['outcomes']:,} offered outcomes. These are archived measurements, not live counters.")


def overview():
    st.subheader('Completed real Kubernetes comparison v2')
    try:
        claims, _ = load()
    except (OSError, ValueError, KeyError) as exc:
        st.warning(f'Final Kubernetes package unavailable: {exc}')
        return
    headline(claims)
    st.write('Significant SLA failure reduction with more target replica-seconds. The below-15% target remains unmet. Simulation findings remain a separate evidence track.')
    st.button('Open Kubernetes comparison v2 and final research package',
              on_click=lambda: st.session_state.update(page='Kubernetes Comparison v2'), key='open-kubernetes-v2')


def downloads():
    st.subheader('Final report paper and presentation')
    for label, name, mime in [
        ('Download full technical report', 'JointSLA_Final_Technical_Report.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        ('Download conference paper draft', 'JointSLA_Conference_Paper_Draft.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        ('Download 14-slide presentation', 'JointSLA_Conference_Presentation.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')]:
        path = asset_path(name)
        if path.exists():
            st.download_button(label, path.read_bytes(), file_name=name, mime=mime, key='publication-'+name)
        else:
            st.warning(label + ': file unavailable')
    st.caption('Word drafts are editable. Slides include native editable charts. Authors, affiliations and venue formatting remain to be supplied before submission.')
    with st.expander('Complete package and preserved raw evidence'):
        st.write('The complete ZIP includes reports, slides, seven PNG/vector-PDF figures, CSVs, source scripts and the checksummed v2 raw evidence archive. Older results remain preserved in the project with a separate hash seal.')
        if st.checkbox('Prepare complete package download (about 49 MB)', key='prepare-publication-zip'):
            package = ROOT/'docs/JointSLA_Final_Research_Package_v2.zip'
            if package.exists():
                st.download_button('Download complete research package ZIP', package.read_bytes(), file_name=package.name,
                                   mime='application/zip', key='publication-zip')
            else:
                st.info('ZIP unavailable; the individual artifacts remain available above.')
        st.code('docs/jointsla_kubernetes_v2_final/\n.venv/Scripts/python.exe docs/jointsla_kubernetes_v2_final/verify_preservation.py --originals\n.venv/Scripts/python.exe docs/jointsla_kubernetes_v2_final/validate_publication.py', language='powershell')
    figures = sorted(asset_path('figures').glob('*.png'))
    if figures:
        chosen = st.selectbox('Verified publication figure', figures, format_func=lambda p:p.stem.replace('_',' '), key='publication-figure')
        st.image(str(chosen), width='stretch')
        for suffix, mime in [('.png','image/png'),('.pdf','application/pdf')]:
            path = chosen.with_suffix(suffix)
            if path.exists():
                st.download_button('Download figure '+suffix.upper()[1:],path.read_bytes(),file_name=path.name,mime=mime,key='figure-'+suffix)
    for name, label in [('JointSLA_Final_Technical_Report.md','Read the full technical report'),
                        ('JointSLA_Conference_Paper_Draft.md','Read the paper draft'),
                        ('FINAL_CONSISTENCY_CHECK.md','Final consistency and preservation check')]:
        with st.expander(label):
            path = asset_path(name)
            if path.exists():st.markdown(path.read_text(encoding='utf-8'))


def render(presentation=False):
    st.title('JointSLA · completed Kubernetes comparison v2')
    try:
        claims, tables = load()
    except (OSError, ValueError, KeyError) as exc:
        st.error(f'Cannot display verified publication evidence: {exc}')
        return
    headline(claims)
    ui.notice('JointSLA significantly reduces SLA failures against the registered core baselines, while using more target replica-seconds. Greater resource efficiency is not established.')
    st.write('Real pretrained MobileNetV3-Large inference on CPU · one physical host and one virtual Kubernetes node · 30 paired blocks, seeds 1001–1030 · six policies. The paced 120 requests/s burst is distinct from simulator traffic.')
    tabs = st.tabs(['Policy results', 'Paired statistics and ablations', 'Performance and resource cost', 'Reports and figures'])
    with tabs[0]:
        for metric,title,unit in [('sla_failure_percent','All-offered SLA failures','Failures (%)'),
                                  ('p95_completed_latency_ms','Completed-request p95','Latency (ms)'),
                                  ('rejection_percent','HTTP 503 rejection rate','All-offered HTTP 503 (%)')]:
            ui.chart(means_chart(claims,metric,title,unit,presentation),'kubernetes-'+metric)
        st.caption('Error bars are sample standard deviations over 30 run-level values. SLA failures count every non-200 outcome and late completion. Completed p95 excludes rejected requests; no confirmatory p95 improvement is claimed.')
        ui.evidence(tables['policy_summary'],'docs/jointsla_kubernetes_v2_final/tables/policy_summary.csv','All policy metrics and sample SD / CSV')
        st.subheader('Gold Silver and Bronze failures')
        tier = tables['per_tier_failures'].copy()
        labels = {p['policy']:p['label'] for p in claims['policies']}
        fig = go.Figure()
        for name,color in [('Gold','#d8b461'),('Silver','#92adcc'),('Bronze','#c38e69')]:
            data = tier[tier.tier==name].set_index('policy').loc[ORDER]
            fig.add_trace(go.Bar(name=name,x=[labels[a] for a in ORDER],y=data.sla_failure_percent,
                                error_y=dict(type='data',array=data.run_std_percent),marker_color=color))
        ui.chart(ch.finish(fig,'Tier SLA failures · mean ± sample SD','Failures (%)',presentation),'kubernetes-tiers')
        st.write('Gold remains difficult: JointSLA Gold failures are 79.63%. Shared FIFO admission and 200/400/800 ms deadlines do not establish robust Gold protection.')
        ui.evidence(tier,'docs/jointsla_kubernetes_v2_final/tables/per_tier_failures.csv','Per-tier offered and failed counts / CSV')
        ui.evidence(tables['failure_attribution'],'docs/jointsla_kubernetes_v2_final/tables/failure_attribution.csv','Explicit failure categories / CSV')
    with tabs[1]:
        ui.chart(paired_chart(tables['paired_sla_comparisons'],presentation),'kubernetes-paired')
        st.write('Primary comparison: JointSLA versus reactive. 95% percentile paired block-bootstrap intervals use 10,000 resamples, seed 39108. Two-sided Wilcoxon uses Pratt zeros. Holm corrects the three core comparisons; the two mechanism arms have raw exploratory p-values.')
        ui.evidence(tables['paired_sla_comparisons'],'docs/jointsla_kubernetes_v2_final/tables/paired_sla_comparisons.csv','Full-precision intervals corrected p-values and roles / CSV')
        st.info('Router ablation: −2.10 pp, 95% CI [−4.84, +0.73], raw p = 0.158844. The interval crosses zero. A separate routing gain is not established.')
        st.write('Scaling ablation: −11.05 pp, CI [−13.73, −8.30], raw exploratory p = 3.147870e−07. Feedback changes realized replica trajectories, preventing unique causal attribution.')
        ui.evidence(tables['ablation_results'],'docs/jointsla_kubernetes_v2_final/tables/ablation_results.csv','Registered exploratory ablations / CSV')
    with tabs[2]:
        ui.chart(cost_chart(claims,tables['all_180_runs'],presentation),'kubernetes-cost-scatter')
        ui.chart(means_chart(claims,'target_replica_seconds','Target replica-time','Replica-seconds',presentation),'kubernetes-replica-cost')
        st.write('JointSLA uses 103.45 target replica-seconds versus reactive’s 65.12: +58.84%. The additional cost is 38.32 replica-seconds, with descriptive paired CI [33.37, 43.38]. This is a ratio of policy means, not a mean of individual cost ratios.')
        st.caption('Target replica-time includes pending desired replicas from burst start through the last response plus 20 s. It is not billing, energy or actual CPU usage. Resource intervals use descriptive bootstrap seed 271830. There is no static-four or matched-budget comparator.')
        ui.evidence(tables['resource_tradeoff'],'docs/jointsla_kubernetes_v2_final/tables/resource_tradeoff.csv','Resource trade-off and descriptive intervals / CSV')
        ui.evidence(tables['all_180_runs'],'docs/jointsla_kubernetes_v2_final/tables/all_180_runs.csv','Explore all 180 completed runs / CSV')
    with tabs[3]:downloads()
    with st.expander('Protocol limitations and historical evidence'):
        st.write('Fresh policy processes, two ready idle replicas, eight direct preconditioning requests/backend, 35 s settle, balanced randomized serial order and fixed 20 s follow-up. Native HPA keeps real default timings. A 91.65-minute user pause affected one exploratory preparation interval before its burst; all trials remain retained.')
        st.write('The historical 1,420-request audit and 38.83%/47.27% bursts are excluded from v2. The held-out simulator remains separate. Physical GPU, multi-edge deployment, inference accuracy and production high availability are not established.')
        st.write('The final package recorded 330 passing tests and verified 1,480 archived v2 files plus 24,364 historical result files. These are dated validation records, not live counters. Local operational completeness does not imply the below-15% SLA goal was met.')
        st.link_button('Open live infrastructure Grafana', 'http://127.0.0.1:3001/d/jointsla-runtime')
        st.caption('Grafana requires the local Kubernetes monitoring stack to be running. Its time range and live counters do not change these archived comparison results.')
