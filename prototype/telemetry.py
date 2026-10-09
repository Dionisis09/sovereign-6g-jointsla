"""Per-process Prometheus registries; request outcomes include rejected traffic."""
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, ProcessCollector, generate_latest

class Metrics:
    def __init__(self, scope):
        self.registry = CollectorRegistry()
        ProcessCollector(namespace=f'jointsla_{scope}', registry=self.registry)
        self.offered = Counter(f'jointsla_{scope}_requests', 'Valid offered requests', ['tier'], registry=self.registry)
        self.outcomes = Counter(f'jointsla_{scope}_outcomes', 'Completed/rejected/failed requests', ['tier', 'outcome'], registry=self.registry)
        self.breaches = Counter(f'jointsla_{scope}_sla_failures', 'Late, rejected or failed requests / all offered', ['tier'], registry=self.registry)
        self.latency = Histogram(f'jointsla_{scope}_latency_seconds', 'Completion latency; failed requests counted separately', ['tier'], buckets=(.005,.01,.025,.05,.1,.2,.5,1,2,5,10,60), registry=self.registry)
        self.queue = Gauge(f'jointsla_{scope}_queue', 'Waiting requests', registry=self.registry)
        self.ready = Gauge(f'jointsla_{scope}_ready_replicas', 'Observed ready replicas', registry=self.registry)
        self.desired = Gauge(f'jointsla_{scope}_desired_replicas', 'Controller target', registry=self.registry)
        self.vram = Gauge(f'jointsla_{scope}_vram_bytes', 'Actual allocated CUDA bytes; zero on CPU', registry=self.registry)
        self.actions = Counter(f'jointsla_{scope}_actions', 'Applied/observed/failed reconciliation actions', ['outcome'], registry=self.registry)
        self.decision_seconds = Gauge(f'jointsla_{scope}_decision_seconds', 'Wall time collecting telemetry and reconciling one step', registry=self.registry)
        self.snapshot_time = Gauge(f'jointsla_{scope}_snapshot_timestamp_seconds', 'Last successfully collected telemetry snapshot', registry=self.registry)
        self.http_inflight = Gauge(f'jointsla_{scope}_http_inflight', 'HTTP infer handlers including response writes', registry=self.registry)
        self.http_rejections = Counter(f'jointsla_{scope}_http_saturation_rejections', 'Connections rejected before parsing at the HTTP handler limit; no tier available', registry=self.registry)
        self.draining = Gauge(f'jointsla_{scope}_draining', 'Readiness withdrawn for shutdown', registry=self.registry)

    def finish(self, tier, elapsed, deadline, outcome='completed'):
        self.outcomes.labels(tier, outcome).inc()
        if outcome == 'completed':
            self.latency.labels(tier).observe(elapsed)
        if outcome != 'completed' or elapsed * 1000 > deadline:
            self.breaches.labels(tier).inc()

    def export(self):
        return generate_latest(self.registry)
