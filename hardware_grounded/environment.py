"""Detect actual hardware and require a successful CUDA kernel, never fallback."""
import csv,ctypes,importlib.metadata,json,os,platform,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"results/hardware_grounded"


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")


def command(args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=20,check=True)
        return p.stdout.strip()
    except (OSError,subprocess.SubprocessError):return None


def telemetry():
    """Read-only NVSMI/power observations; unavailable readings remain null."""
    fields=("name","driver_version","memory.total","memory.used","temperature.gpu","pstate","power.draw","power.limit","clocks.current.graphics","clocks.current.memory","utilization.gpu")
    raw=command(["nvidia-smi","--query-gpu="+",".join(fields),"--format=csv,noheader,nounits"])
    result={"utc":datetime.now(timezone.utc).isoformat(),"gpu":[],"ac_power":None}
    if raw:
        result["gpu"]=[dict(zip(fields,(None if v.strip() in ("[N/A]","N/A") else v.strip() for v in row))) for row in csv.reader(raw.splitlines())]
    if os.name=="nt":
        class Power(ctypes.Structure):
            _fields_=[("ac",ctypes.c_ubyte),("battery",ctypes.c_ubyte),("percent",ctypes.c_ubyte),("reserved",ctypes.c_ubyte),("life",ctypes.c_ulong),("full",ctypes.c_ulong)]
        status=Power()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)) and status.ac in (0,1):result["ac_power"]=bool(status.ac)
    return result


def check():
    """Record software, device capability and a synchronized CUDA arithmetic test."""
    info=dict(python_version=platform.python_version(),python_executable=sys.executable,operating_system=platform.platform(),
        cpu_model=platform.processor(),logical_cpu_count=os.cpu_count(),system_ram_bytes=None,torch_version=None,torchvision_version=None,
        cuda_build_version=None,cuda_available=False,cuda_device_count=0,devices=[],cuda_kernel_success=False,
        torchvision_import_success=False,errors=[],telemetry=telemetry())
    if os.name=="nt":
        cpu=command(["powershell","-NoProfile","-Command","Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress"])
        ram=command(["powershell","-NoProfile","-Command","Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory | ConvertTo-Json -Compress"])
        if cpu:
            value=json.loads(cpu);info["cpu_details"]=value;info["cpu_model"]=value["Name"] if isinstance(value,dict) else "; ".join(x["Name"] for x in value)
        if ram:info["system_ram_bytes"]=json.loads(ram)["TotalPhysicalMemory"]
    try:
        import torch
        info.update(torch_version=torch.__version__,cuda_build_version=torch.version.cuda,cuda_available=torch.cuda.is_available(),cuda_device_count=torch.cuda.device_count())
        info["compiled_cuda_architectures"]=torch.cuda.get_arch_list()
        for i in range(torch.cuda.device_count()):
            p=torch.cuda.get_device_properties(i)
            info["devices"].append(dict(index=i,name=p.name,total_vram_bytes=p.total_memory,compute_capability=[p.major,p.minor],
                free_and_total_bytes=list(torch.cuda.mem_get_info(i))))
        if info["cuda_available"]:
            x=torch.arange(32,dtype=torch.float32,device="cuda")*2;torch.cuda.synchronize()
            assert float(x.sum().item())==992.
            info["cuda_kernel_success"]=True
            info["memory_state"]={k:int(getattr(torch.cuda,k)()) for k in ("memory_allocated","memory_reserved","max_memory_allocated","max_memory_reserved")}
            del x
        import torchvision
        info["torchvision_version"]=torchvision.__version__;info["torchvision_import_success"]=True
    except Exception as e:info["errors"].append(type(e).__name__+": "+str(e))
    info["ready_for_gpu_profiling"]=bool(info["cuda_available"] and info["cuda_kernel_success"] and info["torchvision_import_success"])
    info["background_load_caveat"]="Single laptop; no clock/power control or background-process isolation. Reported readings are observations, not lab isolation."
    if (OUTPUT/"hardware_profiles.json").exists():
        write_json(OUTPUT/"latest_environment_check.json",info)
    else:
        write_json(OUTPUT/"hardware_info.json",info);write_json(OUTPUT/"profiling/hardware_info.json",info)
    print(json.dumps(info,indent=2),flush=True)
    return info
