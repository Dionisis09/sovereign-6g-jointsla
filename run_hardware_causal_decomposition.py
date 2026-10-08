"""Exploratory E/V/C factorial study of frozen SLA-aware and JointSLA."""
import argparse
from hardware_pressure.experiment import CAUSAL,freeze,verify_protected,execute
from hardware_pressure.design import REGIMES
from hardware_pressure.analysis import decomposition_analysis
from run_hardware_pressure_sweep import seeds

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pilot',action='store_true')
    p.add_argument('--regimes',default=','.join(REGIMES));p.add_argument('--seeds',default='1:10')
    p.add_argument('--reuse-results',action='store_true');p.add_argument('--force',action='store_true');args=p.parse_args()
    print(verify_protected(),flush=True);freeze()
    regimes=args.regimes.split(',');ss=[1,2,3] if args.pilot else seeds(args.seeds)
    assert set(regimes)<=set(REGIMES) and set(ss)<=set(range(1,31)) and len(regimes)==len(set(regimes))
    raw=execute(CAUSAL/'pilot' if args.pilot else CAUSAL,regimes,ss,'causal',args.reuse_results,args.force)
    if not args.pilot and set(regimes)==set(REGIMES) and ss==list(range(1,11)):print(decomposition_analysis(raw),flush=True)
    print(verify_protected(),flush=True)

if __name__=='__main__':main()
