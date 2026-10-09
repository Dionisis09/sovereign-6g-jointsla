"""Real serial MobileNetV3/ResNet50 inference with bounded waiting admission."""
import argparse
import base64
from collections import deque
import io
import os
import threading
import time
from prototype.http import run_server, request_parameters
from prototype.telemetry import Metrics

class TorchModel:
    def __init__(self, name='mobilenet', device='cpu', pretrained=True):
        import torch
        from torchvision import models
        start = time.perf_counter()
        torch.set_num_threads(int(os.getenv('TORCH_NUM_THREADS', '2')))
        torch.manual_seed(0)
        weights = {'mobilenet': models.MobileNet_V3_Large_Weights.IMAGENET1K_V2,
                   'resnet50': models.ResNet50_Weights.IMAGENET1K_V2}[name]
        constructor = {'mobilenet': models.mobilenet_v3_large, 'resnet50': models.resnet50}[name]
        self.torch, self.weights, self.device, self.pretrained = torch, weights, device, pretrained
        self.model = constructor(weights=weights if pretrained else None).to(device).eval()
        self.transform = weights.transforms()
        with torch.inference_mode():
            self.model(torch.zeros(1,3,224,224,device=device))
        if device.startswith('cuda'): torch.cuda.synchronize()
        self.load_seconds = time.perf_counter()-start

    def predict(self, body):
        from PIL import Image
        if 'image_base64' in body:
            raw = base64.b64decode(body['image_base64'], validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height > 16_000_000: raise ValueError('Image too large')
                tensor = self.transform(image.convert('RGB')).unsqueeze(0)
            kind = 'image'
        else:
            seed = body.get('seed', 0)
            if type(seed) is not int or not 0 <= seed < 2**31: raise ValueError('Invalid benchmark seed')
            generator = self.torch.Generator().manual_seed(seed)
            tensor = self.torch.rand((1,3,224,224), generator=generator)
            kind = 'synthetic benchmark tensor'
        with self.torch.inference_mode():
            probabilities = self.model(tensor.to(self.device)).softmax(1)
            scores, indices = probabilities.topk(3)
            predictions = [{'class_id':i, 'label':self.weights.meta['categories'][i], 'score':s}
                           for i,s in zip(indices[0].tolist(),scores[0].tolist())]
        if self.device.startswith('cuda'): self.torch.cuda.synchronize()
        return dict(predictions=predictions, input_kind=kind, pretrained=self.pretrained, device=self.device)

    def vram(self):
        return self.torch.cuda.memory_allocated(self.device) if self.device.startswith('cuda') else 0

class Inference:
    def __init__(self, model, queue_limit=8):
        self.model = model
        self.metrics = Metrics('inference')
        self.admission = threading.BoundedSemaphore(queue_limit+1)
        self.worker, self.lock = threading.Lock(), threading.Lock()
        self.waiting, self.busy, self.completed = 0, False, 0
        self.draining=False
        self.admitted=0
        self.compute_started=0.
        self.cycles = deque(maxlen=100)
        self.metrics.ready.set(1)

    def state(self):
        with self.lock:
            samples = list(self.cycles)
            cycle = sum(samples)/len(samples) if samples else 50.
            variance = sum((v-cycle)**2 for v in samples)/len(samples) if samples else cycle**2
            healthy=not self.busy or time.monotonic()-self.compute_started<60
            return dict(ready=not self.draining and healthy,healthy=healthy,queue=self.waiting,busy=self.busy,cycle_ms=cycle,
                        variance_ms2=variance,completed=self.completed,vram_bytes=self.model.vram(),
                        model_load_seconds=self.model.load_seconds)

    def dispatch(self, method, path, body=None):
        if method=='GET' and path=='/metrics': return 200,self.metrics.export()
        if method=='GET' and path=='/live':
            healthy=self.state()['healthy']
            return (200 if healthy else 503),{'healthy':healthy}
        if method=='GET' and path in ('/ready','/state'):
            state=self.state()
            return (503 if path=='/ready' and not state['ready'] else 200),state
        if method!='POST' or path!='/infer': return 404,{'error':'Unknown endpoint'}
        tier,deadline = request_parameters(body)
        start = time.perf_counter()
        self.metrics.offered.labels(tier).inc()
        with self.lock:
            admitted=not self.draining and self.admission.acquire(blocking=False)
            if admitted:
                self.admitted+=1
                self.waiting+=1
                self.metrics.queue.set(self.waiting)
        if not admitted:
            self.metrics.finish(tier,time.perf_counter()-start,deadline,'rejected')
            return 503,{'error':'Replica draining' if self.draining else 'Queue full','tier':tier}
        try:
            with self.worker:
                with self.lock:
                    self.waiting -= 1
                    self.busy = True
                    self.compute_started=time.monotonic()
                    self.metrics.queue.set(self.waiting)
                compute_start = time.perf_counter()
                try:
                    result = self.model.predict(body)
                    cycle_ms = (time.perf_counter()-compute_start)*1000
                    with self.lock:
                        self.cycles.append(cycle_ms)
                        self.completed += 1
                finally:
                    with self.lock: self.busy=False
            elapsed=time.perf_counter()-start
            self.metrics.finish(tier,elapsed,deadline)
            self.metrics.vram.set(self.model.vram())
            return 200,dict(result,latency_ms=elapsed*1000,queue_ms=(compute_start-start)*1000,execution_ms=cycle_ms,sla_breach=elapsed*1000>deadline)
        except Exception:
            self.metrics.finish(tier,time.perf_counter()-start,deadline,'failed')
            raise
        finally:
            with self.lock:
                self.admitted-=1
                self.admission.release()

    def active_requests(self):
        with self.lock: return self.admitted

    def begin_drain(self):
        with self.lock:
            self.draining=True
            self.metrics.ready.set(0)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8080')))
    parser.add_argument('--host',default=os.getenv('HOST','127.0.0.1'))
    args=parser.parse_args()
    model=TorchModel(os.getenv('MODEL','mobilenet'),os.getenv('DEVICE','cpu'),os.getenv('PRETRAINED','true').lower()=='true')
    run_server(Inference(model,int(os.getenv('QUEUE_LIMIT','8'))),args.host,args.port)

if __name__=='__main__': main()
