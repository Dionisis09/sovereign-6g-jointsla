"""Unit conversion and frozen paired-schema regression checks."""
import pandas as pd
import pytest
from dashboard.metrics import display_value,ci,policy_label,paired_table,paired_lookup,wide_means

def test_fraction_percent_and_existing_percent():
    assert display_value(.1498,'sla_breach_rate')==pytest.approx(14.98)
    assert display_value(14.98,'sla_breach_pct')==pytest.approx(14.98)

def test_no_latency_or_gib_conversion():
    assert display_value(189.73,'p95_latency_ms')==189.73
    assert display_value(1.75,'average_vram_residency_gib')==1.75

def test_ci_is_frozen_asymmetric_and_missing():
    assert ci({'ci95_lower':.1,'ci95_upper':.23},'sla_breach_rate')==(10.,23.)
    assert ci({},'sla_breach_rate')==(None,None)

@pytest.mark.parametrize('source,label',[('joint_sla','JointSLA-v1'),('joint_sla_v1','JointSLA-v1'),('joint_sla_v2','JointSLA-v2'),('sla_aware','SLA-aware'),('new_policy','new_policy')])
def test_policy_labels(source,label):assert policy_label(source)==label

def test_original_paired_schema_preserves_b_minus_a():
    frame=pd.DataFrame([dict(policy_A='joint_sla',policy_B='sla_aware',metric='sla_breach_rate',absolute_difference=.06,difference_ci95_lower=.04,difference_ci95_upper=.08)])
    row=paired_table(frame).iloc[0]
    assert row.delta==.06
    assert row.comparison=='SLA-aware − JointSLA-v1'
    assert row.lower==.04

def test_v2_schema_lookup():
    frame=pd.DataFrame([dict(load_multiplier=1.,comparator='joint_sla_v1',metric='sla_breach_rate',delta_v2_minus_comparator=-.03,delta_ci95_lower=-.04,delta_ci95_upper=-.02)])
    row=paired_lookup(frame,'sla_breach_rate',load_multiplier=1.).iloc[0]
    assert row.delta==-.03 and row.comparison=='JointSLA-v2 − JointSLA-v1'
    assert paired_lookup(frame,'sla_breach_rate',load_multiplier=2.).empty

def test_hardware_schema_no_invented_ci():
    row=paired_table(pd.DataFrame([dict(metric='sla_breach_rate',delta_joint_minus_sla=.1)])).iloc[0]
    assert row.delta==.1 and pd.isna(row.lower)

def test_pivot_does_not_average_different_scopes():
    frame=pd.DataFrame([dict(load_multiplier=load,policy='sla_aware',metric='sla_breach_rate',mean=value) for load,value in [(1.,.1),(2.,.4)]])
    result=wide_means(frame)
    assert result.sla_breach_rate.tolist()==[.1,.4]
