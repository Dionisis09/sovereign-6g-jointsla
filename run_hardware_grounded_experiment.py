"""Run frozen hardware calibration pilot or paired MEDIUM evaluation."""
import argparse


def parse_seeds(text):
    if ':' in text:
        first,last=map(int,text.split(':'));values=list(range(first,last+1))
    else:values=[int(s) for s in text.split(',')]
    if not values or len(values)!=len(set(values)) or min(values)<1 or max(values)>30:raise ValueError('Unique seeds must be in 1:30')
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--seeds');parser.add_argument('--reuse-results',action='store_true');parser.add_argument('--force',action='store_true')
    args=parser.parse_args();seeds=parse_seeds(args.seeds or ('1,2,3' if args.pilot else '1:30'))
    if args.pilot and seeds!=[1,2,3]:raise ValueError('Pilot requires seeds 1,2,3')
    from hardware_grounded.experiment import run
    raw=run(seeds,args.pilot,args.reuse_results,args.force)
    if not args.pilot and seeds==list(range(1,31)):
        from hardware_grounded.analysis import analyze
        analyze(raw)


if __name__=='__main__':main()
