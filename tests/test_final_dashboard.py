"""Read-only observability failure/recovery and metric definition boundaries."""
from types import SimpleNamespace as N
from prometheus_client import CollectorRegistry, generate_latest
from prototype.kubernetes.observability import KubernetesSnapshotCollector
from prototype.kubernetes.final_dashboard import build_dashboard


def adapter():
    container=N(name='gateway',restart_count=2,state=N(waiting=None),
                last_state=N(terminated=N(reason='Error')))
    pod=N(metadata=N(name='gateway-a',uid='uid-a',deletion_timestamp=None),
          status=N(conditions=[N(type='Ready',status='True')],container_statuses=[container]))
    return N(namespace='jointsla-prototype',deployment='inference',
             core=N(list_namespaced_pod=lambda *a,**kw:N(items=[pod])),
             apps=N(read_namespaced_deployment_scale=lambda *a,**kw:N(spec=N(replicas=2)))),pod


def test_kubernetes_observer_is_cached_and_does_not_query_during_scrapes():
    source,pod=adapter()
    collector=KubernetesSnapshotCollector(source)
    registry=CollectorRegistry();registry.register(collector)
    assert collector.snapshot is None  # registration has no API side effects
    assert collector.refresh()
    def fail(*a,**kw): raise AssertionError('API call during scrape')
    source.core.list_namespaced_pod=fail
    output=generate_latest(registry).decode()
    assert 'jointsla_kubernetes_deployment_replicas 2.0' in output
    assert 'jointsla_kubernetes_container_restarts' in output
    assert 'reason="Error"' in output
    assert 'uid="uid-a"' in output


def test_kubernetes_observer_failure_preserves_stale_data_and_recovers():
    source,pod=adapter();collector=KubernetesSnapshotCollector(source)
    assert collector.refresh();old=collector.snapshot
    original=source.core.list_namespaced_pod
    def fail(*a,**kw): raise OSError('API unavailable')
    source.core.list_namespaced_pod=fail
    assert not collector.refresh()
    assert not collector.healthy and collector.snapshot is old
    source.core.list_namespaced_pod=original
    pod.metadata.uid='replacement';pod.metadata.deletion_timestamp='now'
    assert collector.refresh() and collector.healthy
    assert collector.snapshot[2][0][1]=='replacement'
    assert collector.snapshot[2][0][2] is False  # terminating Ready pod is excluded
    assert collector.snapshot[2][0][3] is True


def test_kubernetes_observer_reports_unknown_before_first_success():
    source,pod=adapter();collector=KubernetesSnapshotCollector(source)
    registry=CollectorRegistry();registry.register(collector)
    output=generate_latest(registry).decode()
    assert 'jointsla_kubernetes_observer_up 0.0' in output
    assert 'jointsla_kubernetes_deployment_replicas' not in output  # unknown != zero


def test_final_dashboard_keeps_audit_snapshot_separate_from_live_denominators():
    dashboard=build_dashboard()
    assert dashboard['uid']=='jointsla-runtime'
    audit=dashboard['panels'][0]
    assert audit['type']=='text' and '306 tests passed' in audit['options']['content']
    assert '1,420' in audit['options']['content'] and 'not live counters' in audit['options']['content']
    rate=next(p for p in dashboard['panels'] if p['title']=='SLA failures % (1m)')
    assert 'outcomes_total' in rate['targets'][0]['expr'] and '> 0' in rate['targets'][0]['expr']
    assert 'clamp_min' not in rate['targets'][0]['expr']
    assert 'or (0 *' in rate['targets'][0]['expr']  # lazy failure counter + real completions
    completed=next(p for p in dashboard['panels'] if p['title']=='Completed requests')
    assert 'increase' not in completed['targets'][0]['expr']
    assert 'reset on restart' in completed['description']
    latency=next(p for p in dashboard['panels'] if p['title']=='Completed latency · mean and p95')
    assert latency['fieldConfig']['defaults']['unit']=='ms'
    assert 'histogram_quantile' in latency['targets'][1]['expr']
    assert '38.83%' in dashboard['panels'][-1]['options']['content']
    assert '47.27%' in dashboard['panels'][-1]['options']['content']
