"""Reproduce the frozen JointSLA experiment without changing verified baselines."""
import argparse
from dataclasses import replace
from pathlib import Path
import os
from dynamic_placement.config import Config
from paper_evaluation.experiments import ROOT
from run_paper_experiments import parse_seeds
from joint_routing.router import Settings
from joint_routing.experiment import run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds",type=parse_seeds,default=parse_seeds("1:30"))
    parser.add_argument("--output",type=Path,default=ROOT/"results/joint_routing_30seeds")
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--reuse-results",action="store_true")
    mode.add_argument("--force",action="store_true")
    args=parser.parse_args()
    if args.seeds!=list(range(1,31)):
        parser.error("this controlled experiment requires the verified seeds 1:30")
    output=args.output.resolve()
    os.chdir(ROOT)
    config=replace(Config.load(ROOT/"dynamic_placement/config.json"),first_seed=1,trials=30)
    raw=run(config,args.seeds,output,Settings(),reuse=args.reuse_results,force=args.force)
    from joint_routing.analysis import analyze
    from joint_routing.presentation import create
    from joint_routing.validation import verify
    analyze(raw,output,Settings())
    create(output,Settings())
    result=verify(output)
    print(f"Complete: {result['combined_runs']} comparative runs; {result['new_runs']} new simulations; preserved baseline verified.",flush=True)
    print(f"Report: {output/'report.md'}",flush=True)


if __name__=="__main__":
    main()
