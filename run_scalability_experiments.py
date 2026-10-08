"""Pilot, run and verify the frozen three-scale JointSLA experiment."""
import argparse
import json
import os
from pathlib import Path
from scalability.configuration import ROOT
from scalability.experiment import run,sources,safe_output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds",default="1:30",choices=("1:30",))
    parser.add_argument("--pilot",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/"results/scalability_30seeds")
    mode=parser.add_mutually_exclusive_group();mode.add_argument("--reuse-results",action="store_true");mode.add_argument("--force",action="store_true")
    args=parser.parse_args();output=safe_output(args.output);os.chdir(ROOT)
    if args.pilot:
        run(output/"pilot",range(1,4),pilot=True,reuse=args.reuse_results,force=args.force)
        print("Pilot completed and guarded; no main inference on three seeds.",flush=True);return
    if not args.reuse_results:
        pilot=output/"pilot/pilot_validation.json"
        if not pilot.exists():run(output/"pilot",range(1,4),pilot=True)
        status=json.loads(pilot.read_text(encoding="utf-8"))
        assert status["successful"] and status["source_hashes"]==sources(),"successful matching pilot required"
    raw=run(output,range(1,31),reuse=args.reuse_results,force=args.force)
    from scalability.analysis import analyze
    from scalability.presentation import create
    from scalability.validation import verify
    analyze(raw,output);create(output);status=verify(output)
    print(f"Complete: {status['successful_runs']} main runs; {status['requests_verified']:,} requests verified. Report: {output/'report.md'}",flush=True)


if __name__=="__main__":main()
