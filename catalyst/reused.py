"""Generic helpers extracted from user-owned AIMCO/VISTA artifacts. See docs/reuse-provenance.json. No controller or research objective is imported."""
from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
import gzip


def jsonable(value):
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value

def digest(value):
    return hashlib.sha256(json.dumps(jsonable(value), sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()

def quantile(values,p):
    values=sorted(values)
    if not values:return None
    x=(len(values)-1)*p;a=int(x);b=min(a+1,len(values)-1)
    return values[a]+(values[b]-values[a])*(x-a)

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')

def write_gzip(path,data):
    with path.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as z:z.write(json.dumps(data,separators=(',',':'),allow_nan=False).encode())
