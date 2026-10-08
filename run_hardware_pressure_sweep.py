"""Frozen hardware pressure sweep; paired policy execution and analysis."""
import argparse
from hardware_pressure.design import LOADS
from hardware_pressure.experiment import SWEEP,verify_protected,pilot,freeze,execute
from hardware_pressure.analysis import sweep_analysis

def seeds(value):
    if ':' in value:
        a,b=map(int,value.split(':'));return list(range(a,b+1))
    return list(map(int,value.split(',')))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pilot',action='store_true')
    p.add_argument('--loads',default=','.join(map(str,LOADS)));p.add_argument('--seeds',default='1:30')
    p.add_argument('--reuse-results',action='store_true');p.add_argument('--force',action='store_true');args=p.parse_args()
    print(verify_protected(),flush=True)
    if args.pilot:pilot();return
    loads=list(map(float,args.loads.split(',')));ss=seeds(args.seeds)
    assert set(loads)<=set(LOADS) and set(ss)<=set(range(1,31)) and len(loads)==len(set(loads)) and len(ss)==len(set(ss))
    import json
    assert json.loads((SWEEP/'pilot_validation.json').read_text())['successful']
    freeze();raw=execute(SWEEP,loads,ss,'sweep',args.reuse_results,args.force)
    if set(loads)==set(LOADS) and set(ss)==set(range(1,31)):print(sweep_analysis(raw),flush=True)
    print(verify_protected(),flush=True)

if __name__=='__main__':main()
