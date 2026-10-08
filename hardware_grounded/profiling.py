"""Synchronized FP32 architecture profiling; no pretrained weights or datasets."""
import gc
import json
from datetime import datetime, timezone
from time import perf_counter
import numpy as np
import pandas as pd
from .environment import OUTPUT, write_json, telemetry
from .integrity import sha, verify

MODELS={'mobilenet':'mobilenet_v3_large','resnet50':'resnet50','vit_b16':'vit_b_16'}
PROTOCOL=dict(batch_size=1,input_shape=[3,224,224],dtype='float32',weights='locally initialized',
    torch_seed=7107,input_seed=8123,cpu_threads=1,gpu_warmups=50,gpu_repetitions=300,
    cold_repetitions=20,cold_warmups=30,cpu_warmups=10,cpu_repetitions=30,
    tf32=False,cudnn_benchmark=False,
    cpu_pre='In-memory uint8 256x256 RGB; bilinear antialiased resize, float32 normalization, contiguous NCHW; no disk I/O.',
    gpu_forward='Resident CUDA input; CUDA events around forward only, synchronized before and after.',
    cpu_post='Logits CUDA-to-CPU transfer, explicit synchronization, softmax, top-5 and argmax; transfer included.',
    upload='Input CPU-to-CUDA transfer measured separately with host timer and explicit synchronization.',
    cold='New Python model, cached local state load, CPU-to-GPU transfer, first synchronized forward. CUDA process/driver already initialized; OS disk cache not evicted. Delete model/output references, GC and empty CUDA allocator cache between repetitions.',
    memory='Residency allocated delta for model parameters/buffers. Inference peaks include model/input/output/workspace; allocated and reserved are distinct, not summed.',
    accuracy='Latency/memory profiling concerns model architecture execution, not task accuracy.')


def statistics(values):
    x=np.asarray(values,dtype=float)
    return dict(count=len(x),mean=float(x.mean()),median=float(np.median(x)),std=float(x.std(ddof=1)) if len(x)>1 else 0.,
        **{f'p{p}':float(np.percentile(x,p)) for p in (50,90,95,99)},min=float(x.min()),max=float(x.max()))


