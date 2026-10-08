"""Scope guards and real simulator replay verification."""
import hashlib
import json
from pathlib import Path
import pytest
from dashboard import live_experiments as live

@pytest.mark.parametrize('load,seeds,policies',[
    (3.,[31],['sla_aware']), (1.,[],['sla_aware']),
    (1.,[31,32,33,34],['sla_aware']), (1.,[30],['sla_aware']),
    (1.,[31,31],['sla_aware']), (1.,[31],['unknown']),
    (1.,[31],[]), (1.,[31],['sla_aware','sla_aware'])])
def test_invalid_scope(load,seeds,policies):
    with pytest.raises(ValueError):live.check_selection(load,seeds,policies)

def test_live_output_cannot_target_research(monkeypatch):
    monkeypatch.setattr(live,'LIVE_ROOT',live.ROOT/'results')
    with pytest.raises(ValueError,match='must stay'):live.execute(1.,[31],['sla_aware'])

def test_real_replay_preserves_sources_and_matches_reference():
    config,workload,configs,record,paths=live.restore(2.,31)
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    output,raw,manifest=live.execute(2.,[31],['joint_sla_v2'])
    assert Path(output).is_relative_to(live.LIVE_ROOT)
    assert manifest['all_primary_match']
    assert manifest['checks'][0]['exported_requests_verified']==len(workload.requests)
    assert len(raw)==1
    assert json.loads((Path(output)/'manifest.json').read_text())['paper_statistics_updated'] is False
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
