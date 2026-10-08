"""Read-only loaders, actual frozen evidence, and source integrity checks."""
import ast
from pathlib import Path
import hashlib
import pandas as pd
import pytest
from dashboard import data_loader as dl
from dashboard.data_validation import validate

def test_actual_path_discovery():
    paths=dl.discover()
    assert paths['Held-out']==dl.ROOT/'results'/'jointsla_v2_heldout'
    assert all(p.is_dir() for p in paths.values())

def test_loader_missing_fallback(tmp_path):
    assert dl.load_csv('Held-out',root=tmp_path).empty
    assert dl.load_json('Held-out','validation.json',tmp_path)=={}
    assert dl.load_text('Held-out',root=tmp_path)==''

def test_path_escape_rejected():
    with pytest.raises(ValueError):dl.source_path('Held-out','../../outside.csv')

def test_readonly_loader_content_and_copy():
    path=dl.source_path('Held-out','summary_statistics.csv')
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    frame=dl.load_csv('Held-out')
    assert {'policy','metric','mean','ci95_lower','ci95_upper'}.issubset(frame)
    frame.loc[0,'mean']=-999
    assert dl.load_csv('Held-out').iloc[0]['mean']!=-999
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before

def test_paired_identifiers_actual_heldout():
    frame=dl.raw('Held-out')
    assert frame.groupby(['load_multiplier','seed']).traffic_hash.nunique().eq(1).all()
    assert frame.groupby(['load_multiplier','policy']).seed.nunique().eq(30).all()

def test_loader_does_not_load_huge_outcomes(tmp_path):
    path=dl.source_path('Held-out','request_outcomes.csv',tmp_path)
    path.parent.mkdir(parents=True)
    with path.open('wb') as handle:handle.truncate(15_000_001)
    with pytest.raises(ValueError,match='Large'):dl.load_csv('Held-out','request_outcomes.csv',tmp_path)

def test_validation_can_warn_for_missing_artifacts(tmp_path):
    checks=validate(tmp_path)
    assert not checks.passed.all()
    assert 'directory' in checks.check.values

def test_no_dashboard_writes_or_scientific_imports():
    # The runtime package is forbidden to import experiment implementations or use
    # direct filesystem writers. Browser CSV downloads return bytes only.
    forbidden={'write_text','write_bytes','mkdir','rename','unlink','dump','save','savefig','to_file'}
    for path in (dl.ROOT/'dashboard').glob('*.py'):
        if path.name=='live_experiments.py':continue # Explicitly authorized isolated replay writer.
        tree=ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and (isinstance(node.func,ast.Name) and node.func.id=='open' or isinstance(node.func,ast.Attribute) and node.func.attr=='open'):
                modes=[kw.value for kw in node.keywords if kw.arg=='mode']
                if len(node.args)>1:modes.append(node.args[1])
                assert all(isinstance(m,ast.Constant) and not any(c in str(m.value) for c in 'wax+') for m in modes)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                assert node.func.attr not in forbidden,(path,node.func.attr)
                if node.func.attr=='to_csv':
                    assert not node.args,(path,'CSV writes must be bytes-returning, no path target')
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[node.module] if isinstance(node,ast.ImportFrom) else [x.name for x in node.names]
                assert not any(n and n.split('.')[0] in {'dynamic_placement','joint_routing','joint_sla_v2','hardware_pressure','hardware_grounded','paper_evaluation','scalability','strong_baseline','controller_optimization'} for n in names)

def test_frozen_known_heldout_values_are_loaded():
    data=dl.filter_frame(dl.load_csv('Held-out'),load_multiplier=1.,policy='sla_aware',metric='sla_breach_rate')
    assert data.iloc[0]['mean']*100==pytest.approx(14.98,abs=.01)

def test_chart_values_and_ci_match_frozen_rows():
    from dashboard.charts import metric_chart
    summary=dl.filter_frame(dl.load_csv('Held-out'),load_multiplier=1.,metric='sla_breach_rate')
    fig=metric_chart(summary,'sla_breach_rate')
    for row,trace in zip(summary.itertuples(),fig.data):
        assert float(trace.y[0])==pytest.approx(row.mean*100)
        assert float(trace.error_y.array[0])==pytest.approx((row.ci95_upper-row.mean)*100)
        assert float(trace.error_y.arrayminus[0])==pytest.approx((row.mean-row.ci95_lower)*100)
