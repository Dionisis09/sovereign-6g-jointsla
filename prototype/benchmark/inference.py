"""Same model/serving core with benchmark metadata and read-only cgroup data."""
import os
from pathlib import Path
from prototype.inference import Inference,TorchModel
from prototype.http import run_server
from prometheus_client.core import CounterMetricFamily,GaugeMetricFamily


def cgroup_snapshot(directory='/sys/fs/cgroup'):
    result={}
    try:
        cpu=dict(line.split() for line in (Path(directory)/'cpu.stat').read_text().splitlines())
        for key in ('usage_usec','nr_periods','nr_throttled','throttled_usec'):
            if key in cpu: result[key]=int(cpu[key])
        result['memory_bytes']=int((Path(directory)/'memory.current').read_text())
        result['cpu_max']=(Path(directory)/'cpu.max').read_text().strip()
    except (OSError,ValueError): pass  # unavailable remains unknown, never zero
    return result


class CgroupCollector:
    def collect(self):
        data=cgroup_snapshot()
        for key,name,divisor in [('usage_usec','cpu_usage_seconds',1e6),('nr_periods','cpu_periods',1),
                                ('nr_throttled','cpu_throttled_periods',1),('throttled_usec','cpu_throttled_seconds',1e6)]:
            if key in data:
                metric=CounterMetricFamily('jointsla_inference_cgroup_'+name,'Container cgroup v2 '+key)
                metric.add_metric([],data[key]/divisor);yield metric
        if 'memory_bytes' in data:
            metric=GaugeMetricFamily('jointsla_inference_cgroup_memory_bytes','Container cgroup v2 memory.current')
            metric.add_metric([],data['memory_bytes']);yield metric


class InstrumentedInference(Inference):
    def __init__(self,model,queue_limit=8):
        super().__init__(model,queue_limit)
        self.metrics.registry.register(CgroupCollector())

    def state(self):
        return dict(super().state(),pod_name=os.getenv('POD_NAME'),pod_uid=os.getenv('POD_UID'),cgroup=cgroup_snapshot())

    def dispatch(self,method,path,body=None):
        if method=='POST' and path=='/benchmark/reset':
            with self.lock:
                if self.admitted or self.draining: return 409,{'error':'Cannot reset active/draining worker'}
                self.cycles.clear();self.completed=0
            return 200,{'reset':True}
        status,result=super().dispatch(method,path,body)
        if method=='POST' and path=='/infer' and isinstance(result,dict):
            result=dict(result,pod_name=os.getenv('POD_NAME'),pod_uid=os.getenv('POD_UID'),
                        request_id=(body or {}).get('request_id'),model_load_seconds=self.model.load_seconds)
        return status,result


if __name__=='__main__':
    model=TorchModel(os.getenv('MODEL','mobilenet'),os.getenv('DEVICE','cpu'),True)
    run_server(InstrumentedInference(model,int(os.getenv('QUEUE_LIMIT','8'))),'0.0.0.0',8080)
