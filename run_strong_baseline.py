"""Run the frozen causal MJO pilot and 30-seed publication experiment."""
import argparse,os
from strong_baseline.protocol import ROOT,OUTPUT,configure
from strong_baseline.experiment import pilot,run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot",action="store_true")
    parser.add_argument("--seeds",default="1:30",choices=("1:30",))
    mode=parser.add_mutually_exclusive_group();mode.add_argument("--reuse-results",action="store_true");mode.add_argument("--force",action="store_true")
    args=parser.parse_args();os.chdir(ROOT);configure()
    if args.pilot:
        pilot(args.force);print("Pilot complete",flush=True);return
    if not args.reuse_results and not (OUTPUT/"pilot_validation.json").exists():pilot()
    raw=run(args.force,args.reuse_results)
    from strong_baseline.analysis import analyze
    from strong_baseline.presentation import create
    from strong_baseline.validation import verify
    analyze(raw);create();verify()
    print(f"Complete: {OUTPUT/'report.md'}",flush=True)


if __name__=="__main__":main()
