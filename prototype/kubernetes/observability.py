"""Read-only Kubernetes snapshots, outside the JointSLA decision path.

The exporter observes pod readiness/restarts and the actual Deployment target.
It does not classify scale-in or pod deletion as a crash, or mutate resources.
Scrapes serve a cached snapshot; bounded API polling runs on a separate thread.
"""
import threading
import time
from prometheus_client.core import GaugeMetricFamily


class KubernetesSnapshotCollector:
    def __init__(self, adapter):
        self.adapter = adapter
        self.lock = threading.Lock()
        self.snapshot = None
        self.healthy = False

    def describe(self):
        return []  # Registration must not call the Kubernetes API.

    def refresh(self):
        try:
            pods = self.adapter.core.list_namespaced_pod(
                self.adapter.namespace, _request_timeout=(2, 3)).items
            scale = self.adapter.apps.read_namespaced_deployment_scale(
                self.adapter.deployment, self.adapter.namespace,
                _request_timeout=(2, 3))
            rows = []
            for pod in pods:
                ready = any(c.type == 'Ready' and c.status == 'True'
                            for c in (pod.status.conditions or []))
                deleting = bool(pod.metadata.deletion_timestamp)
                containers = []
                for c in (pod.status.container_statuses or []):
                    waiting = c.state.waiting if c.state else None
                    terminated = c.last_state.terminated if c.last_state else None
                    containers.append((c.name, c.restart_count or 0,
                                       waiting.reason if waiting else '',
                                       terminated.reason if terminated else ''))
                rows.append((pod.metadata.name, pod.metadata.uid,
                             ready and not deleting, deleting, containers))
            snapshot = (time.time(), scale.spec.replicas, rows)
        except Exception:
            with self.lock:
                self.healthy = False
            return False
        with self.lock:
            self.snapshot = snapshot
            self.healthy = True
        return True

    def run(self, stop, interval=5):
        while not stop.is_set():
            self.refresh()
            stop.wait(interval)

    def collect(self):
        with self.lock:
            snapshot, healthy = self.snapshot, self.healthy
        health = GaugeMetricFamily('jointsla_kubernetes_observer_up', 'Last API poll succeeded')
        health.add_metric([], int(healthy))
        yield health
        if snapshot is None:
            return
        timestamp, target, rows = snapshot
        stamp = GaugeMetricFamily('jointsla_kubernetes_snapshot_timestamp_seconds', 'Last successful API snapshot')
        stamp.add_metric([], timestamp)
        yield stamp
        desired = GaugeMetricFamily('jointsla_kubernetes_deployment_replicas', 'Actual inference Deployment spec.replicas')
        desired.add_metric([], target)
        yield desired
        labels = ['namespace', 'pod', 'uid']
        ready = GaugeMetricFamily('jointsla_kubernetes_pod_ready', 'Ready and not terminating', labels=labels)
        deleting = GaugeMetricFamily('jointsla_kubernetes_pod_terminating', 'Deletion timestamp present', labels=labels)
        restarts = GaugeMetricFamily('jointsla_kubernetes_container_restarts', 'Kubernetes restartCount for this pod UID', labels=labels + ['container'])
        waiting = GaugeMetricFamily('jointsla_kubernetes_container_waiting', 'Current waiting reason', labels=labels + ['container', 'reason'])
        terminated = GaugeMetricFamily('jointsla_kubernetes_container_last_termination', 'Last termination reason; historical until next restart', labels=labels + ['container', 'reason'])
        for name, uid, is_ready, is_deleting, containers in rows:
            values = [self.adapter.namespace, name, uid]
            ready.add_metric(values, int(is_ready))
            deleting.add_metric(values, int(is_deleting))
            for container, count, wait_reason, last_reason in containers:
                restarts.add_metric(values + [container], count)
                if wait_reason:
                    waiting.add_metric(values + [container, wait_reason], 1)
                if last_reason:
                    terminated.add_metric(values + [container, last_reason], 1)
        yield ready
        yield deleting
        yield restarts
        yield waiting
        yield terminated