def profile(names,force,hardware):
    import torch
    from torchvision import models
    from torchvision.transforms import functional as F, InterpolationMode
    if set(names)-set(MODELS):raise ValueError('Supported models: '+','.join(MODELS))
    directory=OUTPUT/'profiling';directory.mkdir(parents=True,exist_ok=True)
    if (directory/'model_profile_summary.csv').exists() and not force:
        raise FileExistsError('Profiles already exist; use --force to explicitly reprofile.')
    if (OUTPUT/'experiment_freeze.json').exists():raise RuntimeError('Profiles are frozen for evaluation; do not reprofile this experiment.')
    write_json(OUTPUT/'hardware_info.json',hardware);write_json(directory/'hardware_info.json',hardware)
    write_json(directory/'profiling_protocol.json',PROTOCOL)
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.backends.cudnn.benchmark=False;torch.set_float32_matmul_precision('highest')
    torch.manual_seed(PROTOCOL['torch_seed'])
    image=torch.from_numpy(np.random.default_rng(PROTOCOL['input_seed']).integers(0,256,(3,256,256),dtype=np.uint8))
    def preprocess():
        value=F.resize(image,[224,224],interpolation=InterpolationMode.BILINEAR,antialias=True)
        value=value.to(torch.float32).div_(255)
        value=F.normalize(value,[.485,.456,.406],[.229,.224,.225])
        return value.unsqueeze(0).contiguous()
    def elapsed_forward(model,x):
        torch.cuda.synchronize();start=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True)
        wall=perf_counter();start.record();y=model(x);end.record();torch.cuda.synchronize()
        return y,float(start.elapsed_time(end)),(perf_counter()-wall)*1000
    summaries=[];cold_summaries=[];vram=[];cpu_summaries=[];catalog={};observations=[]
    with torch.inference_mode():
        for name in names:
            print('PROFILE '+name,flush=True)
            before=telemetry();rows=[];order=0
            def record(iteration,stage,latency,device,phase='steady'):
                nonlocal order
                order+=1;rows.append(dict(model=name,architecture=MODELS[name],batch_size=1,iteration=iteration,phase=phase,
                    stage=stage,latency_ms=float(latency),device=device,timestamp_utc=datetime.now(timezone.utc).isoformat(),measurement_order=order))
            constructor=getattr(models,MODELS[name]);state_path=directory/'states'/f'{name}.pt';state_path.parent.mkdir(exist_ok=True)
            torch.manual_seed(PROTOCOL['torch_seed'])
            model=constructor(weights=None).eval()
            if not state_path.exists():torch.save(model.state_dict(),state_path)
            else:model.load_state_dict(torch.load(state_path,map_location='cpu',weights_only=True))
            gc.collect();torch.cuda.empty_cache();baseline=torch.cuda.memory_allocated()
            model=model.to('cuda');torch.cuda.synchronize();residency=torch.cuda.memory_allocated()-baseline
            x=preprocess().to('cuda');torch.cuda.synchronize()
            for _ in range(PROTOCOL['gpu_warmups']):y=model(x)
            torch.cuda.synchronize();del y,x;torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
            allocated_after_load=torch.cuda.memory_allocated();reserved_after_load=torch.cuda.memory_reserved()
            for i in range(PROTOCOL['gpu_repetitions']):
                start=perf_counter();cpu_x=preprocess();record(i,'cpu_pre',(perf_counter()-start)*1000,'cpu')
                torch.cuda.synchronize();start=perf_counter();x=cpu_x.to('cuda');torch.cuda.synchronize()
                record(i,'input_upload',(perf_counter()-start)*1000,'cpu+cuda')
                y,ms,wall=elapsed_forward(model,x);record(i,'gpu_inference',ms,'cuda');record(i,'gpu_forward_wall',wall,'cpu+cuda')
                start=perf_counter();logits=y.cpu();torch.cuda.synchronize();probs=logits.softmax(-1);probs.topk(5);probs.argmax(-1)
                record(i,'cpu_post',(perf_counter()-start)*1000,'cpu+cuda')
                del y,x,logits,probs,cpu_x
            peak_allocated=torch.cuda.max_memory_allocated();peak_reserved=torch.cuda.max_memory_reserved()
            vram.append(dict(model=name,model_residency_bytes=int(residency),allocated_after_model_load_bytes=int(allocated_after_load),
                reserved_after_model_load_bytes=int(reserved_after_load),inference_peak_allocated_bytes=int(peak_allocated),
                inference_peak_reserved_bytes=int(peak_reserved),baseline_allocated_bytes=int(baseline)))
            del model;gc.collect();torch.cuda.empty_cache()
            for i in range(PROTOCOL['cold_repetitions']):
                torch.manual_seed(PROTOCOL['torch_seed'])
                start=perf_counter();model=constructor(weights=None).eval();construction=(perf_counter()-start)*1000
                record(i,'construction',construction,'cpu','cold')
                start=perf_counter();state=torch.load(state_path,map_location='cpu',weights_only=True);model.load_state_dict(state);del state
                load=(perf_counter()-start)*1000;record(i,'local_state_load',load,'cpu','cold')
                torch.cuda.synchronize();start=perf_counter();model=model.to('cuda');torch.cuda.synchronize()
                transfer=(perf_counter()-start)*1000;record(i,'model_gpu_transfer',transfer,'cpu+cuda','cold')
                x=preprocess().to('cuda');y,ms,wall=elapsed_forward(model,x)
                record(i,'first_gpu_inference',ms,'cuda','cold');record(i,'first_gpu_forward_wall',wall,'cpu+cuda','cold')
                record(i,'cold_start_total',construction+load+transfer+wall,'cpu+cuda','cold')
                del y
                for _ in range(PROTOCOL['cold_warmups']):y=model(x)
                torch.cuda.synchronize();del y
                y,ms,wall=elapsed_forward(model,x);record(i,'warmed_gpu_inference',ms,'cuda','cold')
                del y,x,model;gc.collect();torch.cuda.empty_cache()
            torch.manual_seed(PROTOCOL['torch_seed']);model=constructor(weights=None).eval()
            model.load_state_dict(torch.load(state_path,map_location='cpu',weights_only=True));x=preprocess()
            for _ in range(PROTOCOL['cpu_warmups']):y=model(x)
            for i in range(PROTOCOL['cpu_repetitions']):
                start=perf_counter();y=model(x);record(i,'cpu_inference',(perf_counter()-start)*1000,'cpu','cpu_secondary')
            del model,x,y;gc.collect();torch.cuda.empty_cache()
            frame=pd.DataFrame(rows);frame.to_csv(directory/f'{name}_raw.csv',index=False)
            assert np.isfinite(frame.latency_ms).all() and (frame.latency_ms>0).all()
            assert len(frame[(frame.phase=='steady') & (frame.stage=='gpu_inference')])==300
            assert residency>0 and peak_allocated>=residency and peak_reserved>=peak_allocated
            for (phase,stage),group in frame.groupby(['phase','stage'],sort=False):
                item=dict(model=name,architecture=MODELS[name],batch_size=1,phase=phase,stage=stage,**statistics(group.latency_ms))
                (cold_summaries if phase=='cold' else cpu_summaries if phase=='cpu_secondary' else summaries).append(item)
            stage_stats={stage:statistics(group.latency_ms) for stage,group in frame[frame.phase=='steady'].groupby('stage')}
            cold_stats={stage:statistics(group.latency_ms) for stage,group in frame[frame.phase=='cold'].groupby('stage')}
            catalog[name]=dict(architecture=MODELS[name],batch_size=1,dtype='float32',input_shape=[3,224,224],
                cpu_pre_ms=stage_stats['cpu_pre']['median'],gpu_inference_ms=stage_stats['gpu_inference']['median'],
                cpu_post_ms=stage_stats['cpu_post']['median'],input_upload_ms=stage_stats['input_upload']['median'],
                vram_mb=peak_allocated/2**20,model_residency_mb=residency/2**20,cold_start_ms=cold_stats['cold_start_total']['median'],
                stage_statistics=stage_stats,cold_statistics=cold_stats,checkpoint_sha256=sha(state_path),raw_sha256=sha(directory/f'{name}_raw.csv'))
            assert catalog[name]['cold_start_ms']>catalog[name]['gpu_inference_ms']
            observations.append(dict(model=name,before=before,after=telemetry()))
            print(f"DONE {name}: GPU median {catalog[name]['gpu_inference_ms']:.3f} ms; cold {catalog[name]['cold_start_ms']:.3f} ms; peak allocated {catalog[name]['vram_mb']:.2f} MiB",flush=True)
    pd.DataFrame(summaries).to_csv(directory/'model_profile_summary.csv',index=False)
    pd.DataFrame(cold_summaries).to_csv(directory/'cold_start_summary.csv',index=False)
    pd.DataFrame(vram).to_csv(directory/'vram_summary.csv',index=False)
    pd.DataFrame(cpu_summaries).to_csv(directory/'cpu_profile_summary.csv',index=False)
    write_json(directory/'telemetry.json',observations)
    write_json(OUTPUT/'hardware_profiles.json',dict(schema_version=1,units=dict(timing='ms',vram='MiB (2^20 bytes)'),
        protocol=PROTOCOL,hardware_sha256=sha(OUTPUT/'hardware_info.json'),models=catalog))
    report=['# Raw hardware profiling report','',PROTOCOL['accuracy'],'',
        'Single-machine laptop calibration. CUDA initialized before all model-cold measurements. Local checkpoint reads may use the OS cache. No process/driver startup, internet, disk I/O in steady preprocessing, power changes, or task accuracy measurements.','',
        '## Protocol','',json.dumps(PROTOCOL,indent=2),'','## Steady stages (ms)','',pd.DataFrame(summaries).to_csv(index=False),
        '## VRAM (bytes)','',pd.DataFrame(vram).to_csv(index=False),'## Cold start (ms)','',pd.DataFrame(cold_summaries).to_csv(index=False),
        '## Secondary CPU inference (ms)','',pd.DataFrame(cpu_summaries).to_csv(index=False)]
    (directory/'report.md').write_text('\n'.join(report),encoding='utf-8')
    write_json(directory/'validation.json',dict(frozen_files=verify(),raw_rows=sum(len(pd.read_csv(directory/f'{n}_raw.csv')) for n in names),
        actual_counts={n:dict(gpu_warmups=50,gpu_measured=300,cold_repetitions=20,cpu_measured=30) for n in names}))
