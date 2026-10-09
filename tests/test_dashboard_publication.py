"""Final research dashboard boundaries and scientific display semantics."""
from pathlib import Path
import hashlib
import pytest
from dashboard import publication as pub


def test_publication_reads_verified_small_aggregates_without_modifying_sources():
    path=pub.asset_path('canonical_results.json');before=hashlib.sha256(path.read_bytes()).hexdigest()
    c,t=pub.load()
    assert c['trials']==180 and c['outcomes']==230400
    assert len(t['all_180_runs'])==180
    assert t['all_180_runs'].groupby('policy').size().eq(30).all()
    assert sum(t['all_180_runs'].offered)==230400
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_publication_paths_and_missing_evidence_do_not_escape_or_invent_results(tmp_path):
    with pytest.raises(ValueError,match='escapes'):pub.asset_path('../../outside.csv')
    with pytest.raises(FileNotFoundError):pub.load(tmp_path)


def test_bar_sd_and_paired_ci_are_distinct_and_match_frozen_data():
    c,t=pub.load()
    fig=pub.means_chart(c,'sla_failure_percent','SLA','%')
    for trace,p in zip(fig.data,c['policies']):
        assert trace.y[0]==p['sla_failure_percent_mean']
        assert trace.error_y.array[0]==p['sla_failure_percent_std']
    paired=pub.paired_chart(t['paired_sla_comparisons'])
    for trace,r in zip(paired.data,t['paired_sla_comparisons'].itertuples()):
        assert trace.x[0]==r.sla_failure_difference_pp
        assert trace.error_x.array[0]==pytest.approx(r.ci95_high_pp-r.sla_failure_difference_pp)
        assert trace.error_x.arrayminus[0]==pytest.approx(r.sla_failure_difference_pp-r.ci95_low_pp)
    assert paired.data[3].error_x.array[0]>abs(paired.data[3].x[0])  # Router CI crosses zero.


def test_checksum_mismatch_is_visible_instead_of_displaying_changed_statistics(tmp_path):
    import shutil
    folder=tmp_path/pub.PACKAGE
    folder.mkdir(parents=True)
    for name in ['canonical_results.json','PACKAGE_MANIFEST.json']+[f'tables/{n}.csv' for n in pub.TABLES]:
        target=folder/name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(pub.asset_path(name),target)
    with (folder/'tables/policy_summary.csv').open('a') as f:f.write('\nchanged')
    with pytest.raises(ValueError,match='checksum mismatch'):pub.load(tmp_path)


def test_kubernetes_page_and_overview_link_render_without_running_an_experiment():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(pub.ROOT/'dashboard/app.py'),default_timeout=30)
    app.run()
    assert not app.exception
    app.button(key='open-kubernetes-v2').click().run()
    assert not app.exception
    assert app.radio(key='page').value=='Kubernetes Comparison v2'
    assert any(m.value=='49.89%' for m in app.metric)
    assert any(m.value=='+58.84%' for m in app.metric)
    assert len(app.get('plotly_chart'))==7
    assert len(app.get('download_button'))>=5
